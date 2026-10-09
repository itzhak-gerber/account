import uuid
from urllib.parse import quote

from fastapi import APIRouter, status
from fastapi.responses import Response

from app.auth.principal import CurrentBusiness, DbSession
from app.core.db import commit
from app.schemas.exports import DataExportOut, ExportRequest
from app.services import exports

router = APIRouter(prefix="/businesses/{business_id}/exports", tags=["exports"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def request_export(
    ctx: CurrentBusiness, session: DbSession, data: ExportRequest | None = None
) -> DataExportOut:
    """Start building a ZIP of all the business's data, with the uniform-format file for the
    given range; poll the list until it is ready."""
    data = data or ExportRequest()
    result = await exports.request(session, ctx, date_from=data.date_from, date_to=data.date_to)
    await commit(session)
    return DataExportOut.model_validate(result)


@router.get("")
async def list_exports(ctx: CurrentBusiness, session: DbSession) -> list[DataExportOut]:
    return [DataExportOut.model_validate(e) for e in await exports.list_exports(session, ctx)]


@router.get("/{export_id}/download")
async def download_export(
    export_id: uuid.UUID, ctx: CurrentBusiness, session: DbSession
) -> Response:
    content, name = await exports.download(session, ctx, export_id)
    await commit(session)
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "no-store",
        },
    )
