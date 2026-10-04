"""Users are created on first login from the identity provider's verified claims."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden
from app.models import User


async def upsert_from_claims(
    session: AsyncSession, claims: dict[str, Any], *, record_login: bool = False
) -> User:
    subject = claims["sub"]
    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise Forbidden("A verified email address is required", code="email_not_verified")
    full_name = claims.get("name") or " ".join(
        p for p in (claims.get("given_name"), claims.get("family_name")) if p
    )

    user = await session.scalar(select(User).where(User.idp_subject == subject))
    if user is None:
        # Same verified email under a new identity-provider id (e.g. the account was
        # re-created there): link it instead of failing on the unique email.
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                idp_subject=subject, email=email, full_name=full_name or email, is_active=True
            )
            session.add(user)
        else:
            user.idp_subject = subject
    if not user.is_active:
        raise Forbidden("This account is disabled", code="account_disabled")
    if email != user.email:
        user.email = email
    if full_name and full_name != user.full_name:
        user.full_name = full_name
    if record_login:
        user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user
