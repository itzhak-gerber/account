"""Allocation numbers (מספרי הקצאה) from the Israel Tax Authority, "חשבוניות ישראל".

A tax invoice or tax invoice/receipt to a customer with a VAT number needs one when its amount
before VAT is above the threshold in force on the invoice date. The number is requested while
issuing, so it is printed on the original. If the tax authority cannot be reached, the user may
issue without it; the request is then retried in the background and the number is added to the
document (and its copies) when it arrives.

Everything here is off unless APP_ITA_ALLOCATION_ENABLED is true and the software's credentials
are configured (see Settings.ita_configured).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext, Principal
from app.core import signing
from app.core.config import get_settings
from app.core.db import after_commit
from app.core.errors import AppError, Forbidden
from app.jobs import queue
from app.models import (
    AllocationRequest,
    AllocationStatus,
    Business,
    Document,
    DocumentType,
    ItaConnection,
    Item,
)
from app.services import audit, ita_client
from app.services.permissions import Permission, require
from app.services.uniform_format import net_line

log = structlog.get_logger()

# Amount before VAT above which an allocation number is needed, by invoice date. The tax
# authority lowers it over time; check the current schedule before relying on it.
THRESHOLDS: list[tuple[date, Decimal]] = [
    (date(2024, 5, 5), Decimal("25000")),
    (date(2025, 1, 1), Decimal("20000")),
    (date(2026, 1, 1), Decimal("10000")),
    (date(2026, 6, 1), Decimal("5000")),
]
APPLIES_TO = frozenset({DocumentType.TAX_INVOICE, DocumentType.TAX_INVOICE_RECEIPT})
TYPE_CODES = {DocumentType.TAX_INVOICE: 305, DocumentType.TAX_INVOICE_RECEIPT: 320}
STATE_PURPOSE = "ita-connect"


class NotConnected(ita_client.ItaRefused):
    """The business has not connected to the tax authority yet."""


class AllocationNeeded(AppError):
    """Issuing stopped: the number is needed and could not be obtained."""

    status_code = 409
    code = "allocation_failed"


def threshold(on: date) -> Decimal | None:
    current = None
    for since, amount in THRESHOLDS:
        if on >= since:
            current = amount
    return current


def required(document: Document) -> bool:
    if document.type not in APPLIES_TO:
        return False
    if not (document.customer or {}).get("tax_id"):
        return False  # a private customer: no allocation number
    limit = threshold(document.issue_date)
    return limit is not None and document.subtotal > limit


# --- tokens -----------------------------------------------------------------------------


def _fernet() -> Fernet:
    return Fernet(get_settings().ita_token_key.encode())


def _seal(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _open(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AppError("Reconnect to the tax authority", code="ita_reconnect") from exc


def redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/api/v1/ita/callback"


def _require_configured() -> None:
    if not get_settings().ita_configured:
        raise AppError(
            "Allocation numbers are not set up on this server", code="ita_not_configured"
        )


async def status(session: AsyncSession, ctx: BusinessContext) -> dict[str, Any]:
    require(ctx.role, Permission.VIEW_BUSINESS)
    settings = get_settings()
    connection = await session.get(ItaConnection, ctx.business_id)
    return {
        "enabled": settings.ita_configured,
        "environment": settings.ita_environment,
        "connected": connection is not None,
        "connected_at": connection.connected_at if connection else None,
        "expires_at": connection.refresh_expires_at if connection else None,
        "threshold": threshold(datetime.now(UTC).date()),
        "redirect_uri": redirect_uri(),
    }


def connect_url(ctx: BusinessContext) -> str:
    """Where to send the owner to approve this software at the tax authority."""
    require(ctx.role, Permission.MANAGE_BUSINESS)
    _require_configured()
    state = signing.sign(
        {"b": str(ctx.business_id), "u": str(ctx.principal.user_id)},
        purpose=STATE_PURPOSE,
        ttl_seconds=900,
    )
    return ita_client.authorize_url(state, redirect_uri())


def business_from_state(state: str, principal: Principal) -> uuid.UUID:
    payload = signing.verify(state, purpose=STATE_PURPOSE)
    if payload.get("u") != str(principal.user_id):
        raise Forbidden("This approval was started by someone else", code="invalid_link")
    return uuid.UUID(payload["b"])


async def finish_connect(session: AsyncSession, ctx: BusinessContext, code: str) -> None:
    require(ctx.role, Permission.MANAGE_BUSINESS)
    _require_configured()
    try:
        tokens = await ita_client.exchange_code(code, redirect_uri())
    except (ita_client.ItaUnavailable, ita_client.ItaRefused) as exc:
        raise AppError(
            f"The tax authority did not connect: {exc}", code="ita_connect_failed"
        ) from exc
    connection = await session.get(ItaConnection, ctx.business_id)
    if connection is None:
        connection = ItaConnection(business_id=ctx.business_id)
        session.add(connection)
    connection.environment = get_settings().ita_environment
    connection.access_token = _seal(tokens.access_token)
    connection.refresh_token = _seal(tokens.refresh_token)
    connection.access_expires_at = tokens.access_expires_at
    connection.refresh_expires_at = tokens.refresh_expires_at
    connection.connected_by_user_id = ctx.principal.user_id
    connection.connected_at = datetime.now(UTC)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="ita.connected",
        entity_type="business",
        entity_id=ctx.business_id,
        business_id=ctx.business_id,
        changes={"environment": connection.environment},
    )


async def disconnect(session: AsyncSession, ctx: BusinessContext) -> None:
    require(ctx.role, Permission.MANAGE_BUSINESS)
    connection = await session.get(ItaConnection, ctx.business_id)
    if connection is not None:
        await session.delete(connection)
        await session.flush()
        await audit.record(
            session,
            ctx.principal,
            action="ita.disconnected",
            entity_type="business",
            entity_id=ctx.business_id,
            business_id=ctx.business_id,
        )


async def _access_token(session: AsyncSession, business_id: uuid.UUID) -> str:
    connection = await session.scalar(
        select(ItaConnection)
        .where(ItaConnection.business_id == business_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connection is None:
        raise NotConnected("The business is not connected to the tax authority")
    if connection.access_expires_at > datetime.now(UTC):
        return _open(connection.access_token)
    tokens = await ita_client.refresh(_open(connection.refresh_token))
    connection.access_token = _seal(tokens.access_token)
    connection.refresh_token = _seal(tokens.refresh_token)
    connection.access_expires_at = tokens.access_expires_at
    if tokens.refresh_expires_at:
        connection.refresh_expires_at = tokens.refresh_expires_at
    await session.flush()
    return tokens.access_token


# --- the request --------------------------------------------------------------------------


def invoice_body(
    document: Document, business: Business, items: dict[uuid.UUID, Item]
) -> dict[str, Any]:
    """The invoice as the tax authority's Approval call expects it (amounts before VAT)."""
    customer: dict[str, Any] = document.customer or {}
    lines = [net_line(document, line, items) for line in document.lines]
    vat_rate = document.vat_rate
    return {
        "Invoice_ID": str(document.number),
        "Invoice_Type": TYPE_CODES[DocumentType(document.type)],
        "Vat_Number": int(business.tax_id),
        "Union_Vat_Number": 0,
        "Invoice_Reference_Number": str(document.number),
        "Customer_VAT_Number": int(customer.get("tax_id") or 0),
        "Customer_Name": customer.get("name", ""),
        "Invoice_Date": document.issue_date.isoformat(),
        "Invoice_Issuance_Date": datetime.now(UTC).date().isoformat(),
        "Branch_ID": "",
        "Accounting_Software_Number": int(get_settings().openformat_registration_number or 0),
        "Client_Software_Key": "",
        "Amount_Before_Discount": float(document.subtotal + document.discount_total),
        "Discount": float(document.discount_total),
        "Payment_Amount": float(document.subtotal),
        "VAT_Amount": float(document.vat_amount),
        "Payment_Amount_Including_VAT": float(document.total),
        "Invoice_Note": "",
        "Action": 0,
        "Items": [
            {
                "Index": index,
                "Catalog_ID": line.sku,
                "Category": 0,
                "Description": line.description[:250],
                "Measure_Unit_Description": line.unit or "יחידה",
                "Quantity": float(line.quantity),
                "Price_Per_Unit": float(line.unit_price),
                "Discount": float(line.discount),
                "Total_Amount": float(line.total),
                "VAT_Rate": float(vat_rate * 100 if line.vat_percent else 0),
                "VAT_Amount": float((line.total * vat_rate).quantize(Decimal("0.01")))
                if line.vat_percent
                else 0.0,
            }
            for index, line in enumerate(lines, start=1)
        ],
    }


async def _items(session: AsyncSession, document: Document) -> dict[uuid.UUID, Item]:
    ids = {line.item_id for line in document.lines if line.item_id}
    if not ids:
        return {}
    return {i.id: i for i in await session.scalars(select(Item).where(Item.id.in_(ids)))}


async def _ask(
    session: AsyncSession, business: Business, document: Document, request: AllocationRequest
) -> str:
    """One call to the tax authority; records the outcome on the request."""
    try:
        token = await _access_token(session, business.id)
        number, response = await ita_client.approval(token, request.request_body)
    except ita_client.ItaRefused as exc:
        request.status = AllocationStatus.REJECTED
        request.error = str(exc)[:500]
        request.response_body = exc.response
        raise
    except ita_client.ItaUnavailable as exc:
        request.status = AllocationStatus.PENDING
        request.error = str(exc)[:500]
        raise
    request.status = AllocationStatus.APPROVED
    request.allocation_number = number[:20]
    request.response_body = response
    request.error = None
    document.allocation_number = number[:20]
    return number


async def on_issue(
    session: AsyncSession,
    ctx: BusinessContext,
    business: Business,
    document: Document,
    *,
    allow_without: bool,
) -> None:
    """Called while issuing, after the number is assigned and before the PDF is rendered."""
    if not get_settings().ita_configured or not required(document):
        return
    request = AllocationRequest(
        id=uuid.uuid4(),
        business_id=ctx.business_id,
        document_id=document.id,
        status=AllocationStatus.PENDING,
        attempts=1,
        request_body=invoice_body(document, business, await _items(session, document)),
    )
    session.add(request)
    try:
        await _ask(session, business, document, request)
        log.info("ita.allocated", document_id=str(document.id))
        return
    except (ita_client.ItaUnavailable, ita_client.ItaRefused) as exc:
        unavailable = isinstance(exc, ita_client.ItaUnavailable)
        log.warning("ita.not_allocated", document_id=str(document.id), error=str(exc)[:200])
        if not allow_without:
            raise AllocationNeeded(
                f"No allocation number: {exc}",
                code="allocation_failed"
                if unavailable
                else "ita_not_connected"
                if isinstance(exc, NotConnected)
                else "allocation_rejected",
            ) from exc
    await session.flush()
    if request.status != AllocationStatus.PENDING:
        return  # refused: asking again only helps after something changes ("ask again")
    business_id, document_id = str(ctx.business_id), str(document.id)

    async def retry_later() -> None:
        await queue.enqueue("retry_allocation", business_id=business_id, document_id=document_id)

    after_commit(session, retry_later)


async def retry(session: AsyncSession, business_id: uuid.UUID, document_id: uuid.UUID) -> str:
    """Ask again for a document issued without its number (worker, or the retry button)."""
    document = await session.get(Document, document_id)
    if document is None or document.business_id != business_id or document.allocation_number:
        return "done"
    request = await session.scalar(
        select(AllocationRequest)
        .where(AllocationRequest.document_id == document_id)
        .order_by(AllocationRequest.created_at.desc())
        .limit(1)
    )
    business = await session.get(Business, business_id)
    if request is None or business is None:
        return "done"
    request.attempts += 1
    try:
        await _ask(session, business, document, request)
    except ita_client.ItaUnavailable:
        await session.flush()
        return "pending"
    except ita_client.ItaRefused:
        await session.flush()
        return "rejected"
    await session.flush()
    return "approved"


async def retry_now(session: AsyncSession, ctx: BusinessContext, document_id: uuid.UUID) -> str:
    require(ctx.role, Permission.ISSUE_DOCUMENTS)
    _require_configured()
    return await retry(session, ctx.business_id, document_id)


async def latest_status(session: AsyncSession, document: Document) -> AllocationStatus | None:
    if document.allocation_number:
        return AllocationStatus.APPROVED
    if document.type not in APPLIES_TO:
        return None
    found: AllocationStatus | None = await session.scalar(
        select(AllocationRequest.status)
        .where(AllocationRequest.document_id == document.id)
        .order_by(AllocationRequest.created_at.desc())
        .limit(1)
    )
    return found
