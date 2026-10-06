"""Email issued documents to customers. Sending happens in the background worker."""

import base64
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.db import after_commit
from app.core.errors import Conflict
from app.emails.templates import document_email
from app.jobs import queue
from app.models import Business, DeliveryStatus, DocumentDelivery, DocumentStatus, DocumentType
from app.schemas.documents import EmailDefaults, EmailRequest
from app.services import audit, branding, documents
from app.services.document_rules import RULES
from app.services.permissions import Permission, require

LOGO_CID = "business-logo"


async def defaults(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID
) -> EmailDefaults:
    document = await documents.get_document(session, ctx, document_id)
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    title = RULES[DocumentType(document.type)].title_he
    customer = document.customer or {}
    greeting = f"שלום {customer['name']}," if customer.get("name") else "שלום,"
    return EmailDefaults(
        to=[customer["email"]] if customer.get("email") else [],
        subject=f"{title} מס׳ {document.number or ''} מאת {business.display_name}".strip(),
        message=(
            f"{greeting}\n\nמצ״ב {title} מס׳ {document.number}.\n"
            "לכל שאלה ניתן להשיב למייל זה.\n\n"
            f"בברכה,\n{business.display_name}"
        ),
    )


async def send(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID, request: EmailRequest
) -> DocumentDelivery:
    require(ctx.role, Permission.ISSUE_DOCUMENTS)
    document = await documents.get_document(session, ctx, document_id)
    if document.status != DocumentStatus.ISSUED:
        raise Conflict("Only issued documents can be sent", code="document_not_issued")
    # The first email carries the original; later ones carry marked copies.
    pdf, _, variant = await documents.pdf(session, ctx, document_id)
    business = await session.get(Business, ctx.business_id)
    assert business is not None and document.number is not None
    title = RULES[DocumentType(document.type)].title_he
    snapshot = document.business_snapshot or {}
    logo = await branding.load_file(session, snapshot.get("logo_file_id"))

    delivery = DocumentDelivery(
        business_id=ctx.business_id,
        document_id=document.id,
        recipients=[str(r) for r in request.to],
        subject=request.subject,
        variant=variant,
        status=DeliveryStatus.QUEUED,
        attempts=0,
        created_by_user_id=ctx.principal.user_id,
    )
    session.add(delivery)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="document.emailed",
        entity_type="document",
        entity_id=document.id,
        business_id=ctx.business_id,
        changes={"to": delivery.recipients, "variant": variant, "delivery_id": str(delivery.id)},
    )

    html, text = document_email(
        to=delivery.recipients,
        subject=request.subject,
        message=request.message,
        business_name=snapshot.get("display_name", business.display_name),
        title=title,
        number=document.number,
        total=f"{document.total:,.2f}",
        logo_cid=LOGO_CID if logo else None,
    )
    job = {
        "delivery_id": str(delivery.id),
        "business_id": str(ctx.business_id),
        "to": delivery.recipients,
        "subject": request.subject,
        "html": html,
        "text": text,
        "attachment_name": f"{title} {document.number}.pdf".replace("/", "-"),
        "attachment_b64": base64.b64encode(pdf).decode(),
        "logo_b64": base64.b64encode(logo).decode() if logo else None,
        "logo_cid": LOGO_CID,
    }

    async def enqueue() -> None:
        await queue.enqueue("send_document_email", **job)

    after_commit(session, enqueue)
    return delivery


async def list_for(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentDelivery]:
    rows = await session.scalars(
        select(DocumentDelivery)
        .where(DocumentDelivery.document_id == document_id)
        .order_by(DocumentDelivery.created_at.desc())
    )
    return list(rows)
