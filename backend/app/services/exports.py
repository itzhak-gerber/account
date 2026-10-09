"""Full export of a business's data: a ZIP with a PDF copy of every issued document, one
spreadsheet with documents, lines, payments, customers and items, and a short explanation.

The business is the one legally required to keep its records (usually seven years); this lets
it take everything with it at any time, or when the service ends. Built in the background
(it renders a PDF per document) and kept for download for seven days.
"""

import io
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.principal import BusinessContext
from app.core.config import get_settings
from app.core.db import after_commit
from app.core.errors import AppError, Conflict, NotFound
from app.core.storage import get_storage
from app.jobs import queue
from app.models import (
    Business,
    Customer,
    DataExport,
    Document,
    DocumentStatus,
    ExportStatus,
    Item,
    Supplier,
    SupplierInvoice,
)
from app.pdf.render import PAYMENT_LABELS, render_pdf
from app.reports.excel import export_xlsx
from app.services import audit, branding, uniform_format
from app.services import inventory as inventory_service
from app.services.document_rules import RULES
from app.services.documents import references_for
from app.services.permissions import Permission, require

KEEP_FOR = timedelta(days=7)
VAT_LABELS = {"standard": "חייב", "exempt": "פטור", "zero": "אפס"}
ITEM_TYPES = {"service": "שירות", "product": "מוצר", "kit": "ערכה"}


def _out(export: DataExport) -> dict[str, Any]:
    expires = export.finished_at + KEEP_FOR if export.finished_at else None
    return {
        "id": export.id,
        "status": export.status,
        "created_at": export.created_at,
        "finished_at": export.finished_at,
        "expires_at": expires,
        "size": export.size,
        "documents": export.documents,
        "date_from": export.date_from,
        "date_to": export.date_to,
        "downloadable": export.status == ExportStatus.READY
        and expires is not None
        and expires > datetime.now(UTC),
    }


async def request(
    session: AsyncSession,
    ctx: BusinessContext,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Start an export. The date range applies to the uniform-format file; the PDFs and the
    workbook always hold everything."""
    require(ctx.role, Permission.EXPORT_DATA)
    if date_from and date_to and date_from > date_to:
        raise AppError("The range ends before it starts", code="invalid_date_range")
    running = await session.scalar(
        select(DataExport.id).where(
            DataExport.business_id == ctx.business_id,
            DataExport.status == ExportStatus.PENDING,
            DataExport.created_at > datetime.now(UTC) - timedelta(hours=1),
        )
    )
    if running:
        raise Conflict("An export is already being prepared", code="export_in_progress")
    export = DataExport(
        id=uuid.uuid4(),
        business_id=ctx.business_id,
        requested_by_user_id=ctx.principal.user_id,
        status=ExportStatus.PENDING,
        date_from=date_from,
        date_to=date_to,
        created_at=datetime.now(UTC),
    )
    session.add(export)
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="data.export_requested",
        entity_type="data_export",
        entity_id=export.id,
        business_id=ctx.business_id,
    )

    async def start() -> None:
        await queue.enqueue(
            "build_export", export_id=str(export.id), business_id=str(ctx.business_id)
        )

    after_commit(session, start)
    return _out(export)


async def list_exports(session: AsyncSession, ctx: BusinessContext) -> list[dict[str, Any]]:
    require(ctx.role, Permission.EXPORT_DATA)
    rows = await session.scalars(
        select(DataExport)
        .where(DataExport.business_id == ctx.business_id)
        .order_by(DataExport.created_at.desc())
        .limit(10)
    )
    return [_out(e) for e in rows]


async def download(
    session: AsyncSession, ctx: BusinessContext, export_id: uuid.UUID
) -> tuple[bytes, str]:
    require(ctx.role, Permission.EXPORT_DATA)
    export = await session.get(DataExport, export_id)
    if export is None or export.business_id != ctx.business_id:
        raise NotFound("Export not found", code="export_not_found")
    if not _out(export)["downloadable"] or not export.storage_key:
        raise Conflict("This export is not available", code="export_not_available")
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    await audit.record(
        session,
        ctx.principal,
        action="data.export_downloaded",
        entity_type="data_export",
        entity_id=export.id,
        business_id=ctx.business_id,
    )
    name = f"export-{business.tax_id}-{export.created_at:%Y%m%d}.zip"
    return await get_storage().get(export.storage_key), name


def _file_name(document: Document) -> str:
    return f"documents/{document.issue_date:%Y}/{document.type}-{document.number:06d}.pdf"


README = """ייצוא נתונים – {name} (מספר עוסק {tax_id})
הופק בתאריך {when}

תוכן הקובץ:
- documents/: עותק PDF של כל מסמך שהופק ({count} מסמכים), מסודר לפי שנה. העותקים מסומנים
  "העתק נאמן למקור"; קובץ המקור של כל מסמך נשמר במערכת.
- data.xlsx: גיליונות של המסמכים, שורות המסמכים, אמצעי התשלום, הלקוחות והפריטים (וגם מלאי,
  ספקים וחשבוניות ספקים, אם יש).
- {openformat}: קבצים במבנה אחיד של רשות המסים (גרסה 1.31) לתקופה {period}:
  INI.TXT, ו-BKMVDATA.zip שבתוכו BKMVDATA.TXT, וגם OPENFRMT_REPORT.txt – דוח ההפקה.
  אלה הקבצים שמוסרים לביקורת של רשות המסים כשהיא מבקשת אותם.

על פי הוראות ניהול פנקסי חשבונות יש לשמור את רשומות העסק לתקופה הקבועה בדין (בדרך כלל
שבע שנים). מומלץ לשמור את הקובץ הזה במקום בטוח, עם גיבוי.
"""


async def build(session: AsyncSession, export_id: uuid.UUID) -> DataExport:
    """Runs in the worker, inside the business's security context."""
    export = await session.get(DataExport, export_id)
    assert export is not None
    business = await session.get(Business, export.business_id)
    assert business is not None
    documents = list(
        await session.scalars(
            select(Document)
            .where(Document.business_id == business.id, Document.status == DocumentStatus.ISSUED)
            .options(selectinload(Document.lines), selectinload(Document.payments))
            .order_by(Document.issue_date, Document.type, Document.number)
        )
    )
    customers = list(
        await session.scalars(
            select(Customer).where(Customer.business_id == business.id).order_by(Customer.name)
        )
    )
    items = list(
        await session.scalars(
            select(Item).where(Item.business_id == business.id).order_by(Item.name)
        )
    )

    stock_rows = await inventory_service.stock_rows(session, business.id)
    suppliers = list(
        await session.scalars(
            select(Supplier).where(Supplier.business_id == business.id).order_by(Supplier.name)
        )
    )
    supplier_invoices = list(
        await session.scalars(
            select(SupplierInvoice)
            .where(SupplierInvoice.business_id == business.id)
            .order_by(SupplierInvoice.invoice_date)
        )
    )

    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    period_from = export.date_from or await uniform_format.first_date(session, business.id) or today
    period_to = export.date_to or today
    uniform = await uniform_format.build(session, business, period_from, period_to)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{uniform.folder}/INI.TXT", uniform.ini)
        archive.writestr(f"{uniform.folder}/BKMVDATA.zip", uniform.bkmvdata_zip)
        archive.writestr(f"{uniform.folder}/OPENFRMT_REPORT.txt", uniform.report)
        logos: dict[str, bytes | None] = {}
        for document in documents:
            assert document.business_snapshot is not None
            logo_id = str(document.business_snapshot.get("logo_file_id") or "")
            if logo_id not in logos:
                logos[logo_id] = await branding.load_file(session, logo_id or None)
            pdf = await render_pdf(
                document,
                document.business_snapshot,
                "copy",
                await references_for(session, document),
                logos[logo_id],
            )
            archive.writestr(_file_name(document), pdf)

        def title(d: Document) -> str:
            return RULES[d.type].title_he

        archive.writestr(
            "data.xlsx",
            export_xlsx(
                business.display_name,
                customers=[
                    [
                        c.name,
                        c.tax_id,
                        c.email,
                        c.phone,
                        c.address_street,
                        c.address_city,
                        c.address_zip,
                        c.notes,
                        "כן" if c.is_archived else "",
                    ]
                    for c in customers
                ],
                items=[
                    [
                        i.name,
                        i.description,
                        ITEM_TYPES.get(i.item_type, i.item_type),
                        i.sku,
                        i.barcode,
                        i.unit_of_measure,
                        i.unit_price,
                        VAT_LABELS.get(i.vat_type, i.vat_type),
                        "כן" if i.is_archived else "",
                    ]
                    for i in items
                ],
                documents=[
                    [
                        title(d),
                        d.number,
                        d.issue_date,
                        d.customer.get("name", ""),
                        d.customer.get("tax_id", ""),
                        d.subtotal,
                        d.vat_amount,
                        d.total,
                        d.amount_paid,
                        d.amount_credited,
                        d.allocation_number or "",
                        d.notes,
                    ]
                    for d in documents
                ],
                lines=[
                    [
                        title(d),
                        d.number,
                        line.position,
                        line.description,
                        line.quantity,
                        line.unit_of_measure,
                        line.unit_price,
                        line.discount_percent,
                        VAT_LABELS.get(line.vat_type, line.vat_type),
                        line.line_total,
                    ]
                    for d in documents
                    for line in d.lines
                ],
                payments=[
                    [
                        title(d),
                        d.number,
                        PAYMENT_LABELS.get(p.method, p.method),
                        p.payment_date,
                        p.amount,
                        ", ".join(f"{k}: {v}" for k, v in (p.details or {}).items()),
                    ]
                    for d in documents
                    for p in d.payments
                ],
                stock=[
                    [r.item.name, r.item.sku, r.quantity, r.average_cost, r.value, r.item.min_stock]
                    for r in stock_rows
                ],
                suppliers=[
                    [
                        s.name,
                        s.tax_id,
                        s.contact_name,
                        s.phone,
                        s.email,
                        s.address_city,
                        "כן" if s.is_archived else "",
                    ]
                    for s in suppliers
                ],
                supplier_invoices=[
                    [
                        i.supplier.name,
                        i.invoice_number,
                        i.invoice_date,
                        i.due_date,
                        i.net_amount,
                        i.vat_amount,
                        i.total,
                        i.paid_date or "",
                    ]
                    for i in supplier_invoices
                ],
            ),
        )
        archive.writestr(
            "README.txt",
            README.format(
                name=business.legal_name,
                tax_id=business.tax_id,
                when=datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC"),
                count=len(documents),
                openformat=uniform.folder + "/",
                period=f"{period_from:%d/%m/%Y}–{period_to:%d/%m/%Y}",
            ),
        )

    content = buffer.getvalue()
    stored = await get_storage().put(f"{business.id}/exports/{export.id}.zip", content)
    export.storage_key = stored.key
    export.size = len(content)
    export.documents = len(documents)
    export.status = ExportStatus.READY
    export.finished_at = datetime.now(UTC)
    return export
