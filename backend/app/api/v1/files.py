"""Downloads by signed link (no session): used for PDF links handed to MCP clients."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.v1.documents import pdf_response
from app.auth.principal import DbSession, Principal, enter_business
from app.core.db import commit, set_rls_context
from app.core.signing import sign, verify
from app.services import documents

router = APIRouter(tags=["files"])
PURPOSE = "document-pdf"


def document_pdf_link(
    principal: Principal, business_id: uuid.UUID, document_id: uuid.UUID, base_url: str
) -> str:
    token = sign(
        {
            "u": str(principal.user_id),
            "e": principal.email,
            "m": principal.mfa,
            "b": str(business_id),
            "d": str(document_id),
        },
        purpose=PURPOSE,
        ttl_seconds=600,
    )
    return f"{base_url.rstrip('/')}/api/v1/files/document-pdf?token={token}"


@router.get("/files/document-pdf")
async def signed_document_pdf(
    session: DbSession, token: Annotated[str, Query(max_length=2000)]
) -> Response:
    payload = verify(token, purpose=PURPOSE)
    principal = Principal(
        user_id=uuid.UUID(payload["u"]), email=payload["e"], channel="mcp", mfa=bool(payload["m"])
    )
    await set_rls_context(session, user_id=principal.user_id)
    # Membership and role are re-checked now, not trusted from when the link was made.
    ctx = await enter_business(session, principal, uuid.UUID(payload["b"]))
    content, filename, variant = await documents.pdf(session, ctx, uuid.UUID(payload["d"]))
    await commit(session)
    return pdf_response(content, filename, variant)
