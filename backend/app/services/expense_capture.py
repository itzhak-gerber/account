"""Supplier invoices from a photo or a PDF.

The upload is kept as a PDF (a photo becomes a one-page PDF, re-encoded, metadata such as GPS
dropped), signed like issued documents when a signing certificate is configured. When an
Anthropic API key is configured, Claude reads the invoice and suggests the fields (supplier,
number, date, amounts); the user always checks and saves them. Without a key the file is
still kept and the fields are typed by hand.
"""

import base64
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import anthropic
import structlog
from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import get_storage
from app.models import Module, StoredFile, Supplier, UsageKind
from app.pdf import signing
from app.schemas.identity import israeli_id_checksum_ok
from app.services import audit, billing
from app.services.permissions import Permission, require

log = structlog.get_logger()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000  # refuse "decompression bomb" images before decoding them
LONG_EDGE = 2400  # enough to read small print; keeps files and the AI request small
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

INSTRUCTIONS = """You read photos and PDFs of invoices that an Israeli business received from its
suppliers (חשבונית מס, חשבונית מס/קבלה, קבלה). Report what is printed on the document; never
guess. Use null for anything that is missing or unreadable.

- supplier_name: the business that issued the document (not the customer it is addressed to).
- supplier_tax_id: the supplier's עוסק מורשה / ח.פ. number, digits only.
- invoice_number: the document's own number, as printed.
- invoice_date: the document date as YYYY-MM-DD (Israeli documents print DD/MM/YYYY).
- net_amount: the total before VAT (סה"כ לפני מע"מ); vat_amount: the VAT (מע"מ);
  total: the total including VAT (סה"כ לתשלום). Plain numbers, no currency signs.
- is_invoice: false when the image is not an invoice or receipt at all."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_invoice": {"type": "boolean"},
        "supplier_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "supplier_tax_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "invoice_number": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "invoice_date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "net_amount": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "vat_amount": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "total": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": [
        "is_invoice",
        "supplier_name",
        "supplier_tax_id",
        "invoice_number",
        "invoice_date",
        "net_amount",
        "vat_amount",
        "total",
    ],
    "additionalProperties": False,
}


class InvalidScan(AppError):
    status_code = 422
    code = "invalid_scan"


@dataclass
class Prepared:
    pdf: bytes  # what is stored
    ai_block: dict[str, Any]  # what Claude reads


def ai_enabled() -> bool:
    return get_settings().anthropic_api_key not in ("", "unset")


def prepare(data: bytes) -> Prepared:
    """Validate the upload; a photo becomes a clean one-page PDF."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidScan("The file must be at most 15 MB", code="scan_too_large")
    if data.startswith(b"%PDF"):
        return Prepared(
            pdf=data,
            ai_block={
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(data).decode(),
                },
            },
        )
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in IMAGE_FORMATS:
                raise InvalidScan("Send a photo (JPG, PNG) or a PDF")
            if probe.width * probe.height > MAX_PIXELS:
                raise InvalidScan("The image is too large", code="scan_too_large")
            probe.verify()
        with Image.open(io.BytesIO(data)) as source:
            image: Image.Image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((LONG_EDGE, LONG_EDGE))
            jpeg, pdf = io.BytesIO(), io.BytesIO()
            image.save(jpeg, format="JPEG", quality=85)
            image.save(pdf, format="PDF", resolution=200)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidScan("The file is not a valid photo or PDF") from exc
    return Prepared(
        pdf=pdf.getvalue(),
        ai_block={
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(jpeg.getvalue()).decode(),
            },
        },
    )


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key=get_settings().anthropic_api_key, timeout=90, max_retries=2
    )


async def read_invoice(block: dict[str, Any]) -> dict[str, Any] | None:
    """Claude's reading of the document, or None when it could not be read."""
    settings = get_settings()
    try:
        response = await _client().beta.messages.create(
            model=settings.expense_ai_model,
            max_tokens=8000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config=cast(
                BetaOutputConfigParam,
                {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            ),
            system=INSTRUCTIONS,
            messages=[
                cast(
                    BetaMessageParam,
                    {
                        "role": "user",
                        "content": [
                            block,
                            {"type": "text", "text": "Read this supplier document."},
                        ],
                    },
                )
            ],
        )
    except anthropic.APIConnectionError as exc:
        log.warning("expense.ai_unreachable", error=str(exc)[:200])
        return None
    except anthropic.APIStatusError as exc:
        log.warning("expense.ai_error", status=exc.status_code, request_id=exc.request_id)
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("expense.ai_stopped", reason=response.stop_reason)
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return None
    try:
        result: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        return None
    return result


def _amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def clean(reading: dict[str, Any] | None) -> dict[str, Any]:
    """Only values that pass the same checks as typed input survive."""
    if not reading or not reading.get("is_invoice"):
        return {}
    out: dict[str, Any] = {}
    if name := (reading.get("supplier_name") or "").strip():
        out["supplier_name"] = name[:200]
    tax_id = re.sub(r"\D", "", reading.get("supplier_tax_id") or "")
    if tax_id and len(tax_id) <= 9 and israeli_id_checksum_ok(tax_id.zfill(9)):
        out["supplier_tax_id"] = tax_id.zfill(9)
    if number := (reading.get("invoice_number") or "").strip():
        out["invoice_number"] = number[:50]
    try:
        out["invoice_date"] = date.fromisoformat(reading.get("invoice_date") or "")
    except ValueError:
        pass
    for key in ("net_amount", "vat_amount", "total"):
        if (amount := _amount(reading.get(key))) is not None:
            out[key] = amount
    # A missing piece of net / VAT / total can be worked out from the other two.
    net, vat, total = out.get("net_amount"), out.get("vat_amount"), out.get("total")
    if net is None and vat is not None and total is not None and total >= vat:
        out["net_amount"] = total - vat
    elif vat is None and net is not None and total is not None and total >= net:
        out["vat_amount"] = total - net
    return out


async def _supplier(
    session: AsyncSession, ctx: BusinessContext, found: dict[str, Any]
) -> Supplier | None:
    base = select(Supplier).where(Supplier.business_id == ctx.business_id)
    if tax_id := found.get("supplier_tax_id"):
        match = await session.scalar(base.where(Supplier.tax_id == tax_id))
        if match:
            return match
    if name := found.get("supplier_name"):
        match = await session.scalar(base.where(func.lower(Supplier.name) == name.lower()))
        if match:
            return match
    return None


async def scan(session: AsyncSession, ctx: BusinessContext, data: bytes) -> dict[str, Any]:
    """Keep the file and suggest the invoice's fields."""
    require(ctx, Permission.MANAGE_PURCHASING)
    ctx.access.require(Module.SCANNING)
    await billing.check_scan_allowed(session, ctx.business_id)
    prepared = prepare(data)
    try:
        pdf = await signing.sign(prepared.pdf)
    except Exception:  # an uploaded PDF the signer cannot handle is kept as it came
        log.warning("expense.not_signed", exc_info=True)
        pdf = prepared.pdf
    stored = await get_storage().put(f"{ctx.business_id}/expenses/{uuid.uuid4()}.pdf", pdf)
    file = StoredFile(
        business_id=ctx.business_id,
        storage_key=stored.key,
        content_type="application/pdf",
        size=stored.size,
        sha256=stored.sha256,
    )
    session.add(file)
    await session.flush()
    await billing.record_usage(session, ctx.business_id, UsageKind.SCAN, file.id)

    found = clean(await read_invoice(prepared.ai_block)) if ai_enabled() else {}
    supplier = await _supplier(session, ctx, found) if found else None
    await audit.record(
        session,
        ctx.principal,
        action="supplier_invoice.scanned",
        entity_type="file",
        entity_id=file.id,
        business_id=ctx.business_id,
        changes={"size": stored.size, "read": bool(found)},
    )
    return {
        "file_id": file.id,
        "read": bool(found),
        "ai_enabled": ai_enabled(),
        "supplier_id": supplier.id if supplier else None,
        **found,
    }
