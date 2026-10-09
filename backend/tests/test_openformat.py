"""The uniform format, read back by the column positions printed in specification 1.31."""

import io
import zipfile
from datetime import date, datetime
from decimal import Decimal

import pytest

from app import openformat as of
from app.jobs import worker
from tests.fake_idp import FakeIdP
from tests.helpers import app_client
from tests.test_delivery_notes import deliver
from tests.test_documents import draft, issue, setup
from tests.test_exports import export_jobs
from tests.test_inventory import item, line
from tests.test_notifications import Jobs
from tests.test_payments import make_receipt
from tests.test_purchasing import order, receive, supplier


def col(record: str, start: int, end: int) -> str:
    """Columns as the specification numbers them (1-based, inclusive)."""
    return record[start - 1 : end]


def sample() -> of.Result:
    customer = of.Party(key="C1", name="לקוח בע״מ", city="חיפה", tax_id="123456782")
    invoice = of.Doc(
        doc_type=305,
        number="17",
        document_date=date(2026, 10, 5),
        produced_at=datetime(2026, 10, 5, 9, 41),
        party=customer,
        net=Decimal("1090.00"),
        vat=Decimal("196.20"),
        total=Decimal("1286.20"),
        operator="dana",
        lines=[
            of.Line(
                description="ייעוץ",
                quantity=Decimal("2"),
                unit_price=Decimal("500"),
                discount=Decimal("0"),
                total=Decimal("1000"),
                vat_percent=Decimal("18"),
                unit="שעה",
                kind=1,
                base_type=200,
                base_number="3",
            ),
            of.Line(
                description="נסיעות",
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                discount=Decimal("10"),
                total=Decimal("90"),
                vat_percent=Decimal("18"),
            ),
        ],
    )
    receipt = of.Doc(
        doc_type=400,
        number="5",
        document_date=date(2026, 10, 6),
        produced_at=datetime(2026, 10, 6, 12, 0),
        party=customer,
        net=Decimal("0"),
        vat=Decimal("0"),
        total=Decimal("1286.20"),
        payments=[
            of.Payment(
                method=2,
                amount=Decimal("1286.20"),
                payment_date=date(2026, 11, 1),
                bank="12",
                branch="600",
                account="123456",
                cheque="1001",
            )
        ],
    )
    return of.build(
        business=of.Business(
            tax_id="516179157",
            name="דוגמה בע״מ",
            street="הרצל 1",
            city="תל אביב",
            company_number="516179157",
        ),
        software=of.Software(name="חשבוניות", version="1.0"),
        documents=[invoice, receipt],
        stock=[
            of.StockItem(
                sku="KB-100",
                name="מקלדת",
                opening=Decimal("5"),
                received=Decimal("195"),
                issued=Decimal("120"),
                cost=Decimal("25.5"),
            )
        ],
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        now=datetime(2026, 10, 9, 14, 5),
        main_id=123456789012345,
    )


def bkmvdata(result: of.Result) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(result.bkmvdata_zip)) as z:
        raw = z.read("BKMVDATA.TXT")
    assert raw.endswith(b"\r\n")
    return raw.decode(of.ENCODING).split("\r\n")[:-1]


def test_records_have_the_specified_lengths_and_order() -> None:
    result = sample()
    records = bkmvdata(result)
    assert [r[:4] for r in records] == [
        "A100",
        "C100",
        "D110",
        "D110",
        "C100",
        "D120",
        "M100",
        "Z900",
    ]
    for r in records:
        assert len(r) == of.RECORD_LENGTHS[r[:4]], r[:4]
        # Field 2 of every record: its running number in the file.
        assert col(r, 5, 13) == str(records.index(r) + 1).zfill(9)
    assert result.counts == {
        "A100": 1,
        "C100": 2,
        "D110": 2,
        "D120": 1,
        "M100": 1,
        "Z900": 1,
    }
    assert result.folder == "OPENFRMT/51617915.26/10091405"


def test_ini_header_and_summaries() -> None:
    result = sample()
    ini = result.ini.decode(of.ENCODING).split("\r\n")[:-1]
    a000 = ini[0]
    assert len(a000) == 466
    assert col(a000, 1, 4) == "A000"
    assert col(a000, 10, 24) == "8".zfill(15)  # 1002: records in BKMVDATA, same as Z900
    assert col(a000, 25, 33) == "516179157"  # 1003
    assert col(a000, 34, 48) == "123456789012345"  # 1004: main id
    assert col(a000, 49, 56) == "&OF1.31&"  # 1005
    assert col(a000, 134, 134) == "2"  # 1011: multi-year software
    assert col(a000, 135, 184).rstrip() == r"OPENFRMT\51617915.26\10091405"  # 1012
    assert col(a000, 187, 195) == "516179157"  # 1015: company number
    assert col(a000, 215, 264).rstrip() == 'דוגמה בע"מ'  # 1018
    assert col(a000, 367, 374) == "20260101"  # 1024
    assert col(a000, 375, 382) == "20261231"  # 1025
    assert col(a000, 383, 390) == "20261009"  # 1026
    assert col(a000, 391, 394) == "1405"  # 1027
    assert col(a000, 396, 396) == "1"  # 1029: ISO-8859-8-i
    assert col(a000, 417, 419) == "ILS"  # 1032
    assert col(a000, 420, 420) == "0"  # 1034: no branches
    assert ini[1:] == [
        "C100" + "2".zfill(15),
        "D110" + "2".zfill(15),
        "D120" + "1".zfill(15),
        "M100" + "1".zfill(15),
    ]


def test_document_header_lines_and_payments() -> None:
    records = bkmvdata(sample())
    c100, line1, line2, receipt, d120 = records[1], records[2], records[3], records[4], records[5]

    assert col(c100, 23, 25) == "305"  # 1203: tax invoice
    assert col(c100, 26, 45).rstrip() == "17"  # 1204
    assert col(c100, 46, 53) == "20261005"  # 1205: production date
    assert col(c100, 54, 57) == "0941"  # 1206
    assert col(c100, 58, 107).rstrip() == 'לקוח בע"מ'  # 1207
    assert col(c100, 168, 197).rstrip() == "חיפה"  # 1210
    assert col(c100, 253, 261) == "123456782"  # 1215
    assert col(c100, 288, 302) == "+00000000109000"  # 1219
    assert col(c100, 303, 317) == "+00000000000000"  # 1220
    assert col(c100, 318, 332) == "+00000000109000"  # 1221
    assert col(c100, 333, 347) == "+00000000019620"  # 1222
    assert col(c100, 348, 362) == "+00000000128620"  # 1223
    assert col(c100, 375, 389).rstrip() == "C1"  # 1225: customer key
    assert col(c100, 401, 408) == "20261005"  # 1230: document date
    assert col(c100, 416, 424).rstrip() == "dana"  # 1233
    assert col(c100, 425, 431) == "0000001"  # 1234: link to the lines

    assert col(line1, 23, 25) == "305"  # 1253
    assert col(line1, 46, 49) == "0001"  # 1255
    assert col(line1, 50, 52) == "200"  # 1256: based on a delivery note
    assert col(line1, 53, 72).rstrip() == "3"  # 1257
    assert col(line1, 73, 73) == "1"  # 1258: service
    assert col(line1, 94, 123).rstrip() == "ייעוץ"  # 1260
    assert col(line1, 204, 223).rstrip() == "שעה"  # 1263
    assert col(line1, 224, 240) == "+0000000000020000"  # 1264: 2.0000
    assert col(line1, 241, 255) == "+00000000050000"  # 1265
    assert col(line1, 271, 285) == "+00000000100000"  # 1267
    assert col(line1, 286, 289) == "1800"  # 1268: 18%
    assert col(line1, 297, 304) == "20261005"  # 1272
    assert col(line1, 305, 311) == "0000001"  # 1273: link to the header
    assert col(line2, 204, 223).rstrip() == "יחידה"  # default unit
    assert col(line2, 256, 270) == "-00000000001000"  # 1266: discounts are negative

    assert col(receipt, 23, 25) == "400"
    # A receipt: 1219, 1221 and 1223 carry the amount received; no VAT.
    assert col(receipt, 288, 302) == col(receipt, 348, 362) == "+00000000128620"
    assert col(receipt, 333, 347) == "+00000000000000"
    assert col(d120, 46, 49) == "0001"  # 1305
    assert col(d120, 50, 50) == "2"  # 1306: cheque
    assert col(d120, 51, 60) == "0000000012"  # 1307: bank
    assert col(d120, 61, 70) == "0000000600"  # 1308
    assert col(d120, 71, 85) == "000000000123456"  # 1309
    assert col(d120, 86, 95) == "0000001001"  # 1310
    assert col(d120, 96, 103) == "20261101"  # 1311
    assert col(d120, 104, 118) == "+00000000128620"  # 1312
    assert col(d120, 156, 162) == "0000002"  # 1323: link to the receipt


def test_stock_item_and_closing_record() -> None:
    records = bkmvdata(sample())
    m100, z900 = records[6], records[7]
    assert col(m100, 63, 82).rstrip() == "KB-100"  # 1455
    assert col(m100, 83, 132).rstrip() == "מקלדת"  # 1456
    assert col(m100, 173, 192).rstrip() == "יחידה"  # 1459
    assert col(m100, 193, 204) == "+00000000500"  # 1460: opening
    assert col(m100, 205, 216) == "+00000019500"  # 1461: in
    assert col(m100, 217, 228) == "+00000012000"  # 1462: out
    assert col(m100, 229, 238) == "0000002550"  # 1463: cost
    assert col(z900, 14, 22) == "516179157"  # 1152
    assert col(z900, 23, 37) == "123456789012345"  # 1153: same main id
    assert col(z900, 38, 45) == "&OF1.31&"
    assert col(z900, 46, 60) == "8".zfill(15)  # 1155: every record, opening and closing


def test_text_is_made_safe_for_the_fixed_width_hebrew_file() -> None:
    assert of.text("שורה\nשנייה", 12) == "שורה שנייה  "
    assert of.text("מחיר ₪5", 10) == 'מחיר ש"ח5 '
    assert of.text("עֲבוֹדָה", 6) == "עבודה "  # vowel points dropped
    assert of.text("café ☕", 6) == "caf? ?"
    assert of.amount(Decimal("-12345.65"), 5) == "-1234565"
    assert of.amount(Decimal("1245"), 5) == "+0124500"
    with pytest.raises(ValueError):
        of.amount(Decimal("1000000"), 5)


async def test_data_export_carries_the_uniform_format_files(idp: FakeIdP, sent_jobs: Jobs) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        base = f"/api/v1/businesses/{bid}/documents"
        mug = await item(owner, bid, track_inventory=True, sku="MUG-1")
        north = await supplier(owner, bid)
        po = (
            await order(
                owner,
                bid,
                north["id"],
                [{"item_id": mug["id"], "description": "ספל", "quantity": "10", "unit_cost": "20"}],
            )
        ).json()
        await receive(
            owner,
            bid,
            north["id"],
            purchase_order_id=po["id"],
            lines=[
                {
                    "item_id": mug["id"],
                    "order_line_id": po["lines"][0]["id"],
                    "quantity": "10",
                    "unit_cost": "20",
                }
            ],
        )
        note = await deliver(owner, bid, [line(mug["id"], "4")])
        invoice = (
            await owner.post(f"{base}/{note['id']}/convert", json={"type": "tax_invoice"})
        ).json()
        await issue(owner, bid, invoice["id"])
        receipt = await make_receipt(
            owner, bid, "188.80", [{"invoice_id": invoice["id"], "amount": "188.80"}]
        )
        await issue(owner, bid, receipt["id"])
        await draft(owner, bid, type="quote")  # drafts and quotes stay out
        sent_jobs.clear()

        started = await owner.post(f"/api/v1/businesses/{bid}/exports", json={})
        assert started.status_code == 202, started.text
        [job] = export_jobs(sent_jobs)
        assert await worker.build_export({}, **job) == "ready"
        [listed] = (await owner.get(f"/api/v1/businesses/{bid}/exports")).json()
        download = await owner.get(f"/api/v1/businesses/{bid}/exports/{listed['id']}/download")
        archive = zipfile.ZipFile(io.BytesIO(download.content))

        [ini_name] = [n for n in archive.namelist() if n.endswith("/INI.TXT")]
        folder = ini_name.rsplit("/", 1)[0]
        assert folder.startswith("OPENFRMT/51617915.")
        assert {f"{folder}/BKMVDATA.zip", f"{folder}/OPENFRMT_REPORT.txt"} <= set(
            archive.namelist()
        )
        with zipfile.ZipFile(io.BytesIO(archive.read(f"{folder}/BKMVDATA.zip"))) as inner:
            records = inner.read("BKMVDATA.TXT").decode(of.ENCODING).split("\r\n")[:-1]
        headers = [r for r in records if r.startswith("C100")]
        # Purchase order, goods receipt, delivery note, tax invoice, receipt.
        assert sorted(col(h, 23, 25) for h in headers) == ["200", "305", "400", "500", "600"]
        invoice_lines = [r for r in records if r.startswith("D110") and col(r, 23, 25) == "305"]
        assert [(col(r, 50, 52), col(r, 53, 72).rstrip()) for r in invoice_lines] == [
            ("200", str(note["number"]))
        ]  # the invoice is based on the delivery note
        receipt_lines = [r for r in records if r.startswith("D120")]
        assert [col(r, 104, 118) for r in receipt_lines] == ["+00000000018880"]
        [m100] = [r for r in records if r.startswith("M100")]
        assert col(m100, 63, 82).rstrip() == "MUG-1"
        assert (col(m100, 205, 216), col(m100, 217, 228)) == ("+00000001000", "+00000000400")
        ini = archive.read(ini_name).decode(of.ENCODING).split("\r\n")[:-1]
        assert col(ini[0], 10, 24) == str(len(records)).zfill(15)
        report = archive.read(f"{folder}/OPENFRMT_REPORT.txt").decode()
        assert "305 | חשבונית מס | 1 | 188.80" in report
        assert "OPENFRMT" in archive.read("README.txt").decode()


async def test_export_range_must_make_sense(idp: FakeIdP) -> None:
    async with app_client() as client:
        owner, bid = await setup(client, idp)
        refused = await owner.post(
            f"/api/v1/businesses/{bid}/exports",
            json={"date_from": "2026-12-31", "date_to": "2026-01-01"},
        )
        assert refused.json()["error"]["code"] == "invalid_date_range"
