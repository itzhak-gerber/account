"""Gapless document numbers: one counter row per business and type, locked while issuing.

The lock is held until the issuing transaction commits, so concurrent issues wait for each
other and a rolled-back issue gives its number back.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.models import Document, DocumentSequence, DocumentStatus, DocumentType


async def next_number(session: AsyncSession, business_id: uuid.UUID, doc_type: DocumentType) -> int:
    await session.execute(
        insert(DocumentSequence)
        .values(business_id=business_id, document_type=doc_type, next_number=1)
        .on_conflict_do_nothing()
    )
    sequence = await session.scalar(
        select(DocumentSequence)
        .where(
            DocumentSequence.business_id == business_id,
            DocumentSequence.document_type == doc_type,
        )
        .with_for_update()
    )
    assert sequence is not None
    number = sequence.next_number
    sequence.next_number = number + 1
    await session.flush()
    return number


async def set_start(
    session: AsyncSession, business_id: uuid.UUID, doc_type: DocumentType, start: int
) -> None:
    """Let a business continue numbering from its previous software. Only before first issue."""
    issued = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.business_id == business_id,
            Document.type == doc_type,
            Document.status == DocumentStatus.ISSUED,
        )
    )
    if issued:
        raise Conflict("Numbering is fixed once a document was issued", code="numbering_locked")
    await session.execute(
        insert(DocumentSequence)
        .values(business_id=business_id, document_type=doc_type, next_number=start)
        .on_conflict_do_update(
            index_elements=["business_id", "document_type"], set_={"next_number": start}
        )
    )


async def peek(session: AsyncSession, business_id: uuid.UUID) -> dict[DocumentType, int]:
    rows = await session.scalars(
        select(DocumentSequence).where(DocumentSequence.business_id == business_id)
    )
    current = {DocumentType(r.document_type): r.next_number for r in rows}
    return {t: current.get(t, 1) for t in DocumentType}
