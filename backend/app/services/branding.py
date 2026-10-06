"""Business logo: validated, cleaned (re-encoded as PNG, metadata dropped) and resized."""

import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import BusinessContext
from app.core.errors import AppError
from app.core.storage import get_storage
from app.models import Business, StoredFile
from app.services import audit
from app.services.permissions import Permission, require

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 25_000_000  # refuse "decompression bomb" images before decoding them
MAX_SIZE = (800, 400)  # stored size; the PDF shows it at most ~60x22 mm
ALLOWED_FORMATS = {"PNG", "JPEG"}


class InvalidImage(AppError):
    status_code = 422
    code = "invalid_image"


def clean_logo(data: bytes) -> bytes:
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImage("The logo must be at most 2 MB", code="image_too_large")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise InvalidImage("Only PNG or JPG images are supported")
            if probe.width * probe.height > MAX_PIXELS:
                raise InvalidImage("The image is too large", code="image_too_large")
            probe.verify()
        with Image.open(io.BytesIO(data)) as source:
            image: Image.Image = ImageOps.exif_transpose(source)
            image.thumbnail(MAX_SIZE)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImage("The file is not a valid image") from exc


async def set_logo(session: AsyncSession, ctx: BusinessContext, data: bytes) -> Business:
    require(ctx.role, Permission.MANAGE_BUSINESS)
    png = clean_logo(data)
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    stored = await get_storage().put(f"{ctx.business_id}/logo/{uuid.uuid4()}.png", png)
    file = StoredFile(
        business_id=ctx.business_id,
        storage_key=stored.key,
        content_type="image/png",
        size=stored.size,
        sha256=stored.sha256,
    )
    session.add(file)
    await session.flush()
    business.logo_file_id = file.id
    await session.flush()
    await audit.record(
        session,
        ctx.principal,
        action="business.logo_changed",
        entity_type="business",
        entity_id=business.id,
        business_id=business.id,
        changes={"file_id": str(file.id), "size": stored.size},
    )
    return business


async def remove_logo(session: AsyncSession, ctx: BusinessContext) -> None:
    require(ctx.role, Permission.MANAGE_BUSINESS)
    business = await session.get(Business, ctx.business_id)
    assert business is not None
    if business.logo_file_id is not None:
        business.logo_file_id = None
        await session.flush()
        await audit.record(
            session,
            ctx.principal,
            action="business.logo_removed",
            entity_type="business",
            entity_id=business.id,
            business_id=business.id,
        )


async def load_file(session: AsyncSession, file_id: uuid.UUID | str | None) -> bytes | None:
    """Read a stored file of the current business (RLS limits it to that business)."""
    if not file_id:
        return None
    file = await session.get(StoredFile, uuid.UUID(str(file_id)))
    if file is None:
        return None
    return await get_storage().get(file.storage_key)
