from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import VatRate


async def rate_on(session: AsyncSession, on: date) -> Decimal:
    rate = await session.scalar(
        select(VatRate.rate)
        .where(VatRate.effective_from <= on)
        .order_by(VatRate.effective_from.desc())
        .limit(1)
    )
    if rate is None:
        raise AppError(f"No VAT rate configured for {on}", code="vat_rate_missing")
    return rate
