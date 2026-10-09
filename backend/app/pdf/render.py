"""Render documents to PDF (WeasyPrint + Jinja2, Hebrew right-to-left, embedded Heebo font)."""

import base64
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import anyio
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.models import BusinessType, Document, DocumentType, PaymentMethod, VatType
from app.services.document_rules import RULES

Variant = Literal["original", "copy", "draft"]

_HERE = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(_HERE / "templates"), autoescape=select_autoescape(["html"])
)

VARIANT_LABELS = {"original": "מקור", "copy": "העתק נאמן למקור", "draft": "טיוטה – לא בתוקף"}
TAX_ID_LABELS = {
    BusinessType.COMPANY: "ח.פ",
    BusinessType.NONPROFIT: "מס׳ עמותה",
    BusinessType.LICENSED_DEALER: "עוסק מורשה",
    BusinessType.EXEMPT_DEALER: "עוסק פטור",
}
PAYMENT_LABELS = {
    PaymentMethod.CASH: "מזומן",
    PaymentMethod.CHECK: "צ׳ק",
    PaymentMethod.CREDIT_CARD: "כרטיס אשראי",
    PaymentMethod.BANK_TRANSFER: "העברה בנקאית",
    PaymentMethod.DIGITAL_WALLET: "ארנק דיגיטלי",
    PaymentMethod.OTHER: "אחר",
}
DETAIL_LABELS = {
    "bank": "בנק",
    "branch": "סניף",
    "account": "חשבון",
    "check_number": "מס׳ צ׳ק",
    "card_last4": "4 ספרות",
    "installments": "תשלומים",
    "reference": "אסמכתא",
}


def fmt_money(value: Decimal) -> str:
    return f"{value:,.2f}"


def fmt_qty(value: Decimal) -> str:
    return f"{value.normalize():f}" if value == value.to_integral() else f"{value:f}".rstrip("0")


def fmt_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _address(data: dict[str, Any]) -> str:
    parts = [
        data.get("address_street", ""),
        data.get("address_city", ""),
        data.get("address_zip", ""),
    ]
    return ", ".join(p for p in parts if p) or str(data.get("address", ""))


def _context(
    doc: Document,
    business: dict[str, Any],
    variant: Variant,
    references: list[str],
    logo: bytes | None,
) -> dict[str, Any]:
    rules = RULES[DocumentType(doc.type)]
    business_type = BusinessType(business["business_type"])
    shows_vat = rules.shows_vat and doc.vat_rate > 0
    is_receipt = doc.type == DocumentType.RECEIPT
    lines = [
        {
            "description": line.description,
            "quantity": fmt_qty(line.quantity),
            "unit": line.unit_of_measure,
            "unit_price": fmt_money(line.unit_price),
            "discount": f"{line.discount_percent.normalize():f}%" if line.discount_percent else "",
            "total": fmt_money(line.line_total),
            "vat_note": {VatType.EXEMPT: "פטור ממע״מ", VatType.ZERO: "מע״מ בשיעור אפס"}.get(
                VatType(line.vat_type), ""
            )
            if shows_vat
            else "",
        }
        for line in doc.lines
    ]
    payments = [
        {
            "method": PAYMENT_LABELS[PaymentMethod(p.method)],
            "details": ", ".join(
                f"{DETAIL_LABELS.get(k, k)} {v}" for k, v in (p.details or {}).items() if v
            ),
            "date": fmt_date(p.payment_date),
            "amount": fmt_money(p.amount),
        }
        for p in doc.payments
    ]
    total_label = {
        DocumentType.RECEIPT: "סה״כ התקבל",
        DocumentType.TAX_INVOICE_RECEIPT: "סה״כ שולם",
        DocumentType.CREDIT_NOTE: "סה״כ זיכוי",
        DocumentType.QUOTE: "סה״כ",
        DocumentType.DELIVERY_NOTE: "סה״כ",
    }.get(DocumentType(doc.type), "סה״כ לתשלום")
    exempt_note = (
        "העסק פטור מגביית מע״מ"
        if business_type not in (BusinessType.LICENSED_DEALER, BusinessType.COMPANY)
        else ""
    )
    return {
        "fonts": (_HERE / "fonts").resolve().as_uri(),
        "doc": doc,
        "title": rules.title_he,
        "variant": variant,
        "variant_label": VARIANT_LABELS[variant],
        "business": {**business, "address": _address(business)},
        "tax_id_label": TAX_ID_LABELS[business_type],
        "customer": {**doc.customer, "address": _address(doc.customer)},
        "is_receipt": is_receipt,
        "issue_date": fmt_date(doc.issue_date),
        "due_date": fmt_date(doc.due_date),
        "lines": lines,
        "payments": payments,
        "shows_vat": shows_vat,
        "vat_percent": fmt_qty(doc.vat_rate * 100),
        "totals": {
            "subtotal": fmt_money(doc.subtotal),
            "discount": fmt_money(doc.discount_total),
            "vat": fmt_money(doc.vat_amount),
            "total": fmt_money(doc.total),
        },
        "total_label": total_label,
        "exempt_note": exempt_note,
        "references": references,
        # Delivery notes are signed by whoever receives the goods.
        "receiver_signature": DocumentType(doc.type) == DocumentType.DELIVERY_NOTE,
        "logo": f"data:image/png;base64,{base64.b64encode(logo).decode()}" if logo else None,
        "footer": "מסמך ממוחשב · הופק באמצעות מערכת חשבוניות",
    }


def render_html(
    doc: Document,
    business: dict[str, Any],
    variant: Variant,
    references: list[str] | None = None,
    logo: bytes | None = None,
) -> str:
    return _env.get_template("document.html").render(
        **_context(doc, business, variant, references or [], logo)
    )


async def render_pdf(
    doc: Document,
    business: dict[str, Any],
    variant: Variant,
    references: list[str] | None = None,
    logo: bytes | None = None,
) -> bytes:
    html = render_html(doc, business, variant, references, logo)
    # PDF/UA: tagged (headings, tables, language) so screen readers can read the document.
    pdf: bytes = await anyio.to_thread.run_sync(
        lambda: HTML(string=html).write_pdf(pdf_variant="pdf/ua-1")
    )
    return pdf
