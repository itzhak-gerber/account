import uuid
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from app.auth.principal import CurrentBusiness, DbSession
from app.core.db import commit
from app.models import Business, BusinessType, DocumentStatus, DocumentType
from app.schemas.documents import (
    ConvertIn,
    DocumentIn,
    DocumentOut,
    DocumentPatch,
    DocumentSummary,
    DocumentTypeInfo,
    NumberingIn,
    NumberingOut,
)
from app.services import audit, documents, numbering
from app.services.document_rules import RULES, allowed_types
from app.services.permissions import Permission, require

router = APIRouter(prefix="/businesses/{business_id}", tags=["documents"])


@router.get("/document-types")
async def document_types(ctx: CurrentBusiness, session: DbSession) -> list[DocumentTypeInfo]:
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    return [
        DocumentTypeInfo(
            type=t,
            title=RULES[t].title_he,
            has_lines=RULES[t].has_lines,
            has_payments=RULES[t].has_payments,
            is_tax_document=RULES[t].is_tax_document,
            shows_vat=RULES[t].shows_vat,
            has_due_date=RULES[t].has_due_date,
        )
        for t in allowed_types(BusinessType(business.business_type))
    ]


@router.get("/documents")
async def list_documents(
    ctx: CurrentBusiness,
    session: DbSession,
    type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    customer_id: uuid.UUID | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentSummary]:
    return await documents.list_documents(
        session,
        ctx,
        doc_type=type,
        status=status,
        customer_id=customer_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
        open_only=open_only,
        limit=limit,
        offset=offset,
    )


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def create_draft(ctx: CurrentBusiness, data: DocumentIn, session: DbSession) -> DocumentOut:
    document = await documents.create_draft(session, ctx, data)
    out = await documents.to_out(session, document)
    await commit(session)
    return out


@router.get("/documents/{document_id}")
async def get_document(
    ctx: CurrentBusiness, document_id: uuid.UUID, session: DbSession
) -> DocumentOut:
    return await documents.to_out(session, await documents.get_document(session, ctx, document_id))


@router.patch("/documents/{document_id}")
async def update_draft(
    ctx: CurrentBusiness, document_id: uuid.UUID, patch: DocumentPatch, session: DbSession
) -> DocumentOut:
    document = await documents.update_draft(session, ctx, document_id, patch)
    out = await documents.to_out(session, document)
    await commit(session)
    return out


@router.delete("/documents/{document_id}", status_code=204)
async def delete_draft(ctx: CurrentBusiness, document_id: uuid.UUID, session: DbSession) -> None:
    await documents.delete_draft(session, ctx, document_id)
    await commit(session)


@router.post("/documents/{document_id}/issue")
async def issue(ctx: CurrentBusiness, document_id: uuid.UUID, session: DbSession) -> DocumentOut:
    document = await documents.issue(session, ctx, document_id)
    out = await documents.to_out(session, document)
    await commit(session)
    return out


@router.post("/documents/{document_id}/convert", status_code=201)
async def convert(
    ctx: CurrentBusiness, document_id: uuid.UUID, data: ConvertIn, session: DbSession
) -> DocumentOut:
    document = await documents.convert(session, ctx, document_id, data.type)
    out = await documents.to_out(session, document)
    await commit(session)
    return out


@router.post("/documents/{document_id}/credit-note", status_code=201)
async def credit_note(
    ctx: CurrentBusiness, document_id: uuid.UUID, session: DbSession
) -> DocumentOut:
    document = await documents.create_credit_note(session, ctx, document_id)
    out = await documents.to_out(session, document)
    await commit(session)
    return out


def pdf_response(content: bytes, filename: str, variant: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "X-Document-Variant": variant,
            "Cache-Control": "no-store",
        },
    )


@router.get("/documents/{document_id}/pdf")
async def document_pdf(
    ctx: CurrentBusiness, document_id: uuid.UUID, session: DbSession
) -> Response:
    content, filename, variant = await documents.pdf(session, ctx, document_id)
    await commit(session)
    return pdf_response(content, filename, variant)


@router.get("/numbering")
async def get_numbering(ctx: CurrentBusiness, session: DbSession) -> NumberingOut:
    require(ctx.role, Permission.VIEW_DOCUMENTS)
    return NumberingOut(next_numbers=await numbering.peek(session, ctx.business_id))


@router.put("/numbering")
async def set_numbering(
    ctx: CurrentBusiness, data: NumberingIn, session: DbSession
) -> NumberingOut:
    require(ctx.role, Permission.MANAGE_BUSINESS)
    await numbering.set_start(session, ctx.business_id, data.type, data.next_number)
    await audit.record(
        session,
        ctx.principal,
        action="numbering.changed",
        entity_type="business",
        entity_id=ctx.business_id,
        business_id=ctx.business_id,
        changes={"type": data.type, "next_number": data.next_number},
    )
    out = NumberingOut(next_numbers=await numbering.peek(session, ctx.business_id))
    await commit(session)
    return out
