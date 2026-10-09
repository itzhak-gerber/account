"""Collects a business's data for the uniform-format file (מבנה אחיד) over a date range.

Documents are taken by their date (the date printed on them), as the specification asks for
software that keeps several years. Quotes have no code in the specification's document table
and are left out; so are drafts. Stock (M100) covers stock-tracked products: the quantity at
the start of the range, what came in and went out during it, and the current average cost.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import openformat as of
from app.core.config import get_settings
from app.models import (
    Business,
    BusinessType,
    Document,
    DocumentRelation,
    DocumentStatus,
    DocumentType,
    GoodsReceipt,
    Item,
    ItemType,
    PaymentMethod,
    PurchaseOrder,
    RelationType,
    StockLevel,
    StockMovement,
    Supplier,
    SupplierInvoice,
    VatType,
)
from app.services.calc import money

# Appendix 1 of the specification.
SALES_CODES = {
    DocumentType.DELIVERY_NOTE: 200,
    DocumentType.PROFORMA_INVOICE: 300,
    DocumentType.TAX_INVOICE: 305,
    DocumentType.TAX_INVOICE_RECEIPT: 320,
    DocumentType.CREDIT_NOTE: 330,
    DocumentType.RECEIPT: 400,
}
PURCHASE_ORDER, GOODS_RECEIPT, SUPPLIER_INVOICE = 500, 600, 700
PAYMENT_CODES = {
    PaymentMethod.CASH: 1,
    PaymentMethod.CHECK: 2,
    PaymentMethod.CREDIT_CARD: 3,
    PaymentMethod.BANK_TRANSFER: 4,
    PaymentMethod.DIGITAL_WALLET: 9,
    PaymentMethod.OTHER: 9,
}
OCCASIONAL_CUSTOMER = "0"  # a customer typed on the document, not in the customer list


def _key(value: uuid.UUID | None) -> str:
    return value.hex[:15].upper() if value else OCCASIONAL_CUSTOMER


def _local(value: datetime | None, zone: ZoneInfo) -> datetime | None:
    return value.astimezone(zone) if value else None


def _customer(document: Document) -> of.Party:
    c: dict[str, Any] = document.customer or {}
    return of.Party(
        key=_key(document.customer_id),
        name=c.get("name", ""),
        street=c.get("address_street", ""),
        city=c.get("address_city", ""),
        zip=c.get("address_zip", ""),
        phone=c.get("phone", ""),
        tax_id=c.get("tax_id", ""),
    )


def _supplier(supplier: Supplier) -> of.Party:
    return of.Party(
        key=_key(supplier.id),
        name=supplier.name,
        street=supplier.address_street,
        city=supplier.address_city,
        zip=supplier.address_zip,
        phone=supplier.phone,
        tax_id=supplier.tax_id,
    )


def _kind(item: Item | None) -> int:
    if item is None:
        return 0
    return 1 if item.item_type == ItemType.SERVICE else 2


async def _bases(
    session: AsyncSession, documents: list[Document]
) -> dict[uuid.UUID, tuple[int, str]]:
    """The one document each document is based on (an invoice on its delivery note, a credit
    note on its invoice), when there is exactly one."""
    if not documents:
        return {}
    rows = await session.execute(
        select(DocumentRelation.from_document_id, Document.type, Document.number)
        .join(Document, Document.id == DocumentRelation.to_document_id)
        .where(
            DocumentRelation.from_document_id.in_([d.id for d in documents]),
            DocumentRelation.relation.in_([RelationType.CONVERTED_FROM, RelationType.CREDITS]),
        )
    )
    found: dict[uuid.UUID, list[tuple[int, str]]] = defaultdict(list)
    for doc_id, doc_type, doc_number in rows.all():
        code = SALES_CODES.get(DocumentType(doc_type))
        if code and doc_number is not None:
            found[doc_id].append((code, str(doc_number)))
    return {doc_id: bases[0] for doc_id, bases in found.items() if len(bases) == 1}


def _sales_line(document: Document, line: Any, items: dict[uuid.UUID, Item]) -> of.Line:
    standard = line.vat_type == VatType.STANDARD
    # Prices typed including VAT are reported before VAT, as the specification asks.
    divisor = 1 + document.vat_rate if document.prices_include_vat and standard else Decimal(1)
    gross = money(line.quantity * line.unit_price / divisor)
    total = money(line.line_total / divisor)
    item = items.get(line.item_id) if line.item_id else None
    return of.Line(
        description=line.description,
        quantity=line.quantity,
        unit_price=money(line.unit_price / divisor),
        discount=gross - total,
        total=total,
        vat_percent=document.vat_rate * 100 if standard else Decimal(0),
        unit=line.unit_of_measure,
        sku=item.sku if item else "",
        kind=_kind(item),
    )


def _payment(payment: Any) -> of.Payment:
    details: dict[str, Any] = payment.details or {}
    installments = details.get("installments") or 1
    return of.Payment(
        method=PAYMENT_CODES.get(PaymentMethod(payment.method), 9),
        amount=payment.amount,
        payment_date=payment.payment_date,
        bank=str(details.get("bank", "")),
        branch=str(details.get("branch", "")),
        account=str(details.get("account", "")),
        cheque=str(details.get("check_number", "")),
        credit_kind=2 if installments > 1 else 1,
    )


async def _sales(
    session: AsyncSession, business_id: uuid.UUID, date_from: date, date_to: date, zone: ZoneInfo
) -> list[of.Doc]:
    documents = list(
        await session.scalars(
            select(Document)
            .where(
                Document.business_id == business_id,
                Document.status == DocumentStatus.ISSUED,
                Document.type.in_(list(SALES_CODES)),
                Document.issue_date >= date_from,
                Document.issue_date <= date_to,
            )
            .options(selectinload(Document.lines), selectinload(Document.payments))
        )
    )
    item_ids = {line.item_id for d in documents for line in d.lines if line.item_id}
    items = (
        {i.id: i for i in await session.scalars(select(Item).where(Item.id.in_(item_ids)))}
        if item_ids
        else {}
    )
    bases = await _bases(session, documents)
    result = []
    for d in documents:
        lines = [_sales_line(d, line, items) for line in d.lines]
        base = bases.get(d.id)
        if base:
            for line in lines:
                line.base_type, line.base_number = base
        result.append(
            of.Doc(
                doc_type=SALES_CODES[DocumentType(d.type)],
                number=str(d.number),
                document_date=d.issue_date,
                produced_at=_local(d.issued_at, zone),
                party=_customer(d),
                net=d.subtotal,
                vat=d.vat_amount,
                total=d.total,
                lines=lines,
                payments=[_payment(p) for p in d.payments],
            )
        )
    return result


def _cost_line(description: str, quantity: Decimal, cost: Decimal, item: Item | None) -> of.Line:
    total = money(quantity * cost)
    return of.Line(
        description=description,
        quantity=quantity,
        unit_price=money(cost),
        discount=Decimal(0),
        total=total,
        vat_percent=Decimal(0),
        unit=item.unit_of_measure if item else "",
        sku=item.sku if item else "",
        kind=_kind(item),
    )


async def _purchasing(
    session: AsyncSession, business_id: uuid.UUID, date_from: date, date_to: date, zone: ZoneInfo
) -> list[of.Doc]:
    orders = list(
        await session.scalars(
            select(PurchaseOrder).where(
                PurchaseOrder.business_id == business_id,
                PurchaseOrder.order_date >= date_from,
                PurchaseOrder.order_date <= date_to,
            )
        )
    )
    receipts = list(
        await session.scalars(
            select(GoodsReceipt).where(
                GoodsReceipt.business_id == business_id,
                GoodsReceipt.receipt_date >= date_from,
                GoodsReceipt.receipt_date <= date_to,
            )
        )
    )
    invoices = list(
        await session.scalars(
            select(SupplierInvoice).where(
                SupplierInvoice.business_id == business_id,
                SupplierInvoice.invoice_date >= date_from,
                SupplierInvoice.invoice_date <= date_to,
            )
        )
    )
    item_ids = {line.item_id for o in orders for line in o.lines if line.item_id} | {
        line.item_id for r in receipts for line in r.lines
    }
    items = (
        {i.id: i for i in await session.scalars(select(Item).where(Item.id.in_(item_ids)))}
        if item_ids
        else {}
    )
    order_numbers = {
        o.id: o.number
        for o in await session.scalars(
            select(PurchaseOrder).where(PurchaseOrder.business_id == business_id)
        )
    }
    result = []
    for o in orders:
        result.append(
            of.Doc(
                doc_type=PURCHASE_ORDER,
                number=str(o.number),
                document_date=o.order_date,
                produced_at=_local(o.created_at, zone),
                party=_supplier(o.supplier),
                net=o.total,
                vat=Decimal(0),
                total=o.total,
                lines=[
                    _cost_line(
                        line.description,
                        line.quantity,
                        line.unit_cost,
                        items.get(line.item_id) if line.item_id else None,
                    )
                    for line in o.lines
                ],
            )
        )
    for r in receipts:
        lines = []
        for line in r.lines:
            row = _cost_line(
                line.description, line.quantity, line.unit_cost, items.get(line.item_id)
            )
            if r.purchase_order_id and line.order_line_id:
                row.base_type = PURCHASE_ORDER
                row.base_number = str(order_numbers.get(r.purchase_order_id, ""))
            lines.append(row)
        result.append(
            of.Doc(
                doc_type=GOODS_RECEIPT,
                number=str(r.number),
                document_date=r.receipt_date,
                produced_at=_local(r.created_at, zone),
                party=_supplier(r.supplier),
                net=r.total,
                vat=Decimal(0),
                total=r.total,
                lines=lines,
            )
        )
    for i in invoices:
        result.append(
            of.Doc(
                doc_type=SUPPLIER_INVOICE,
                number=i.invoice_number,
                document_date=i.invoice_date,
                produced_at=_local(i.created_at, zone),
                party=_supplier(i.supplier),
                net=i.net_amount,
                vat=i.vat_amount,
                total=i.total,
            )
        )
    return result


async def _stock(
    session: AsyncSession, business_id: uuid.UUID, date_from: date, date_to: date, tz: str
) -> list[of.StockItem]:
    products = list(
        await session.scalars(
            select(Item)
            .where(Item.business_id == business_id, Item.track_inventory.is_(True))
            .order_by(Item.name)
        )
    )
    if not products:
        return []
    day = func.date(func.timezone(tz, StockMovement.created_at))
    rows = await session.execute(
        select(
            StockMovement.item_id,
            func.sum(case((day < date_from, StockMovement.quantity), else_=0)),
            func.sum(
                case(
                    (
                        (day >= date_from) & (day <= date_to) & (StockMovement.quantity > 0),
                        StockMovement.quantity,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        (day >= date_from) & (day <= date_to) & (StockMovement.quantity < 0),
                        -StockMovement.quantity,
                    ),
                    else_=0,
                )
            ),
        )
        .where(StockMovement.business_id == business_id)
        .group_by(StockMovement.item_id)
    )
    sums = {item_id: (o, i, out) for item_id, o, i, out in rows.all()}
    costs = {
        level.item_id: level.average_cost
        for level in await session.scalars(
            select(StockLevel).where(StockLevel.business_id == business_id)
        )
    }
    skus = [p.sku for p in products]
    result = []
    for p in products:
        opening, received, issued = sums.get(p.id, (0, 0, 0))
        # The internal catalogue number must be unique in the file.
        sku = p.sku if p.sku and skus.count(p.sku) == 1 else p.id.hex[:20].upper()
        result.append(
            of.StockItem(
                sku=sku,
                name=p.name,
                barcode=p.barcode,
                unit=p.unit_of_measure,
                opening=Decimal(opening or 0),
                received=Decimal(received or 0),
                issued=Decimal(issued or 0),
                cost=costs.get(p.id, Decimal(0)),
            )
        )
    return result


async def first_date(session: AsyncSession, business_id: uuid.UUID) -> date | None:
    """The earliest date of anything the file can hold (sales or purchasing)."""
    firsts = [
        await session.scalar(
            select(func.min(Document.issue_date)).where(
                Document.business_id == business_id, Document.status == DocumentStatus.ISSUED
            )
        ),
        await session.scalar(
            select(func.min(PurchaseOrder.order_date)).where(
                PurchaseOrder.business_id == business_id
            )
        ),
        await session.scalar(
            select(func.min(GoodsReceipt.receipt_date)).where(
                GoodsReceipt.business_id == business_id
            )
        ),
        await session.scalar(
            select(func.min(SupplierInvoice.invoice_date)).where(
                SupplierInvoice.business_id == business_id
            )
        ),
    ]
    return min((d for d in firsts if d is not None), default=None)


async def build(
    session: AsyncSession, business: Business, date_from: date, date_to: date
) -> of.Result:
    settings = get_settings()
    zone = ZoneInfo(settings.timezone)
    documents = await _sales(session, business.id, date_from, date_to, zone)
    documents += await _purchasing(session, business.id, date_from, date_to, zone)
    documents.sort(key=lambda d: (d.document_date, d.doc_type, d.number.zfill(20)))
    return of.build(
        business=of.Business(
            tax_id=business.tax_id,
            name=business.legal_name,
            street=business.address_street,
            city=business.address_city,
            zip=business.address_zip,
            company_number=business.tax_id
            if business.business_type == BusinessType.COMPANY
            else "",
        ),
        software=of.Software(
            name=settings.openformat_software_name,
            version=settings.version,
            registration_number=settings.openformat_registration_number,
            maker_tax_id=settings.openformat_maker_tax_id,
            maker_name=settings.openformat_maker_name,
        ),
        documents=documents,
        stock=await _stock(session, business.id, date_from, date_to, settings.timezone),
        date_from=date_from,
        date_to=date_to,
        now=datetime.now(zone),
    )
