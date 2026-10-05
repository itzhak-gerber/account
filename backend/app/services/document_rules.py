"""What each document type is and who may issue it (Israeli rules; confirm with a CPA)."""

from dataclasses import dataclass

from app.models import BusinessType, DocumentType


@dataclass(frozen=True)
class TypeRules:
    title_he: str
    has_lines: bool
    has_payments: bool
    # A tax document (מסמך מס) carries VAT and can only be issued by a VAT-registered business.
    is_tax_document: bool
    shows_vat: bool
    # Payments must add up exactly to the document total.
    payments_equal_total: bool = False
    has_due_date: bool = False


RULES: dict[DocumentType, TypeRules] = {
    DocumentType.QUOTE: TypeRules("הצעת מחיר", True, False, False, True),
    DocumentType.PROFORMA_INVOICE: TypeRules(
        "חשבון עסקה", True, False, False, True, has_due_date=True
    ),
    DocumentType.TAX_INVOICE: TypeRules("חשבונית מס", True, False, True, True, has_due_date=True),
    DocumentType.RECEIPT: TypeRules("קבלה", False, True, False, False),
    DocumentType.TAX_INVOICE_RECEIPT: TypeRules(
        "חשבונית מס/קבלה", True, True, True, True, payments_equal_total=True
    ),
    DocumentType.CREDIT_NOTE: TypeRules("חשבונית מס זיכוי", True, False, True, True),
}

# Businesses registered for VAT (עוסק מורשה, חברה). Exempt dealers and nonprofits charge no VAT
# and cannot issue tax invoices.
VAT_REGISTERED = frozenset({BusinessType.LICENSED_DEALER, BusinessType.COMPANY})

# Which drafts can be created from an issued document of a given type.
CONVERSIONS: dict[DocumentType, frozenset[DocumentType]] = {
    DocumentType.QUOTE: frozenset(
        {
            DocumentType.PROFORMA_INVOICE,
            DocumentType.TAX_INVOICE,
            DocumentType.TAX_INVOICE_RECEIPT,
        }
    ),
    DocumentType.PROFORMA_INVOICE: frozenset(
        {DocumentType.TAX_INVOICE, DocumentType.TAX_INVOICE_RECEIPT}
    ),
}

CREDITABLE = frozenset({DocumentType.TAX_INVOICE, DocumentType.TAX_INVOICE_RECEIPT})


def allowed_types(business_type: BusinessType) -> list[DocumentType]:
    if business_type in VAT_REGISTERED:
        return list(DocumentType)
    return [t for t, r in RULES.items() if not r.is_tax_document]


def charges_vat(business_type: BusinessType, document_type: DocumentType) -> bool:
    return business_type in VAT_REGISTERED and RULES[document_type].shows_vat
