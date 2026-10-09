import uuid
from datetime import datetime

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
    downloadable: bool
