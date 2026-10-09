"""The tax authority's uniform format (מבנה אחיד, OPENFRMT), version 1.31.

Two fixed-width text files in ISO-8859-8 (logical Hebrew), each record ending in CR LF:

- INI.TXT: one A000 record about the business and this run, then one summary record per
  record type present in BKMVDATA.TXT.
- BKMVDATA.TXT (delivered zipped as BKMVDATA.zip): A100 opening record, C100 document headers,
  D110 document lines, D120 receipt payment lines, M100 stock items, Z900 closing record.

This module only formats; the caller collects the data (see services/exports.py). Every record
is checked against the length the specification gives, so a wrong field width fails loudly.
Bookkeeping records (B100, B110) do not apply: the software is not a double-entry ledger.
"""

import io
import secrets
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

SYSTEM_CONSTANT = "&OF1.31&"
ENCODING = "iso8859_8"
RECORD_LENGTHS = {
    "A000": 466,
    "A100": 95,
    "C100": 444,
    "D110": 339,
    "D120": 222,
    "M100": 298,
    "Z900": 110,
}
SUMMARY_LENGTH = 19
# Appendix 1: document types.
DOC_TYPE_NAMES = {
    200: "תעודת משלוח",
    300: "חשבונית / חשבון עסקה",
    305: "חשבונית מס",
    320: "חשבונית מס / קבלה",
    330: "חשבונית מס זיכוי",
    400: "קבלה",
    500: "הזמנת רכש",
    600: "תעודת משלוח רכש",
    700: "חשבונית מס רכש",
}
# Characters that ISO-8859-8 lacks, written the way Hebrew is typed on a keyboard.
_REPLACE = {"״": '"', "׳": "'", "–": "-", "—": "-", "₪": 'ש"ח', "\u00a0": " "}


# --- field formatting -------------------------------------------------------------------


def _clean(text: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFC", text or ""):
        ch = _REPLACE.get(ch, ch)
        if ch in "\r\n\t":
            ch = " "
        try:
            ch.encode(ENCODING)
        except UnicodeEncodeError:
            # Vowel points and other marks are dropped; anything else becomes "?".
            ch = "" if unicodedata.category(ch).startswith("M") else "?"
        out.append(ch)
    return "".join(out)


def text(value: str | None, length: int) -> str:
    """Alphanumeric: left-aligned, padded with spaces, cut to length."""
    return _clean(value or "")[:length].ljust(length)


def number(value: int | str | None, length: int) -> str:
    """Numeric: right-aligned with leading zeros. Non-digits are dropped."""
    digits = "".join(ch for ch in str(value or 0) if ch.isdigit()) or "0"
    if len(digits) > length:
        digits = digits[-length:]
    return digits.rjust(length, "0")


def amount(value: Decimal | int | None, whole: int, decimals: int = 2) -> str:
    """Signed amount X9(whole)v9(decimals): "+0000012345" without the decimal point."""
    scaled = (Decimal(value or 0) * (10**decimals)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    sign = "-" if scaled < 0 else "+"
    digits = str(abs(int(scaled)))
    if len(digits) > whole + decimals:
        raise ValueError(f"Amount {value} does not fit {whole}.{decimals} digits")
    return sign + digits.rjust(whole + decimals, "0")


def unsigned(value: Decimal | int | None, whole: int, decimals: int = 2) -> str:
    """Numeric amount 9(whole)v9(decimals) without a sign (negative values become zero)."""
    scaled = (max(Decimal(value or 0), Decimal(0)) * (10**decimals)).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return number(int(scaled), whole + decimals)


def ymd(value: date | None) -> str:
    return value.strftime("%Y%m%d") if value else "0" * 8


def hhmm(value: datetime | None) -> str:
    return value.strftime("%H%M") if value else "0000"


def blank(length: int) -> str:
    return " " * length


# --- input --------------------------------------------------------------------------------


@dataclass
class Party:
    """A customer (sales documents) or supplier (purchasing documents)."""

    key: str  # the business's own key for the party
    name: str
    street: str = ""
    city: str = ""
    zip: str = ""
    phone: str = ""
    tax_id: str = ""


@dataclass
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal  # before VAT
    discount: Decimal  # before VAT, positive (written as a negative amount)
    total: Decimal  # before VAT, after the discount
    vat_percent: Decimal  # e.g. 18 (0 for exempt or zero-rated lines)
    unit: str = ""
    sku: str = ""
    kind: int = 0  # 1 service, 2 goods
    base_type: int = 0  # the document this one is based on (e.g. a delivery note)
    base_number: str = ""


@dataclass
class Payment:
    method: int  # 1 cash, 2 cheque, 3 credit card, 4 bank transfer, 9 other
    amount: Decimal
    payment_date: date | None = None
    bank: str = ""
    branch: str = ""
    account: str = ""
    cheque: str = ""
    credit_kind: int = 0  # 1 regular, 2 installments


@dataclass
class Doc:
    doc_type: int  # appendix 1
    number: str
    document_date: date
    produced_at: datetime | None  # when the software issued it (Israel time)
    party: Party
    net: Decimal  # before VAT
    vat: Decimal
    total: Decimal
    operator: str = ""
    lines: list[Line] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)


@dataclass
class StockItem:
    sku: str  # unique within the business
    name: str
    barcode: str = ""
    unit: str = ""
    opening: Decimal = Decimal(0)
    received: Decimal = Decimal(0)
    issued: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)  # cost per unit at the end of the period


@dataclass
class Business:
    tax_id: str
    name: str
    street: str = ""
    city: str = ""
    zip: str = ""
    company_number: str = ""  # ח"פ, companies only


@dataclass
class Software:
    name: str
    version: str
    registration_number: str = "0"  # issued by the tax authority once the software is registered
    maker_tax_id: str = "0"
    maker_name: str = ""


@dataclass
class Result:
    folder: str  # OPENFRMT/<8 digits>.<yy>/<MMDDhhmm>
    ini: bytes
    bkmvdata_zip: bytes
    counts: dict[str, int]  # records per type in BKMVDATA.TXT
    by_doc_type: dict[int, tuple[int, Decimal]]  # appendix 4 / §2.6: count and total
    report: str  # the printable summary (UTF-8)


# --- records ------------------------------------------------------------------------------


def _record(code: str, parts: list[str]) -> str:
    record = code + "".join(parts)
    expected = RECORD_LENGTHS[code]
    if len(record) != expected:
        raise AssertionError(f"{code} record is {len(record)} long, expected {expected}")
    return record


def _c100(n: int, vat_id: str, doc: Doc, link: int) -> str:
    p = doc.party
    receipt = doc.doc_type == 400
    before_discount = doc.total if receipt else doc.net
    return _record(
        "C100",
        [
            number(n, 9),
            number(vat_id, 9),
            number(doc.doc_type, 3),
            text(doc.number, 20),
            ymd(doc.produced_at.date() if doc.produced_at else doc.document_date),
            hhmm(doc.produced_at),
            text(p.name, 50),
            text(p.street, 50),
            blank(10),  # house number: kept in the street field
            text(p.city, 30),
            text(p.zip, 8),
            blank(30),  # country (Israel when empty)
            blank(2),
            text(p.phone, 15),
            number(p.tax_id, 9),
            ymd(doc.document_date),  # value date
            blank(15),  # foreign-currency total: export invoices only
            blank(3),
            amount(before_discount, 12),
            amount(0, 12),  # document discount: discounts are per line
            amount(before_discount, 12),
            amount(0 if receipt else doc.vat, 12),
            amount(doc.total, 12),
            amount(0, 9),  # tax withheld at source
            text(p.key, 15),
            blank(10),  # matching field
            blank(1),  # cancelled: issued documents are never cancelled, only credited
            ymd(doc.document_date),
            blank(7),  # branch
            text(doc.operator, 9),
            number(link, 7),
            blank(13),
        ],
    )


def _d110(n: int, vat_id: str, doc: Doc, index: int, line: Line, link: int) -> str:
    return _record(
        "D110",
        [
            number(n, 9),
            number(vat_id, 9),
            number(doc.doc_type, 3),
            text(doc.number, 20),
            number(index, 4),
            number(line.base_type, 3),
            text(line.base_number, 20),
            number(line.kind, 1),
            text(line.sku, 20),
            text(line.description, 30),
            blank(50),  # manufacturer (goods listed in appendix C of instruction 36 only)
            blank(30),  # serial number
            text(line.unit or "יחידה", 20),
            amount(line.quantity, 12, 4),
            amount(line.unit_price, 12),
            amount(-line.discount, 12),
            amount(line.total, 12),
            unsigned(line.vat_percent, 2),
            blank(7),  # branch
            ymd(doc.document_date),
            number(link, 7),
            blank(7),  # branch of the base document
            blank(21),
        ],
    )


def _d120(n: int, vat_id: str, doc: Doc, index: int, pay: Payment, link: int) -> str:
    cheque = pay.method == 2
    dated = pay.method in (2, 3)
    return _record(
        "D120",
        [
            number(n, 9),
            number(vat_id, 9),
            number(doc.doc_type, 3),
            text(doc.number, 20),
            number(index, 4),
            number(pay.method, 1),
            number(pay.bank if cheque else 0, 10),
            number(pay.branch if cheque else 0, 10),
            number(pay.account if cheque else 0, 15),
            number(pay.cheque if cheque else 0, 10),
            ymd(pay.payment_date) if dated else "0" * 8,
            amount(pay.amount, 12),
            number(0, 1),  # clearing company: not recorded
            blank(20),  # card name
            number(pay.credit_kind if pay.method == 3 else 0, 1),
            blank(7),  # branch
            ymd(doc.document_date),
            number(link, 7),
            blank(60),
        ],
    )


def _m100(n: int, vat_id: str, item: StockItem) -> str:
    return _record(
        "M100",
        [
            number(n, 9),
            number(vat_id, 9),
            text(item.barcode, 20),
            blank(20),  # supplier's catalogue number
            text(item.sku, 20),
            text(item.name, 50),
            blank(10),  # sort code
            blank(30),
            text(item.unit or "יחידה", 20),
            amount(item.opening, 9),
            amount(item.received, 9),
            amount(item.issued, 9),
            unsigned(item.cost, 8),
            unsigned(0, 8),  # bonded warehouses: not used
            blank(50),
        ],
    )


def build(
    *,
    business: Business,
    software: Software,
    documents: list[Doc],
    stock: list[StockItem],
    date_from: date,
    date_to: date,
    now: datetime,
    main_id: int | None = None,
) -> Result:
    """Both files for one run. ``now`` is the local (Israel) time of the run."""
    vat_id = number(business.tax_id, 9)
    main = number(main_id if main_id is not None else secrets.randbelow(9 * 10**14) + 10**14, 15)
    folder = f"OPENFRMT/{vat_id[:8]}.{now:%y}/{now:%m%d%H%M}"

    records: list[str] = []
    add = records.append

    add(_record("A100", [number(1, 9), vat_id, main, SYSTEM_CONSTANT, blank(50)]))
    link = 0
    by_type: dict[int, tuple[int, Decimal]] = {}
    for doc in documents:
        link += 1
        count, total = by_type.get(doc.doc_type, (0, Decimal(0)))
        by_type[doc.doc_type] = (count + 1, total + doc.total)
        add(_c100(len(records) + 1, vat_id, doc, link))
        for index, line in enumerate(doc.lines, start=1):
            add(_d110(len(records) + 1, vat_id, doc, index, line, link))
        for index, pay in enumerate(doc.payments, start=1):
            add(_d120(len(records) + 1, vat_id, doc, index, pay, link))
    for item in stock:
        add(_m100(len(records) + 1, vat_id, item))
    total_records = len(records) + 1
    add(
        _record(
            "Z900",
            [
                number(total_records, 9),
                vat_id,
                main,
                SYSTEM_CONSTANT,
                number(total_records, 15),
                blank(50),
            ],
        )
    )
    counts = Counter(r[:4] for r in records)

    multi_year = 2
    ini_records = [
        _record(
            "A000",
            [
                blank(5),
                number(total_records, 15),
                vat_id,
                main,
                SYSTEM_CONSTANT,
                number(software.registration_number, 8),
                text(software.name, 20),
                text(software.version, 20),
                number(software.maker_tax_id, 9),
                text(software.maker_name, 20),
                number(multi_year, 1),
                text(folder.replace("/", "\\"), 50),
                number(0, 1),  # bookkeeping: not relevant (not a ledger)
                number(0, 1),
                number(business.company_number, 9),
                number(0, 9),  # withholding file
                blank(10),
                text(business.name, 50),
                text(business.street, 50),
                blank(10),
                text(business.city, 30),
                text(business.zip, 8),
                number(0, 4),  # tax year: single-year software only
                ymd(date_from),
                ymd(date_to),
                ymd(now.date()),
                hhmm(now),
                number(0, 1),  # language: Hebrew
                number(1, 1),  # ISO-8859-8-i
                text("zip", 20),
                text("ILS", 3),
                number(0, 1),  # no branches
                blank(46),
            ],
        )
    ]
    for code in ("C100", "D110", "D120", "M100"):
        if counts.get(code):
            summary = code + number(counts[code], 15)
            assert len(summary) == SUMMARY_LENGTH
            ini_records.append(summary)

    def encode(lines: list[str]) -> bytes:
        return "".join(line + "\r\n" for line in lines).encode(ENCODING)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BKMVDATA.TXT", encode(records))
    return Result(
        folder=folder,
        ini=encode(ini_records),
        bkmvdata_zip=archive.getvalue(),
        counts=dict(counts),
        by_doc_type=by_type,
        report=_report(business, software, folder, date_from, date_to, now, counts, by_type),
    )


def _report(
    business: Business,
    software: Software,
    folder: str,
    date_from: date,
    date_to: date,
    now: datetime,
    counts: Counter[str],
    by_type: dict[int, tuple[int, Decimal]],
) -> str:
    """The printout of appendix 4, with the document totals of section 2.6."""
    names = {
        "A100": "רשומת פתיחה",
        "C100": "כותרת מסמך",
        "D110": "פרטי מסמך",
        "D120": "פרטי קבלות",
        "M100": "פריטים במלאי",
        "Z900": "רשומת סיום",
    }
    lines = [
        "הפקת קבצים במבנה אחיד עבור:",
        f"מספר עוסק מורשה: {business.tax_id}",
        f"שם בית העסק: {business.name}",
        "ביצוע ממשק פתוח הסתיים בהצלחה.",
        f"הנתונים נשמרו בנתיב הבא: {folder.replace('/', chr(92))}",
        f"טווח תאריכים: מתאריך {date_from:%d%m%Y} ועד תאריך {date_to:%d%m%Y}",
        "",
        "פירוט סך סוגי הרשומות שנוצרו בקובץ BKMVDATA.TXT:",
        "קוד רשומה | תיאור רשומה | סך רשומות",
    ]
    for code, name in names.items():
        if counts.get(code):
            lines.append(f"{code} | {name} | {counts[code]}")
    lines += [
        "",
        "סיכום מסמכים לפי סוג (סעיף 2.6):",
        "מספר המסמך | סוג המסמך | סה״כ כמותי | סה״כ כספי (בש״ח)",
    ]
    for doc_code, doc_name in DOC_TYPE_NAMES.items():
        count, total = by_type.get(doc_code) or (0, Decimal(0))
        lines.append(f"{doc_code} | {doc_name} | {count} | {total:,.2f}")
    lines += [
        "",
        f"הנתונים הופקו באמצעות תוכנת: {software.name}, "
        f"מספר תעודת הרישום: {software.registration_number}",
        f"בתאריך {now:%d/%m/%y} בשעה {now:%H:%M}",
    ]
    return "\n".join(lines) + "\n"
