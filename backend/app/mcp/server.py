"""MCP server. Tools are thin adapters over the service layer, exactly like REST routers.

Authentication: OAuth 2.1 bearer tokens from Keycloak (audience ``invoice-api``). Each tool
call resolves the same Principal and BusinessContext as the REST API, so roles, two-factor
rules and row-level security apply identically. Membership management stays web-only.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.files import document_pdf_link
from app.auth.oidc import get_oidc_client
from app.auth.principal import BusinessContext, Principal, enter_business, principal_from_bearer
from app.core.config import get_settings
from app.core.db import commit, get_sessionmaker
from app.core.errors import AppError, NotAuthenticated
from app.models import DocumentStatus, DocumentType, Role, User
from app.schemas.catalog import CustomerIn, CustomerOut, ItemIn, ItemOut
from app.schemas.documents import (
    DeliveryOut,
    DocumentIn,
    DocumentOut,
    DocumentPatch,
    DocumentSummary,
    EmailRequest,
)
from app.schemas.identity import BusinessOut, MemberOut, UserOut
from app.schemas.notifications import NotificationOut
from app.schemas.reports import IncomeReport, OpenBalancesReport, ReceiptsReport, ReportName
from app.services import businesses, catalog, delivery, documents, notifications, reports
from app.services.system import SystemStatus, get_system_status


class KeycloakTokenVerifier:
    """Validates bearer tokens for the MCP endpoint (signature, issuer, audience, expiry)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        settings = get_settings()
        try:
            claims = await get_oidc_client().validate(token, audience=settings.oidc_audience)
        except NotAuthenticated:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("azp", "")),
            scopes=str(claims.get("scope", "")).split(),
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
        )


@asynccontextmanager
async def _principal_session() -> AsyncIterator[tuple[AsyncSession, Principal]]:
    access = get_access_token()
    if access is None:
        raise PermissionError("Not authenticated")
    async with get_sessionmaker()() as session:
        try:
            principal = await principal_from_bearer(
                session, get_oidc_client(), access.token, channel="mcp"
            )
            yield session, principal
            await commit(session)
        except AppError as exc:
            # Business errors (permission, not found, 2FA) are shown to the client as-is.
            raise ToolError(f"{exc.code}: {exc.message}") from exc


@asynccontextmanager
async def _business_session(
    business_id: uuid.UUID,
) -> AsyncIterator[tuple[AsyncSession, BusinessContext]]:
    async with _principal_session() as (session, principal):
        try:
            ctx = await enter_business(session, principal, business_id)
        except AppError as exc:
            raise ToolError(f"{exc.code}: {exc.message}") from exc
        yield session, ctx


class BusinessSummary(BaseModel):
    business: BusinessOut
    role: Role


class WhoAmI(BaseModel):
    user: UserOut
    mfa: bool


def build_mcp_server(*, with_auth: bool = True) -> MCPServer:
    settings = get_settings()
    auth_kwargs: dict[str, object] = {}
    if with_auth:
        auth_kwargs = {
            "token_verifier": KeycloakTokenVerifier(),
            "auth": AuthSettings(
                issuer_url=settings.oidc_issuer,
                resource_server_url=settings.mcp_resource_url,
                validate_token_resource=False,  # the verifier checks the audience itself
            ),
        }
    mcp = MCPServer(
        name="invoice-platform",
        version=settings.version,
        instructions=(
            "Invoice platform for Israeli businesses: customers, items, quotes, invoices, "
            "receipts and credit notes. Every business-scoped tool takes a business_id; call "
            "list_businesses first. Documents are created as drafts; issuing is irreversible."
        ),
        **auth_kwargs,  # type: ignore[arg-type]
    )

    @mcp.tool(name="get_system_status")
    async def get_system_status_tool() -> SystemStatus:
        """Return the platform status (version, environment, database health)."""
        async with get_sessionmaker()() as session:
            return await get_system_status(session)

    @mcp.tool()
    async def whoami() -> WhoAmI:
        """Return the signed-in user and whether they signed in with two-factor authentication."""
        async with _principal_session() as (session, principal):
            user = await session.get(User, principal.user_id)
            return WhoAmI(user=UserOut.model_validate(user), mfa=principal.mfa)

    @mcp.tool()
    async def list_businesses() -> list[BusinessSummary]:
        """List the businesses the signed-in user belongs to, with their role in each."""
        async with _principal_session() as (session, principal):
            rows = await businesses.list_for_user(session, principal)
            return [BusinessSummary(business=BusinessOut.from_business(b), role=r) for b, r in rows]

    @mcp.tool()
    async def get_business(business_id: uuid.UUID) -> BusinessOut:
        """Get a business's details (name, tax ID, type, address, contact)."""
        async with _principal_session() as (session, principal):
            ctx = await enter_business(session, principal, business_id)
            return BusinessOut.from_business(await businesses.get_business(session, ctx))

    @mcp.tool()
    async def list_members(business_id: uuid.UUID) -> list[MemberOut]:
        """List the members of a business and their roles."""
        async with _principal_session() as (session, principal):
            ctx = await enter_business(session, principal, business_id)
            return await businesses.list_members(session, ctx)

    # --- catalog -------------------------------------------------------------------------

    @mcp.tool()
    async def search_customers(
        business_id: uuid.UUID, query: str | None = None, limit: int = 20
    ) -> list[CustomerOut]:
        """Find customers by name, tax ID, email or phone. Omit query to list recent ones."""
        async with _business_session(business_id) as (session, ctx):
            rows = await catalog.list_customers(session, ctx, q=query, limit=min(limit, 100))
            return [CustomerOut.model_validate(c) for c in rows]

    @mcp.tool()
    async def create_customer(business_id: uuid.UUID, customer: CustomerIn) -> CustomerOut:
        """Add a customer. Search first to avoid duplicates."""
        async with _business_session(business_id) as (session, ctx):
            return CustomerOut.model_validate(await catalog.create_customer(session, ctx, customer))

    @mcp.tool()
    async def search_items(
        business_id: uuid.UUID, query: str | None = None, limit: int = 20
    ) -> list[ItemOut]:
        """Find products/services in the catalog by name, SKU, barcode or description."""
        async with _business_session(business_id) as (session, ctx):
            rows = await catalog.list_items(session, ctx, q=query, limit=min(limit, 100))
            return [ItemOut.model_validate(i) for i in rows]

    @mcp.tool()
    async def create_item(business_id: uuid.UUID, item: ItemIn) -> ItemOut:
        """Add a product or service to the catalog (unit_price is before VAT)."""
        async with _business_session(business_id) as (session, ctx):
            return ItemOut.model_validate(await catalog.create_item(session, ctx, item))

    # --- documents -----------------------------------------------------------------------

    @mcp.tool()
    async def search_documents(
        business_id: uuid.UUID,
        type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        query: str | None = None,
        unpaid_only: bool = False,
        limit: int = 20,
    ) -> list[DocumentSummary]:
        """List documents, newest first. query matches the customer name or document number.

        unpaid_only: issued tax invoices/proformas with an open balance (balance_due).
        """
        async with _business_session(business_id) as (session, ctx):
            return await documents.list_documents(
                session,
                ctx,
                doc_type=type,
                status=status,
                q=query,
                open_only=unpaid_only,
                limit=min(limit, 100),
            )

    @mcp.tool()
    async def get_document(business_id: uuid.UUID, document_id: uuid.UUID) -> DocumentOut:
        """Get a document with its lines, payments, VAT and totals."""
        async with _business_session(business_id) as (session, ctx):
            doc = await documents.get_document(session, ctx, document_id)
            return await documents.to_out(session, doc)

    @mcp.tool()
    async def create_document_draft(business_id: uuid.UUID, document: DocumentIn) -> DocumentOut:
        """Create a DRAFT quote, proforma, tax invoice, receipt or tax invoice-receipt.

        Prices are before VAT unless prices_include_vat is true; VAT and totals are computed.
        Receipts have payments instead of lines, and can list the invoices they pay in
        allocations (find them with search_documents unpaid_only=true).
        Drafts have no number and are not valid
        documents until issued with issue_document. Credit notes: use create_credit_note.
        """
        async with _business_session(business_id) as (session, ctx):
            doc = await documents.create_draft(session, ctx, document)
            return await documents.to_out(session, doc)

    @mcp.tool()
    async def update_document_draft(
        business_id: uuid.UUID, document_id: uuid.UUID, changes: DocumentPatch
    ) -> DocumentOut:
        """Change a draft. Lists (lines, payments) given here replace the existing ones."""
        async with _business_session(business_id) as (session, ctx):
            doc = await documents.update_draft(session, ctx, document_id, changes)
            return await documents.to_out(session, doc)

    @mcp.tool()
    async def issue_document(
        business_id: uuid.UUID, document_id: uuid.UUID, confirm: bool = False
    ) -> DocumentOut:
        """Issue a draft: assigns the next number and makes it a legal document. IRREVERSIBLE.

        Show the user the customer, lines and total first, and only call this with
        confirm=true after they explicitly approve. Mistakes are fixed with a credit note.
        """
        if not confirm:
            raise ToolError(
                "confirmation_required: show the draft to the user and call again with "
                "confirm=true once they approve. Issuing cannot be undone."
            )
        async with _business_session(business_id) as (session, ctx):
            doc = await documents.issue(session, ctx, document_id)
            return await documents.to_out(session, doc)

    @mcp.tool()
    async def create_credit_note(business_id: uuid.UUID, invoice_id: uuid.UUID) -> DocumentOut:
        """Create a DRAFT credit note for an issued tax invoice (lines copied; edit, then issue)."""
        async with _business_session(business_id) as (session, ctx):
            doc = await documents.create_credit_note(session, ctx, invoice_id)
            return await documents.to_out(session, doc)

    @mcp.tool()
    async def convert_document(
        business_id: uuid.UUID, document_id: uuid.UUID, target_type: DocumentType
    ) -> DocumentOut:
        """Create a DRAFT from an issued quote/proforma (e.g. quote → tax_invoice)."""
        async with _business_session(business_id) as (session, ctx):
            doc = await documents.convert(session, ctx, document_id, target_type)
            return await documents.to_out(session, doc)

    @mcp.tool()
    async def get_document_pdf_link(business_id: uuid.UUID, document_id: uuid.UUID) -> str:
        """Return a link to the document's PDF, valid for 10 minutes."""
        async with _business_session(business_id) as (session, ctx):
            await documents.get_document(session, ctx, document_id)
            return document_pdf_link(
                ctx.principal, business_id, document_id, get_settings().public_url
            )

    @mcp.tool()
    async def send_document_email(
        business_id: uuid.UUID,
        document_id: uuid.UUID,
        to: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
        confirm: bool = False,
    ) -> DeliveryOut:
        """Email an issued document (PDF attached) to the customer. Sends a real email.

        Omitted fields use the defaults (customer's email, standard Hebrew subject/message).
        Show the user the recipients and text first; call with confirm=true once approved.
        """
        async with _business_session(business_id) as (session, ctx):
            defaults = await delivery.defaults(session, ctx, document_id)
            request = EmailRequest(
                to=to or defaults.to,
                subject=subject or defaults.subject,
                message=message if message is not None else defaults.message,
            )
            if not confirm:
                raise ToolError(
                    "confirmation_required: will send to "
                    f"{', '.join(map(str, request.to))} with subject '{request.subject}'. "
                    "Call again with confirm=true once the user approves."
                )
            return DeliveryOut.model_validate(
                await delivery.send(session, ctx, document_id, request)
            )

    # --- reports -------------------------------------------------------------------------

    @mcp.tool()
    async def get_report(
        business_id: uuid.UUID,
        report: ReportName,
        date_from: date | None = None,
        date_to: date | None = None,
        include_documents: bool = False,
    ) -> IncomeReport | ReceiptsReport | OpenBalancesReport:
        """Business reports. Amounts in ILS; issued documents only.

        income: tax invoices, invoice-receipts and credit notes (negative) by issue date, per
          month, split as the VAT return asks (taxable, zero-rated, exempt, VAT).
        receipts: money received (receipts and invoice-receipts) per month and payment method.
        open_balances: what customers owe now, per customer, with aging (days past due).
        The period defaults to this month; open_balances ignores it. Set include_documents to
        list the individual documents too.
        """
        async with _business_session(business_id) as (session, ctx):
            now = documents.today()
            start, end = date_from or reports.month_start(now), date_to or now
            result: IncomeReport | ReceiptsReport | OpenBalancesReport
            if report == "income":
                result = await reports.income(session, ctx, start, end)
            elif report == "receipts":
                result = await reports.receipts(session, ctx, start, end)
            else:
                result = await reports.open_balances(session, ctx)
            if not include_documents:
                result.documents = []
            return result

    # --- notifications -------------------------------------------------------------------

    @mcp.tool()
    async def list_notifications(
        business_id: uuid.UUID, unread_only: bool = True, limit: int = 20
    ) -> list[NotificationOut]:
        """The user's notifications in this business (payments received, overdue invoices,
        failed emails, new members, documents issued by others), newest first."""
        async with _business_session(business_id) as (session, ctx):
            return await notifications.list_notifications(
                session, ctx, unread_only=unread_only, limit=min(limit, 100)
            )

    @mcp.tool()
    async def mark_notifications_read(
        business_id: uuid.UUID, notification_ids: list[uuid.UUID] | None = None
    ) -> int:
        """Mark notifications as read: the given ids, or all of them when none are given.
        Returns how many unread notifications are left."""
        async with _business_session(business_id) as (session, ctx):
            await notifications.mark_read(session, ctx, notification_ids)
            await commit(session)
            return await notifications.unread_count(session, ctx)

    return mcp
