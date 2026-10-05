from decimal import Decimal as D

from app.models import VatType
from app.services.calc import LineInput, compute_totals


def line(qty: str, price: str, discount: str = "0", vat: VatType = VatType.STANDARD) -> LineInput:
    return LineInput(D(qty), D(price), D(discount), vat)


def test_prices_before_vat() -> None:
    totals = compute_totals([line("2", "100")], vat_rate=D("0.18"), prices_include_vat=False)

    assert (totals.subtotal, totals.vat_amount, totals.total) == (D("200"), D("36.00"), D("236.00"))


def test_line_discount() -> None:
    totals = compute_totals([line("1", "1000", "10")], vat_rate=D("0.18"), prices_include_vat=False)

    assert totals.line_totals == [D("900.00")]
    assert totals.discount_total == D("100.00")
    assert totals.total == D("1062.00")


def test_prices_including_vat() -> None:
    totals = compute_totals([line("1", "118")], vat_rate=D("0.18"), prices_include_vat=True)

    assert (totals.subtotal, totals.vat_amount, totals.total) == (D("100.00"), D("18.00"), D("118"))


def test_exempt_and_zero_rated_lines_carry_no_vat() -> None:
    totals = compute_totals(
        [line("1", "100"), line("1", "50", vat=VatType.EXEMPT), line("1", "30", vat=VatType.ZERO)],
        vat_rate=D("0.18"),
        prices_include_vat=False,
    )

    assert totals.subtotal == D("180")
    assert totals.vat_amount == D("18.00")
    assert totals.total == D("198.00")


def test_rounding_is_half_up_per_line() -> None:
    totals = compute_totals([line("1.5", "9.99")], vat_rate=D("0.17"), prices_include_vat=False)

    assert totals.line_totals == [D("14.99")]  # 14.985 → 14.99
    assert totals.vat_amount == D("2.55")  # 2.5483 → 2.55
    assert totals.total == D("17.54")
