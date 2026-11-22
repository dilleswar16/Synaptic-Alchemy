"""Operating notes: a short note an application's team writes for the AI (which services carry revenue, which alerts are usually noise, what a quiet night looks like).

The notes are guidance for explanations, never evidence, and they change no alert rule or noise policy. Readers of the application can read them; Keigan admins
and the application's admin group can change them. Every change is audited with who and the old and new length (the audit trail keeps no before and after text).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.dtos.operating_notes_dtos import OperatingNotesResponse
from keigan.entities.application_entities import Application
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.utils.time_utils import utc_now

OPERATING_NOTES_AUDIT_ACTION = "application.operating_notes_update"


def normalize_operating_notes(text: str) -> str:
    """Trimmed, with Windows line breaks stored as one newline so the length matches what a browser text box counts."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


class OperatingNotesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.authorization_service = AuthorizationService(session)

    async def get_notes(self, current_user: CurrentUser, application_id: str) -> OperatingNotesResponse:
        await self.authorization_service.ensure_application_reader(current_user, application_id)
        return self._to_response(await self._load_application(application_id))

    async def update_notes(self, current_user: CurrentUser, application_id: str, text: str) -> OperatingNotesResponse:
        await self.authorization_service.ensure_application_admin(current_user, application_id)
        application = await self._load_application(application_id)
        new_text = normalize_operating_notes(text)
        maximum_characters = self.settings.application_operating_notes_maximum_characters
        if len(new_text) > maximum_characters:
            raise BusinessValidationException(
                "The operating notes are too long.",
                field_errors=[{"field": "text", "message": f"Operating notes can have at most {maximum_characters} characters; these have {len(new_text)}."}],
            )
        previous_text = application.operating_notes_text or ""
        if new_text == previous_text:
            return self._to_response(application)
        application.operating_notes_text = new_text or None
        application.operating_notes_updated_at = utc_now()
        application.operating_notes_updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await AuditService(self.session).record(
            current_user, OPERATING_NOTES_AUDIT_ACTION, target_entity_type="application", target_entity_id=application_id, application_id=application_id,
            action_details={"previousLength": len(previous_text), "newLength": len(new_text)},
        )
        return self._to_response(application)

    async def _load_application(self, application_id: str) -> Application:
        application = await self.session.get(Application, application_id)
        if application is None:
            raise NotFoundException("The application was not found.")
        return application

    def _to_response(self, application: Application) -> OperatingNotesResponse:
        return OperatingNotesResponse(
            text=application.operating_notes_text or "", maximum_characters=self.settings.application_operating_notes_maximum_characters,
            updated_at=application.operating_notes_updated_at, updated_by=application.operating_notes_updated_by_user_principal_name,
        )
