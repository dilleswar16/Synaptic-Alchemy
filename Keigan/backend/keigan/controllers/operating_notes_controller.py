"""Operating notes endpoints: read and replace the application team's guidance for the AI."""

from fastapi import APIRouter, Depends

from keigan.config.database_config import provide
from keigan.dtos.operating_notes_dtos import OperatingNotesResponse, OperatingNotesUpdateRequest
from keigan.security.current_user import CurrentUser, require_application_admin, require_application_reader
from keigan.services.operating_notes_service import OperatingNotesService

router = APIRouter(prefix="/api", tags=["Applications"])


@router.get("/applications/{application_id}/operating-notes", response_model=OperatingNotesResponse)
async def get_operating_notes(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_reader),
    operating_notes_service: OperatingNotesService = Depends(provide(OperatingNotesService)),
) -> OperatingNotesResponse:
    return await operating_notes_service.get_notes(current_user, application_id)


@router.put("/applications/{application_id}/operating-notes", response_model=OperatingNotesResponse)
async def update_operating_notes(
    application_id: str,
    request: OperatingNotesUpdateRequest,
    current_user: CurrentUser = Depends(require_application_admin),
    operating_notes_service: OperatingNotesService = Depends(provide(OperatingNotesService)),
) -> OperatingNotesResponse:
    """Notes are trimmed; an empty value clears them; more than the configured maximum answers 422 with a field error."""
    return await operating_notes_service.update_notes(current_user, application_id, request.text)
