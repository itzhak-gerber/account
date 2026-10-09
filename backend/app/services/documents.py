"""Documents: drafts, issuing (numbering, VAT, PDF, immutability), conversions, credit notes."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.storage import get_storage
from app.models import (
    Business,
    BusinessType,
    Document,
    DocumentDelivery,
    DocumentLine,
    DocumentPayment,
    DocumentRelation,
    DocumentStatus,
    DocumentType,
    RelationType,
    StoredFile,
    User,
    VatType,
)
from app.pdf.render import Variant, render_pdf
from app.schemas.documents import (
    AllocationIn,
    AllocationOut,
    CustomerDetails,
    DeliveryNoteStatus,
    DeliveryOut,
    DocumentIn,
    DocumentOut,
    DocumentPatch,
    DocumentSummary,
    LineIn,
    LineOut,
    PaymentIn,
    PaymentOut,
    PaymentStatus,
    RelatedDocument,
)
from app.services import allocation as allocation_numbers
from app.services import (
    audit,
    branding,
    catalog,
    events,
    inventory,
    numbering,
    vat,
)
from app.services.calc import ZERO, LineInput, compute_totals, money
from app.services.document_rules import (
    BILLS_DELIVERY_NOTES,
    CONVERSIONS,
    CREDITABLE,
    RULES,
    allowed_types,
    charges_vat,
)
from app.services.permissions import Permission, require


class InvalidDocument(AppError):
    status_code = 422
    code = "invalid_document"


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


async def _business(session: AsyncSession, ctx: BusinessContext) -> Business:
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    return business


async def _load(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID, *, lock: bool = False
) -> Document:
    query = select(Document).where(
        Document.id == document_id, Document.business_id == ctx.business_id
    )
    if lock:
        query = query.with_for_update()
    document = await session.scalar(query)
    if document is None:
        raise NotFound("Document not found", code="document_not_found")
    return document


def _require_draft(document: Document) -> None:
    if document.status != DocumentStatus.DRAFT:
        raise Conflict("Issued documents cannot be changed", code="document_issued")


def _customer_dict(details: CustomerDetails) -> dict[str, Any]:
    data = details.model_dump()
    data["email"] = data["email"] or ""
    return data


def _business_snapshot(business: Business) -> dict[str, Any]:
    return {
        "legal_name": business.legal_name,
        "display_name": business.display_name,
        "tax_id": business.tax_id,
        "business_type": business.business_type,
        "address_street": business.address_street,
        "address_city": business.address_city,
        "address_zip": business.address_zip,
        "phone": business.phone,
        "email": business.email,
        "logo_file_id": str(business.logo_file_id) if business.logo_file_id else None,
    }


async def _vat_rate(session: AsyncSession, business: Business, document: Document) -> Decimal:
    doc_type = DocumentType(document.type)
    if doc_type == DocumentType.CREDIT_NOTE:
        return document.vat_rate  # fixed to the credited invoice's rate
    if not charges_vat(BusinessType(business.business_type), doc_type):
        return ZERO
    return await vat.rate_on(session, document.issue_date)


async def _set_customer(
    session: AsyncSession,
    ctx: BusinessContext,
    document: Document,
    customer_id: uuid.UUID | None,
    details: CustomerDetails | None,
) -> None:
    if customer_id is not None:
        customer = await catalog.get_customer(session, ctx, customer_id)
        document.customer_id = customer.id
        document.customer = (
            _customer_dict(details)
            if details is not None
            else {
                "name": customer.name,
                "tax_id": customer.tax_id,
                "email": customer.email,
                "phone": customer.phone,
                "address_street": customer.address_street,
                "address_city": customer.address_city,
                "address_zip": customer.address_zip,
            }
        )
    elif details is not None:
        document.customer_id = None
        document.customer = _customer_dict(details)


async def _set_lines(
    session: AsyncSession, ctx: BusinessContext, document: Document, lines: list[LineIn]
) -> None:
    rules = RULES[DocumentType(document.type)]
    if lines and not rules.has_lines:
        raise InvalidDocument(f"A {document.type} has no item lines", code="lines_not_allowed")
    for line in lines:
        if line.item_id is not None:
            await catalog.get_item(session, ctx, line.item_id)
    document.lines = [
        DocumentLine(
            business_id=ctx.business_id,
            position=i,
            item_id=line.item_id,
            description=line.description,
            quantity=line.quantity,
            unit_of_measure=line.unit_of_measure,
            unit_price=line.unit_price,
            discount_percent=line.discount_percent,
            vat_type=line.vat_type,
            line_total=ZERO,
        )
        for i, line in enumerate(lines)
    ]


def _set_payments(ctx: BusinessContext, document: Document, payments: list[PaymentIn]) -> None:
    if payments and not RULES[DocumentType(document.type)].has_payments:
        raise InvalidDocument(f"A {document.type} has no payments", code="payments_not_allowed")
    document.payments = [
        DocumentPayment(
            business_id=ctx.business_id,
            position=i,
            method=p.method,
            amount=p.amount,
            payment_date=p.payment_date,
            details=p.details.model_dump(exclude_defaults=True),
        )
        for i, p in enumerate(payments)
    ]


async def _recalculate(session: AsyncSession, business: Business, document: Document) -> None:
    rate = await _vat_rate(session, business, document)
    document.vat_rate = rate
    if not RULES[DocumentType(document.type)].has_lines:
        # Receipts: the total is what was received.
        total = money(sum((p.amount for p in document.payments), ZERO))
        document.subtotal, document.discount_total = total, money(ZERO)
        document.vat_amount, document.total = money(ZERO), total
        return
    no_vat = rate == ZERO
    totals = compute_totals(
        [
            LineInput(
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                vat_type=VatType.EXEMPT if no_vat else VatType(line.vat_type),
            )
            for line in document.lines
        ],
        vat_rate=rate,
        prices_include_vat=document.prices_include_vat and not no_vat,
    )
    for line, total in zip(document.lines, totals.line_totals, strict=True):
        line.line_total = total
    document.subtotal = totals.subtotal
    document.discount_total = totals.discount_total
    document.vat_amount = totals.vat_amount
    document.total = totals.total


# --- payments applied to invoices ------------------------------------------------------

# Documents that are a demand for payment and can be paid by receipts.
PAYABLE = frozenset({DocumentType.TAX_INVOICE, DocumentType.PROFORMA_INVOICE})


def balance_due(document: Document) -> Decimal:
    if document.superseded_by_id is not None:
        return ZERO  # the tax invoice issued from this proforma is what is owed now
    return document.total - document.amount_paid - document.amount_credited


def payment_status(document: Document) -> tuple[PaymentStatus | None, Decimal | None]:
    if document.status != DocumentStatus.ISSUED:
        return None, None
    if document.type == DocumentType.TAX_INVOICE_RECEIPT:
        return "paid", money(ZERO)
    if document.type not in PAYABLE:
        return None, None
    if document.superseded_by_id is not None:
        return "superseded", money(ZERO)
    balance = balance_due(document)
    if balance <= ZERO:
        return "paid", money(ZERO)
    if document.amount_paid > ZERO or document.amount_credited > ZERO:
        return "partial", money(balance)
    return "unpaid", money(balance)


def delivery_status(document: Document) -> DeliveryNoteStatus | None:
    """Issued delivery notes: billed by an issued invoice yet, or still open."""
    if document.type != DocumentType.DELIVERY_NOTE or document.status != DocumentStatus.ISSUED:
        return None
    return "open" if document.superseded_by_id is None else "invoiced"


async def _set_allocations(
    session: AsyncSession, ctx: BusinessContext, document: Document, allocations: list[AllocationIn]
) -> None:
    if allocations and DocumentType(document.type) != DocumentType.RECEIPT:
        raise InvalidDocument(
            "Only receipts can be applied to invoices", code="allocations_not_allowed"
        )
    seen: set[uuid.UUID] = set()
    for allocation in allocations:
        if allocation.invoice_id in seen:
            raise InvalidDocument("An invoice appears twice", code="allocation_duplicate")
        seen.add(allocation.invoice_id)
        invoice = await _load(session, ctx, allocation.invoice_id)
        if invoice.status != DocumentStatus.ISSUED or invoice.type not in PAYABLE:
            raise InvalidDocument(
                "Receipts can only pay issued tax invoices or proformas",
                code="allocation_invalid_invoice",
            )
    existing = await session.scalars(
        select(DocumentRelation).where(
            DocumentRelation.from_document_id == document.id,
            DocumentRelation.relation == RelationType.PAYS,
        )
    )
    for relation in existing:
        await session.delete(relation)
    await session.flush()
    for allocation in allocations:
        session.add(
            DocumentRelation(
                business_id=ctx.business_id,
                from_document_id=document.id,
                to_document_id=allocation.invoice_id,
                relation=RelationType.PAYS,
                amount=allocation.amount,
            )
        )
    await session.flush()


async def _allocations(
    session: AsyncSession, document: Document
) -> list[tuple[DocumentRelation, Document]]:
    rows = await session.execute(
        select(DocumentRelation, Document)
        .join(Document, Document.id == DocumentRelation.to_document_id)
        .where(
            DocumentRelation.from_document_id == document.id,
            DocumentRelation.relation == RelationType.PAYS,
        )
        .order_by(DocumentRelation.created_at, Document.number)
    )
    return [(rel, invoice) for rel, invoice in rows.all()]


# --- reading ---------------------------------------------------------------------------


async def related(session: AsyncSession, document: Document) -> list[RelatedDocument]:
    rows = await session.execute(
        select(DocumentRelation, Document)
        .join(
            Document,
            or_(
                (DocumentRelation.from_document_id == document.id)
                & (Document.id == DocumentRelation.to_document_id),
                (DocumentRelation.to_document_id == document.id)
                & (Document.id == DocumentRelation.from_document_id),
            ),
        )
        .order_by(DocumentRelation.created_at)
    )
    return [
        RelatedDocument(
            id=other.id,
            type=DocumentType(other.type),
            number=other.number,
            status=DocumentStatus(other.status),
            relation=RelationType(rel.relation),
            amount=rel.amount,
            direction="outgoing" if rel.from_document_id == document.id else "incoming",
        )
        for rel, other in rows.all()
    ]


async def to_out(session: AsyncSession, document: Document) -> DocumentOut:
    status, balance = payment_status(document)
    allocations = [
        AllocationOut(
            invoice_id=invoice.id,
            invoice_type=DocumentType(invoice.type),
            invoice_number=invoice.number,
            invoice_date=invoice.issue_date,
            invoice_total=invoice.total,
            amount=rel.amount or ZERO,
            balance_due=balance_due(invoice),
        )
        for rel, invoice in await _allocations(session, document)
    ]
    return DocumentOut(
        id=document.id,
        type=DocumentType(document.type),
        title=RULES[DocumentType(document.type)].title_he,
        status=DocumentStatus(document.status),
        number=document.number,
        issue_date=document.issue_date,
        due_date=document.due_date,
        customer_id=document.customer_id,
        customer=CustomerDetails.model_validate(
            {**(document.customer or {}), "email": (document.customer or {}).get("email") or None}
        ),
        currency=document.currency,
        prices_include_vat=document.prices_include_vat,
        returns_stock=document.returns_stock,
        vat_rate=document.vat_rate,
        subtotal=document.subtotal,
        discount_total=document.discount_total,
        vat_amount=document.vat_amount,
        total=document.total,
        notes=document.notes,
        allocation_number=document.allocation_number,
        payment_status=status,
        delivery_status=delivery_status(document),
        allocation_status=await allocation_numbers.latest_status(session, document),
        amount_paid=document.amount_paid,
        amount_credited=document.amount_credited,
        balance_due=balance,
        allocations=allocations,
        deliveries=[
            DeliveryOut.model_validate(d)
            for d in await session.scalars(
                select(DocumentDelivery)
                .where(DocumentDelivery.document_id == document.id)
                .order_by(DocumentDelivery.created_at.desc())
            )
        ],
        lines=[LineOut.model_validate(line) for line in document.lines],
        payments=[PaymentOut.model_validate(p) for p in document.payments],
        related=await related(session, document),
        original_delivered_at=document.original_delivered_at,
        issued_at=document.issued_at,
        created_at=document.created_at,
    )


async def get_document(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID
) -> Document:
    require(ctx.role, Permission.VIEW_DOCUMENTS)
    return await _load(session, ctx, document_id)


async def list_documents(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    doc_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    customer_id: uuid.UUID | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    open_only: bool = False,
    uninvoiced: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[DocumentSummary]:
    require(ctx.role, Permission.VIEW_DOCUMENTS)
    query = select(Document).where(Document.business_id == ctx.business_id)
    if doc_type:
        query = query.where(Document.type == doc_type)
    if status:
        query = query.where(Document.status == status)
    if customer_id:
        query = query.where(Document.customer_id == customer_id)
    if date_from:
        query = query.where(Document.issue_date >= date_from)
    if date_to:
        query = query.where(Document.issue_date <= date_to)
    if open_only:
        # Issued invoices with something left to pay (for receipts and unpaid reports).
        query = query.where(
            Document.status == DocumentStatus.ISSUED,
            Document.type.in_(PAYABLE),
            Document.superseded_by_id.is_(None),
            Document.total - Document.amount_paid - Document.amount_credited > 0,
        )
    if uninvoiced:
        # Issued delivery notes no invoice has billed yet.
        query = query.where(
            Document.status == DocumentStatus.ISSUED,
            Document.type == DocumentType.DELIVERY_NOTE,
            Document.superseded_by_id.is_(None),
        )
    if q:
        text = q.strip()
        condition = Document.customer["name"].astext.ilike(f"%{text.replace('%', '')}%")
        if text.isdigit():
            condition = or_(condition, Document.number == int(text))
        query = query.where(condition)
    query = query.order_by(Document.issue_date.desc(), Document.created_at.desc())
    documents = list(await session.scalars(query.limit(min(limit, 200)).offset(offset)))
    statuses = {d.id: payment_status(d) for d in documents}
    return [
        DocumentSummary(
            id=d.id,
            type=DocumentType(d.type),
            status=DocumentStatus(d.status),
            number=d.number,
            issue_date=d.issue_date,
            customer_name=(d.customer or {}).get("name", ""),
            total=d.total,
            payment_status=statuses[d.id][0],
            balance_due=statuses[d.id][1],
            delivery_status=delivery_status(d),
            created_at=d.created_at,
        )
        for d in documents
    ]


# --- drafts ----------------------------------------------------------------------------


async def create_draft(session: AsyncSession, ctx: BusinessContext, data: DocumentIn) -> Document:
    require(ctx.role, Permission.EDIT_DRAFTS)
    business = await _business(session, ctx)
    if data.type == DocumentType.CREDIT_NOTE:
        raise InvalidDocument(
            "Credit notes are created from the invoice they credit", code="credit_note_from_invoice"
        )
    if data.type not in allowed_types(BusinessType(business.business_type)):
        raise Forbidden(
            "This business type cannot issue this document type", code="document_type_not_allowed"
        )
    document = Document(
        business_id=ctx.business_id,
        type=data.type,
        status=DocumentStatus.DRAFT,
        issue_date=data.issue_date or today(),
        due_date=data.due_date if RULES[data.type].has_due_date else None,
        customer={},
        currency=business.default_currency,
        prices_include_vat=data.prices_include_vat,
        returns_stock=data.returns_stock,
        vat_rate=ZERO,
        notes=data.notes,
        amount_paid=ZERO,
        amount_credited=ZERO,
        source=ctx.principal.channel,
        created_by_user_id=ctx.principal.user_id,
    )
    await _set_customer(session, ctx, document, data.customer_id, data.customer)
    await _set_lines(session, ctx, document, data.lines)
    _set_payments(ctx, document, data.payments)
    await _recalculate(session, business, document)
    session.add(document)
    await session.flush()
    await _set_allocations(session, ctx, document, data.allocations)
    await audit.record(
        session,
        ctx.principal,
        action="document.draft_created",
        entity_type="document",
        entity_id=document.id,
        business_id=ctx.business_id,
        changes={"type": data.type},
    )
    return document


async def update_draft(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID, patch: DocumentPatch
) -> Document:
    require(ctx.role, Permission.EDIT_DRAFTS)
    document = await _load(session, ctx, document_id, lock=True)
    _require_draft(document)
    business = await _business(session, ctx)
    fields = patch.model_fields_set
    if "issue_date" in fields and patch.issue_date is not None:
        document.issue_date = patch.issue_date
    if "due_date" in fields:
        document.due_date = (
            patch.due_date if RULES[DocumentType(document.type)].has_due_date else None
        )
    if "customer_id" in fields or "customer" in fields:
        if patch.customer_id is None and patch.customer is None:
            document.customer_id, document.customer = None, {}
        else:
            await _set_customer(session, ctx, document, patch.customer_id, patch.customer)
    if patch.prices_include_vat is not None:
        document.prices_include_vat = patch.prices_include_vat
    if patch.returns_stock is not None:
        document.returns_stock = patch.returns_stock
    if patch.lines is not None:
        await _set_lines(session, ctx, document, patch.lines)
    if patch.payments is not None:
        _set_payments(ctx, document, patch.payments)
    if patch.allocations is not None:
        await _set_allocations(session, ctx, document, patch.allocations)
    if patch.notes is not None:
        document.notes = patch.notes
    await _recalculate(session, business, document)
    document.updated_at = datetime.now(UTC)
    await session.flush()
    return document


async def delete_draft(session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID) -> None:
    require(ctx.role, Permission.EDIT_DRAFTS)
    document = await _load(session, ctx, document_id, lock=True)
    _require_draft(document)
    await session.delete(document)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="document.draft_deleted",
        entity_type="document",
        entity_id=document_id,
        business_id=ctx.business_id,
        changes={"type": document.type},
    )


async def _new_draft_from(
    session: AsyncSession,
    ctx: BusinessContext,
    sources: list[Document],
    target_type: DocumentType,
    relation: RelationType,
) -> Document:
    """A draft copying the first source's customer and every source's lines, linked to each."""
    first = sources[0]
    source_lines = [line for source in sources for line in source.lines]
    draft = Document(
        business_id=ctx.business_id,
        type=target_type,
        status=DocumentStatus.DRAFT,
        issue_date=today(),
        customer_id=first.customer_id,
        customer=dict(first.customer or {}),
        currency=first.currency,
        prices_include_vat=first.prices_include_vat,
        vat_rate=first.vat_rate if target_type == DocumentType.CREDIT_NOTE else ZERO,
        notes=first.notes if len(sources) == 1 else "",
        amount_paid=ZERO,
        amount_credited=ZERO,
        source=ctx.principal.channel,
        created_by_user_id=ctx.principal.user_id,
        lines=[
            DocumentLine(
                business_id=ctx.business_id,
                position=position,
                item_id=line.item_id,
                description=line.description,
                quantity=line.quantity,
                unit_of_measure=line.unit_of_measure,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                vat_type=line.vat_type,
                line_total=line.line_total,
            )
            for position, line in enumerate(source_lines)
        ],
        payments=[],
    )
    await _recalculate(session, await _business(session, ctx), draft)
    session.add(draft)
    await session.flush()
    for source in sources:
        session.add(
            DocumentRelation(
                business_id=ctx.business_id,
                from_document_id=draft.id,
                to_document_id=source.id,
                relation=relation,
            )
        )
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="document.draft_created",
        entity_type="document",
        entity_id=draft.id,
        business_id=ctx.business_id,
        changes={"type": target_type, relation.value: [str(s.id) for s in sources]},
    )
    return draft


async def convert(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID, target: DocumentType
) -> Document:
    require(ctx.role, Permission.EDIT_DRAFTS)
    source = await _load(session, ctx, document_id)
    if source.status != DocumentStatus.ISSUED:
        raise Conflict("Only issued documents can be converted", code="document_not_issued")
    if target not in CONVERSIONS.get(DocumentType(source.type), frozenset()):
        raise InvalidDocument("This conversion is not supported", code="conversion_not_allowed")
    business = await _business(session, ctx)
    if target not in allowed_types(BusinessType(business.business_type)):
        raise Forbidden(
            "This business type cannot issue this document type", code="document_type_not_allowed"
        )
    if source.type == DocumentType.DELIVERY_NOTE and source.superseded_by_id is not None:
        raise Conflict("This delivery note was already invoiced", code="delivery_note_invoiced")
    return await _new_draft_from(session, ctx, [source], target, RelationType.CONVERTED_FROM)


async def invoice_delivery_notes(
    session: AsyncSession,
    ctx: BusinessContext,
    note_ids: list[uuid.UUID],
    target: DocumentType,
) -> Document:
    """A draft invoice billing several delivery notes of one customer (חשבונית מרכזת)."""
    require(ctx.role, Permission.EDIT_DRAFTS)
    if target not in BILLS_DELIVERY_NOTES:
        raise InvalidDocument("This conversion is not supported", code="conversion_not_allowed")
    business = await _business(session, ctx)
    if target not in allowed_types(BusinessType(business.business_type)):
        raise Forbidden(
            "This business type cannot issue this document type", code="document_type_not_allowed"
        )
    notes = [await _load(session, ctx, note_id) for note_id in dict.fromkeys(note_ids)]
    for note in notes:
        if note.type != DocumentType.DELIVERY_NOTE or note.status != DocumentStatus.ISSUED:
            raise InvalidDocument(
                "Only issued delivery notes can be invoiced", code="not_a_delivery_note"
            )
        if note.superseded_by_id is not None:
            raise Conflict("This delivery note was already invoiced", code="delivery_note_invoiced")
    customers = {(n.customer_id, (n.customer or {}).get("name", "")) for n in notes}
    if len(customers) > 1:
        raise InvalidDocument(
            "The delivery notes are for different customers", code="delivery_notes_customers"
        )
    notes.sort(key=lambda n: (n.issue_date, n.number or 0))
    return await _new_draft_from(session, ctx, notes, target, RelationType.CONVERTED_FROM)


async def create_credit_note(
    session: AsyncSession, ctx: BusinessContext, invoice_id: uuid.UUID
) -> Document:
    require(ctx.role, Permission.EDIT_DRAFTS)
    invoice = await _load(session, ctx, invoice_id)
    if invoice.status != DocumentStatus.ISSUED or invoice.type not in CREDITABLE:
        raise InvalidDocument(
            "Credit notes can only be created for issued tax invoices", code="not_creditable"
        )
    return await _new_draft_from(
        session, ctx, [invoice], DocumentType.CREDIT_NOTE, RelationType.CREDITS
    )


# --- issuing ---------------------------------------------------------------------------


async def _credited_invoice(session: AsyncSession, document: Document) -> Document | None:
    return await session.scalar(
        select(Document)
        .join(DocumentRelation, DocumentRelation.to_document_id == Document.id)
        .where(
            DocumentRelation.from_document_id == document.id,
            DocumentRelation.relation == RelationType.CREDITS,
        )
    )


async def _validate_for_issue(
    session: AsyncSession, business: Business, document: Document
) -> None:
    doc_type = DocumentType(document.type)
    rules = RULES[doc_type]
    if doc_type not in allowed_types(BusinessType(business.business_type)):
        raise Forbidden(
            "This business type cannot issue this document type", code="document_type_not_allowed"
        )
    if rules.is_tax_document and not (business.address_street and business.address_city):
        raise InvalidDocument(
            "The business address must be filled in before issuing tax documents",
            code="business_address_required",
        )
    if not (document.customer or {}).get("name"):
        raise InvalidDocument("Customer name is required", code="customer_name_required")
    if rules.has_lines and not document.lines:
        raise InvalidDocument("At least one line is required", code="lines_required")
    if rules.has_payments and not document.payments:
        raise InvalidDocument("At least one payment is required", code="payments_required")
    # A delivery note may list goods without prices; every other document is about money.
    if document.total <= ZERO and doc_type != DocumentType.DELIVERY_NOTE:
        raise InvalidDocument("The total must be positive", code="total_not_positive")
    if rules.payments_equal_total:
        paid = sum((p.amount for p in document.payments), ZERO)
        if paid != document.total:
            raise InvalidDocument(
                f"Payments ({paid}) must equal the total ({document.total})",
                code="payments_mismatch",
            )
    if document.issue_date > today():
        raise InvalidDocument("The date cannot be in the future", code="issue_date_in_future")
    last_date = await session.scalar(
        select(func.max(Document.issue_date)).where(
            Document.business_id == business.id,
            Document.type == doc_type,
            Document.status == DocumentStatus.ISSUED,
        )
    )
    if last_date and document.issue_date < last_date:
        # Numbers follow dates: a document cannot be dated before the last one of its type.
        raise InvalidDocument(
            f"The date cannot be earlier than the last issued document ({last_date})",
            code="issue_date_before_last",
            last_issue_date=last_date.isoformat(),
        )
    if doc_type == DocumentType.CREDIT_NOTE:
        invoice = await _credited_invoice(session, document)
        if invoice is None:
            raise InvalidDocument("Credit note has no invoice", code="credit_note_from_invoice")
        already = await session.scalar(
            select(func.coalesce(func.sum(Document.total), 0))
            .join(DocumentRelation, DocumentRelation.from_document_id == Document.id)
            .where(
                DocumentRelation.to_document_id == invoice.id,
                DocumentRelation.relation == RelationType.CREDITS,
                Document.status == DocumentStatus.ISSUED,
            )
        )
        if document.total > invoice.total - Decimal(already or 0):
            raise InvalidDocument(
                "The credit exceeds what is left to credit on the invoice",
                code="credit_exceeds_invoice",
                remaining=str(invoice.total - Decimal(already or 0)),
            )


async def _apply_to_invoices(session: AsyncSession, document: Document) -> None:
    """Record what an issued document pays or credits on its invoices (locked rows)."""
    doc_type = DocumentType(document.type)
    if doc_type == DocumentType.TAX_INVOICE_RECEIPT:
        document.amount_paid = document.total
        return
    if doc_type == DocumentType.CREDIT_NOTE:
        credited = await _credited_invoice(session, document)
        if credited is not None:
            invoice = await _lock(session, credited.id)
            invoice.amount_credited += document.total
        return
    if doc_type != DocumentType.RECEIPT:
        return
    allocations = await _allocations(session, document)
    allocated = sum((rel.amount or ZERO for rel, _ in allocations), ZERO)
    if allocated > document.total:
        raise InvalidDocument(
            f"The invoices ({allocated}) exceed the receipt total ({document.total})",
            code="allocations_exceed_receipt",
        )
    for rel, unlocked in allocations:
        invoice = await _lock(session, unlocked.id)
        if (
            document.customer_id
            and invoice.customer_id
            and invoice.customer_id != document.customer_id
        ):
            raise InvalidDocument(
                f"Invoice {invoice.number} belongs to another customer",
                code="allocation_customer_mismatch",
            )
        balance = balance_due(invoice)
        if (rel.amount or ZERO) > balance:
            raise InvalidDocument(
                f"The amount for invoice {invoice.number} exceeds its open balance ({balance})",
                code="allocation_exceeds_balance",
                invoice_number=invoice.number,
                balance=str(balance),
            )
        invoice.amount_paid += rel.amount or ZERO


async def _close_proforma(session: AsyncSession, document: Document) -> None:
    """A tax invoice issued from a proforma replaces it: the proforma is closed, and what was
    already paid on the proforma counts as paid on the invoice."""
    if document.type not in (DocumentType.TAX_INVOICE, DocumentType.TAX_INVOICE_RECEIPT):
        return
    source_id = await session.scalar(
        select(DocumentRelation.to_document_id).where(
            DocumentRelation.from_document_id == document.id,
            DocumentRelation.relation == RelationType.CONVERTED_FROM,
        )
    )
    if source_id is None:
        return
    proforma = await _lock(session, source_id)
    if (
        proforma.type != DocumentType.PROFORMA_INVOICE
        or proforma.status != DocumentStatus.ISSUED
        or proforma.superseded_by_id is not None
    ):
        return
    proforma.superseded_by_id = document.id
    if document.type == DocumentType.TAX_INVOICE:
        document.amount_paid = min(proforma.amount_paid, document.total)


async def _close_delivery_notes(session: AsyncSession, document: Document) -> None:
    """An invoice billing delivery notes marks them invoiced; a note is never billed twice."""
    if document.type not in BILLS_DELIVERY_NOTES:
        return
    note_ids = await session.scalars(
        select(DocumentRelation.to_document_id)
        .join(Document, Document.id == DocumentRelation.to_document_id)
        .where(
            DocumentRelation.from_document_id == document.id,
            DocumentRelation.relation == RelationType.CONVERTED_FROM,
            Document.type == DocumentType.DELIVERY_NOTE,
        )
        .order_by(DocumentRelation.to_document_id)
    )
    for note_id in note_ids.all():
        note = await _lock(session, note_id)
        if note.superseded_by_id is not None:
            raise Conflict(
                f"Delivery note {note.number} was already invoiced",
                code="delivery_note_invoiced",
            )
        note.superseded_by_id = document.id


async def _lock(session: AsyncSession, document_id: uuid.UUID) -> Document:
    # populate_existing: re-read after the lock, so a concurrent receipt's update is not lost.
    invoice = await session.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert invoice is not None
    return invoice


async def references_for(session: AsyncSession, document: Document) -> list[str]:
    lines = []
    for rel in await related(session, document):
        if rel.direction != "outgoing" or rel.number is None:
            continue
        title = RULES[rel.type].title_he
        if rel.relation == RelationType.CREDITS:
            lines.append(f"זיכוי עבור {title} מס׳ {rel.number}")
        elif rel.relation == RelationType.CONVERTED_FROM:
            lines.append(f"בהמשך ל{title} מס׳ {rel.number}")
        elif rel.relation == RelationType.PAYS and rel.amount is not None:
            lines.append(f"תשלום עבור {title} מס׳ {rel.number}: {rel.amount:,.2f}")
    return lines


async def issue(
    session: AsyncSession,
    ctx: BusinessContext,
    document_id: uuid.UUID,
    *,
    without_allocation: bool = False,
) -> Document:
    """Assign the next number, freeze the document, store the original PDF. Irreversible.

    A tax invoice that needs an allocation number gets it before the PDF is made; if the tax
    authority cannot give one, issuing stops unless ``without_allocation`` (then it is retried
    in the background)."""
    require(ctx.role, Permission.ISSUE_DOCUMENTS)
    document = await _load(session, ctx, document_id, lock=True)
    _require_draft(document)
    business = await _business(session, ctx)
    await _recalculate(session, business, document)  # VAT rate for the final issue date
    await _validate_for_issue(session, business, document)
    await _apply_to_invoices(session, document)
    await _close_proforma(session, document)
    await _close_delivery_notes(session, document)

    document.number = await numbering.next_number(
        session, ctx.business_id, DocumentType(document.type)
    )
    document.status = DocumentStatus.ISSUED
    document.business_snapshot = _business_snapshot(business)
    document.issued_at = datetime.now(UTC)
    document.issued_by_user_id = ctx.principal.user_id
    await allocation_numbers.on_issue(
        session, ctx, business, document, allow_without=without_allocation
    )
    await inventory.apply_document(session, ctx, document)

    pdf = await render_pdf(
        document,
        document.business_snapshot,
        "original",
        await references_for(session, document),
        await branding.load_file(session, business.logo_file_id),
    )
    stored = await get_storage().put(f"{ctx.business_id}/documents/{document.id}/original.pdf", pdf)
    file = StoredFile(
        business_id=ctx.business_id,
        storage_key=stored.key,
        content_type="application/pdf",
        size=stored.size,
        sha256=stored.sha256,
    )
    session.add(file)
    await session.flush()
    document.original_pdf_file_id = file.id
    actor = await session.get(User, ctx.principal.user_id)
    events.emit(
        session,
        ctx.business_id,
        "document.issued",
        {
            "document_id": str(document.id),
            "type": document.type,
            "number": document.number,
            "total": str(document.total),
            "customer_id": str(document.customer_id) if document.customer_id else None,
            "customer_name": (document.customer or {}).get("name", ""),
            "actor_user_id": str(ctx.principal.user_id),
            "actor_name": (actor.full_name or actor.email) if actor else "",
            "channel": ctx.principal.channel,
        },
    )
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="document.issued",
        entity_type="document",
        entity_id=document.id,
        business_id=ctx.business_id,
        changes={"type": document.type, "number": document.number, "total": str(document.total)},
    )
    return document


# --- PDF -------------------------------------------------------------------------------


async def pdf(
    session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID
) -> tuple[bytes, str, Variant]:
    """Drafts: preview. Issued: the stored original the first time, then marked copies."""
    require(ctx.role, Permission.VIEW_DOCUMENTS)
    document = await _load(session, ctx, document_id, lock=True)
    name = f"{document.type}-{document.number or 'draft'}.pdf"
    if document.status == DocumentStatus.DRAFT:
        business = await _business(session, ctx)
        content = await render_pdf(
            document,
            _business_snapshot(business),
            "draft",
            await references_for(session, document),
            await branding.load_file(session, business.logo_file_id),
        )
        return content, name, "draft"
    if document.original_delivered_at is None and document.original_pdf_file_id:
        file = await session.get(StoredFile, document.original_pdf_file_id)
        assert file is not None
        content = await get_storage().get(file.storage_key)
        document.original_delivered_at = datetime.now(UTC)
        await session.flush()
        await audit.record(
            session,
            ctx.principal,
            action="document.original_delivered",
            entity_type="document",
            entity_id=document.id,
            business_id=ctx.business_id,
        )
        return content, name, "original"
    assert document.business_snapshot is not None
    # Copies use the logo the document was issued with, not today's logo.
    content = await render_pdf(
        document,
        document.business_snapshot,
        "copy",
        await references_for(session, document),
        await branding.load_file(session, document.business_snapshot.get("logo_file_id")),
    )
    return content, name, "copy"
