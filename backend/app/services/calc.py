"""Money calculations for documents. Pure functions on Decimal; no floats anywhere.

Rounding rule (documented in docs/PLAN.md §3): each line total is rounded to agorot
(ROUND_HALF_UP); VAT is computed once on the sum of standard-rated lines and rounded;
the document total is the sum of the rounded parts.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models import VatType

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineInput:
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    vat_type: VatType


@dataclass(frozen=True)
class Totals:
    line_totals: list[Decimal]  # per line, as entered (before VAT, or incl. VAT if so entered)
    subtotal: Decimal  # before VAT, after line discounts
    discount_total: Decimal  # sum of line discounts, before VAT
    vat_amount: Decimal
    total: Decimal  # amount to pay


def line_total(line: LineInput) -> Decimal:
    gross = line.quantity * line.unit_price
    return money(gross * (HUNDRED - line.discount_percent) / HUNDRED)


def compute_totals(
    lines: Sequence[LineInput], *, vat_rate: Decimal, prices_include_vat: bool
) -> Totals:
    totals = [line_total(line) for line in lines]
    discounts = [
        money(line.quantity * line.unit_price) - total
        for line, total in zip(lines, totals, strict=True)
    ]
    taxable = sum(
        (t for line, t in zip(lines, totals, strict=True) if line.vat_type == VatType.STANDARD),
        ZERO,
    )
    entered_sum = sum(totals, ZERO)

    if prices_include_vat:
        vat = money(taxable * vat_rate / (1 + vat_rate))
        total = entered_sum
        subtotal = total - vat
        discount_total = (
            money(sum(discounts, ZERO) / (1 + vat_rate)) if vat_rate else sum(discounts, ZERO)
        )
    else:
        vat = money(taxable * vat_rate)
        subtotal = entered_sum
        total = subtotal + vat
        discount_total = sum(discounts, ZERO)
    return Totals(
        line_totals=totals,
        subtotal=money(subtotal),
        discount_total=money(discount_total),
        vat_amount=vat,
        total=money(total),
    )
