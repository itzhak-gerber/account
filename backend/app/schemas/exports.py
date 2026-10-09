import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models import ExportStatus


class DataExportOut(BaseModel):
    id: uuid.UUID
    status: ExportStatus
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    size: int | None
    documents: int | None
    date_from: date | None
    date_to: date | None
    downloadable: bool


class ExportRequest(BaseModel):
    """Range of the uniform-format file, by document date (default: everything until today)."""

    date_from: date | None = None
    date_to: date | None = None
