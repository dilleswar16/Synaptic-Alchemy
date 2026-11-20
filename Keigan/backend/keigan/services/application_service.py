"""Applications: list with summary counts, create / request, update, delete, readiness, go live, pause, access and platform identity."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic.alias_generators import to_camel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import AuthenticationMode, IntegrationMode, get_settings
from keigan.dtos.application_dtos import (
    AccessResponse,
    AccessUpdateRequest,
    AccessVerificationResponse,
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationSummaryResponse,
    ApplicationUpdateRequest,
    GroupVerificationResult,
    IncidentCreationPolicy,
    PlatformIdentityResponse,
    ReadinessResponse,
)
from keigan.entities.application_entities import Application, ApplicationComponent, MonitoredService
from keigan.entities.incident_entities import Incident
from keigan.exceptions.keigan_exceptions import AmbiguousGroupNameException, BusinessValidationException, ConflictException, ForbiddenException, IntegrationException, NotFoundException
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.application_readiness_service import ApplicationReadinessService
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.onboarding_service import GUID_PATTERN
from keigan.services.reference_release import release_references
from keigan.entities.status_values import ApplicationLifecycleStatus

logger = logging.getLogger(__name__)

DEFAULT_LOCALE_BY_REGION = {"JP": "ja", "CN": "zh-CN", "ES": "es", "MX": "es-MX", "NL": "nl", "FR": "fr"}
DEFAULT_TIME_ZONE_BY_REGION = {"JP": "Asia/Tokyo", "AU": "Australia/Sydney", "US": "America/New_York", "NL": "Europe/Amsterdam", "FR": "Europe/Paris", "MX": "America/Mexico_City"}
CLOSED_INCIDENT_STATUSES = ("resolved", "closed", "cancelled", "canceled")
LIVE_LIFECYCLE_STATUSES = (ApplicationLifecycleStatus.LIVE, ApplicationLifecycleStatus.PAUSED)


class ApplicationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.application_repository = BaseRepository(session, Application)
        self.authorization_service = AuthorizationService(session)
        self.readiness_service = ApplicationReadinessService(session)
        self.audit_service = AuditService(session)

    # ── Queries ────────────────────────────────────────────────────────────────
    async def list_applications(self, current_user: CurrentUser) -> list[ApplicationSummaryResponse]:
        readable_ids = await self.authorization_service.readable_application_ids(current_user)
        if not readable_ids:
            return []
        editable_ids = await self.authorization_service.editable_application_ids(current_user)
        applications = await self.application_repository.find_all(Application.application_id.in_(readable_ids), order_by=Application.application_name)
        component_types_by_application: dict[str, set[str]] = defaultdict(set)
        component_counts: dict[str, int] = defaultdict(int)
        for application_id, component_type in (await self.session.execute(select(ApplicationComponent.application_id, ApplicationComponent.component_type).where(ApplicationComponent.application_id.in_(readable_ids)))).all():
            component_types_by_application[application_id].add(component_type)
            component_counts[application_id] += 1
        service_counts = dict((await self.session.execute(select(MonitoredService.application_id, func.count()).where(MonitoredService.application_id.in_(readable_ids)).group_by(MonitoredService.application_id))).all())
        incident_counts = dict(
            (await self.session.execute(
                select(Incident.application_id, func.count()).where(Incident.application_id.in_(readable_ids), Incident.incident_status.not_in(CLOSED_INCIDENT_STATUSES)).group_by(Incident.application_id)
            )).all()
        )
        compliance_by_application = await self._slo_compliance_by_application(list(readable_ids))
        summaries: list[ApplicationSummaryResponse] = []
        for application in applications:
            summary = ApplicationSummaryResponse(
                **self._to_response(application, application.application_id in editable_ids).model_dump(),
                component_types=sorted(component_types_by_application.get(application.application_id, set())),
                component_count=component_counts.get(application.application_id, 0),
                service_count=int(service_counts.get(application.application_id, 0)),
                open_incident_count=int(incident_counts.get(application.application_id, 0)),
                slo_compliance_percentage=compliance_by_application.get(application.application_id),
            )
            if application.lifecycle_status not in LIVE_LIFECYCLE_STATUSES:
                readiness = await self.readiness_service.build_readiness(application)
                summary.required_total_count = len(readiness.required)
                summary.required_done_count = sum(1 for requirement in readiness.required if requirement.is_done)
            summaries.append(summary)
        return summaries

    async def _slo_compliance_by_application(self, application_ids: list[str]) -> dict[str, float]:
        try:
            from keigan.services.slo_service import SloService

            slo_rows = await SloService(self.session).summarize_slos(application_ids)
        except NotImplementedError:
            return {}
        except Exception:  # noqa: BLE001  (SLO data must never break the applications list)
            return {}
        statuses_by_application: dict[str, list[str]] = defaultdict(list)
        for slo_row in slo_rows:
            if slo_row.get("status") != "no_data":
                statuses_by_application[str(slo_row.get("applicationId"))].append(str(slo_row.get("status")))
        return {
            application_id: round(100.0 * sum(1 for status in statuses if status in ("healthy", "at_risk")) / len(statuses), 1)
            for application_id, statuses in statuses_by_application.items()
            if statuses
        }

    async def get_application(self, current_user: CurrentUser, application_id: str) -> ApplicationResponse:
        await self.authorization_service.ensure_application_reader(current_user, application_id)
        application = await self.application_repository.get_required(application_id, "application")
        return self._to_response(application, await self.authorization_service.can_edit_application(current_user, application_id))

    async def get_readiness(self, application_id: str) -> ReadinessResponse:
        application = await self.application_repository.get_required(application_id, "application")
        return await self.readiness_service.build_readiness(application)

    # ── Writes ─────────────────────────────────────────────────────────────────
    async def create_application(self, current_user: CurrentUser, request: ApplicationCreateRequest) -> ApplicationResponse:
        if await self.application_repository.exists(Application.application_code == request.application_code):
            raise ConflictException(f"The application code {request.application_code} is already used.")
        region_code = (request.region_code or "").upper() or None
        lifecycle_status = ApplicationLifecycleStatus.DRAFT if current_user.is_keigan_admin and request.lifecycle_status != ApplicationLifecycleStatus.REQUESTED else ApplicationLifecycleStatus.REQUESTED
        application = Application(
            application_name=request.application_name.strip(),
            application_code=request.application_code,
            application_description=request.application_description,
            business_unit_name=request.business_unit_name,
            region_code=region_code,
            primary_locale=request.primary_locale or DEFAULT_LOCALE_BY_REGION.get(region_code or "", "en"),
            time_zone_name=request.time_zone_name or DEFAULT_TIME_ZONE_BY_REGION.get(region_code or "", "UTC"),
            criticality_tier=request.criticality_tier,
            lifecycle_status=lifecycle_status,
            admin_group_name=self.settings.application_admin_group_name_for(request.application_code),
            reader_group_name=self.settings.application_reader_group_name_for(request.application_code),
            incident_creation_policy_json={"mode": "suggest", "minimum_score": 70, "assignment_group_name": None},
            created_by_user_principal_name=current_user.user_principal_name,
            updated_by_user_principal_name=current_user.user_principal_name,
        )
        await self._link_groups_in_entra(application)
        await self.application_repository.add(application)
        await self.audit_service.record(
            current_user,
            "application.request" if lifecycle_status == ApplicationLifecycleStatus.REQUESTED else "application.create",
            target_entity_type="application",
            target_entity_id=application.application_id,
            application_id=application.application_id,
            action_details={"applicationCode": application.application_code},
        )
        return self._to_response(application, current_user.is_keigan_admin)

    async def _link_groups_in_entra(self, application: Application) -> None:
        """With Entra sign-in only the group object ids grant access (H7), so look them up as soon as the application exists.
        Groups SailPoint has not provisioned yet are linked later by 'Check in Entra'; a Graph failure never blocks the request."""
        if self.settings.auth_mode != AuthenticationMode.ENTRA:
            return
        from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient

        graph_client = MicrosoftGraphClient(application_context.azure_credential_provider())
        for group_name, object_id_field in ((application.admin_group_name, "admin_group_object_id"), (application.reader_group_name, "reader_group_object_id")):
            try:
                group = await graph_client.find_group(group_name, None)
            except IntegrationException as lookup_error:
                logger.warning("Could not look up the Entra group %s for application %s: %s", group_name, application.application_code, lookup_error.detail)
                continue
            if group is not None:
                setattr(application, object_id_field, group["id"].lower())

    async def update_application(self, current_user: CurrentUser, application_id: str, request: ApplicationUpdateRequest) -> ApplicationResponse:
        await self.authorization_service.ensure_application_admin(current_user, application_id)
        application = await self.application_repository.get_required(application_id, "application")
        changes = request.model_dump(exclude_unset=True)
        if "lifecycle_status" in changes and changes["lifecycle_status"] is not None:
            self._apply_lifecycle_change(current_user, application, changes.pop("lifecycle_status"))
        else:
            changes.pop("lifecycle_status", None)
        if "incident_creation_policy" in changes:
            policy = changes.pop("incident_creation_policy")
            application.incident_creation_policy_json = policy
        if "onboarding_progress" in changes:
            application.onboarding_progress_json = changes.pop("onboarding_progress")
        for field_name, field_value in changes.items():
            if field_value is not None or field_name in ("application_description", "business_unit_name"):
                setattr(application, field_name, field_value)
        application.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "application.update", target_entity_type="application", target_entity_id=application_id, application_id=application_id,
            action_details={"changedFields": sorted(request.model_dump(exclude_unset=True).keys())},
        )
        return self._to_response(application, True)

    def _apply_lifecycle_change(self, current_user: CurrentUser, application: Application, new_status: str) -> None:
        if application.lifecycle_status in LIVE_LIFECYCLE_STATUSES:
            raise BusinessValidationException("A live application changes status through pause and resume.")
        if application.lifecycle_status == ApplicationLifecycleStatus.REQUESTED and not current_user.is_keigan_admin:
            raise ForbiddenException("Only Keigan admins can accept an onboarding request.")
        application.lifecycle_status = new_status

    async def delete_application(self, current_user: CurrentUser, application_id: str) -> None:
        await self.authorization_service.ensure_application_admin(current_user, application_id)
        application = await self.application_repository.get_required(application_id, "application")
        if application.lifecycle_status == ApplicationLifecycleStatus.LIVE or (application.lifecycle_status in LIVE_LIFECYCLE_STATUSES and not current_user.is_keigan_admin):
            raise BusinessValidationException("A live application cannot be deleted. Pause it first; a Keigan admin can then delete it.")
        await self.audit_service.record(
            current_user, "application.delete", target_entity_type="application", target_entity_id=application_id, application_id=application_id,
            action_details={"applicationCode": application.application_code},
        )
        await self._delete_rows_outside_the_cascade_path(application_id)
        await self.application_repository.delete(application)

    async def _delete_rows_outside_the_cascade_path(self, application_id: str) -> None:
        """Removes the application's rows the database cannot cascade: rows reachable through a second parent (SQL Server allows one
        cascade path per table, so those keys are NO ACTION) and the references to the application's services. Everything else
        (components, knowledge, alert sources, alerts, SLIs with their measurements, SLOs, signals, reports, stakeholders, incidents)
        cascades from the application row. Audit events and AI usage records are kept as history."""
        from sqlalchemy import delete, or_

        from keigan.entities.alert_entities import AlertGroup
        from keigan.entities.incident_entities import Conversation, Incident, IncidentCommunication, Investigation, InvestigationTimelineEvent, PostmortemReport
        from keigan.entities.notification_entities import NotificationDelivery, TeamsIncidentChat

        application_service_ids = list((await self.session.scalars(select(MonitoredService.service_id).where(MonitoredService.application_id == application_id))).all())
        await release_references(self.session, MonitoredService.service_id, application_service_ids)
        application_incident_ids = select(Incident.incident_id).where(Incident.application_id == application_id)
        application_investigation_ids = select(Investigation.investigation_id).where(Investigation.application_id == application_id)
        for delete_statement in (
            delete(MonitoredService).where(MonitoredService.application_id == application_id),
            *(delete(entity).where(or_(entity.incident_id.in_(application_incident_ids), entity.investigation_id.in_(application_investigation_ids)))
              for entity in (InvestigationTimelineEvent, IncidentCommunication, PostmortemReport, Conversation)),
            # Children first: these name the incident or investigation that is deleted next.
            *(delete(entity).where(entity.application_id == application_id) for entity in (NotificationDelivery, TeamsIncidentChat, AlertGroup)),
            delete(Investigation).where(Investigation.application_id == application_id),
        ):
            await self.session.execute(delete_statement)

    async def go_live(self, current_user: CurrentUser, application_id: str) -> ApplicationResponse:
        await self.authorization_service.ensure_application_admin(current_user, application_id)
        application = await self.application_repository.get_required(application_id, "application")
        if application.lifecycle_status == ApplicationLifecycleStatus.LIVE:
            return self._to_response(application, True)
        if self.settings.auth_mode == AuthenticationMode.ENTRA and not (application.admin_group_object_id and application.reader_group_object_id):
            raise BusinessValidationException(
                "The application's access groups are not linked to Entra yet, so nobody could open it after go-live. Run 'Check in Entra' on the Access step first."
            )
        readiness = await self.readiness_service.build_readiness(application)
        if not readiness.can_go_live:
            missing_keys = [requirement.requirement_key for requirement in readiness.required if not requirement.is_done]
            raise BusinessValidationException(
                "The application is not ready to go live yet.",
                field_errors=[{"field": requirement_key, "message": "Required step is not complete."} for requirement_key in missing_keys],
            )
        application.lifecycle_status = ApplicationLifecycleStatus.LIVE
        application.went_live_at = application.went_live_at or datetime.now(UTC)
        application.went_live_by_user_principal_name = application.went_live_by_user_principal_name or current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(current_user, "application.go_live", target_entity_type="application", target_entity_id=application_id, application_id=application_id)
        return self._to_response(application, True)

    async def pause_application(self, current_user: CurrentUser, application_id: str) -> ApplicationResponse:
        return await self._switch_live_status(current_user, application_id, from_status="live", to_status="paused", action_name="application.pause")

    async def resume_application(self, current_user: CurrentUser, application_id: str) -> ApplicationResponse:
        return await self._switch_live_status(current_user, application_id, from_status="paused", to_status="live", action_name="application.resume")

    async def _switch_live_status(self, current_user: CurrentUser, application_id: str, *, from_status: str, to_status: str, action_name: str) -> ApplicationResponse:
        await self.authorization_service.ensure_application_admin(current_user, application_id)
        application = await self.application_repository.get_required(application_id, "application")
        if application.lifecycle_status != from_status:
            raise BusinessValidationException(f"Only an application that is {from_status} can change to {to_status}.")
        application.lifecycle_status = to_status
        await self.session.flush()
        await self.audit_service.record(current_user, action_name, target_entity_type="application", target_entity_id=application_id, application_id=application_id)
        return self._to_response(application, True)

    # ── Access ─────────────────────────────────────────────────────────────────
    async def get_access(self, current_user: CurrentUser, application_id: str) -> AccessResponse:
        application = await self.application_repository.get_required(application_id, "application")
        return AccessResponse(
            admin_group_name=application.admin_group_name,
            admin_group_object_id=application.admin_group_object_id,
            reader_group_name=application.reader_group_name,
            reader_group_object_id=application.reader_group_object_id,
            members_available=self.settings.auth_mode == AuthenticationMode.ENTRA,
            sailpoint_instructions=(
                f"Request membership of {application.admin_group_name} (edit access) or {application.reader_group_name} (read-only access) in SailPoint. "
                "New members can sign in to Keigan as soon as SailPoint has provisioned the group in Entra ID."
            ),
            can_edit_group_names=current_user.is_keigan_admin,
        )

    async def update_access(self, current_user: CurrentUser, application_id: str, request: AccessUpdateRequest) -> AccessResponse:
        await self.authorization_service.ensure_application_admin(current_user, application_id)
        application = await self.application_repository.get_required(application_id, "application")
        changes = request.model_dump(exclude_unset=True)
        if ("admin_group_name" in changes or "reader_group_name" in changes) and not current_user.is_keigan_admin:
            raise ForbiddenException("Only Keigan admins can change group names.")
        for field_name in ("admin_group_name", "reader_group_name"):
            if changes.get(field_name):
                setattr(application, field_name, changes[field_name].strip())
        self._apply_group_object_id_changes(current_user, application, changes)
        await self.session.flush()
        await self.audit_service.record(
            current_user, "application.access_update", target_entity_type="application", target_entity_id=application_id, application_id=application_id,
            action_details={"changedFields": sorted(changes.keys())},
        )
        return await self.get_access(current_user, application_id)

    @staticmethod
    def _apply_group_object_id_changes(current_user: CurrentUser, application: Application, changes: dict[str, Any]) -> None:
        """With Entra sign-in the object ids decide who may open the application, so only Keigan admins may change them
        (the access check fills in missing ids). Sending the stored value again is not a change."""
        new_object_ids = {
            field_name: (changes[field_name] or "").strip().lower() or None
            for field_name in ("admin_group_object_id", "reader_group_object_id")
            if field_name in changes
        }
        changed_object_ids = {
            field_name: new_object_id for field_name, new_object_id in new_object_ids.items()
            if new_object_id != ((getattr(application, field_name) or "").lower() or None)
        }
        if changed_object_ids and not current_user.is_keigan_admin:
            raise ForbiddenException("Only Keigan admins can change the group object IDs. Run 'Check in Entra' to link the groups.")
        field_errors = [
            {"field": to_camel(field_name), "message": "Enter the group's object ID as a GUID (for example 3f2a9c1b-0d4e-4c7a-9b1f-2e8d6a5c4b30)."}
            for field_name, new_object_id in changed_object_ids.items()
            if new_object_id and not GUID_PATTERN.match(new_object_id)
        ]
        if field_errors:
            raise BusinessValidationException("A group object ID is not valid.", field_errors=field_errors)
        for field_name, new_object_id in changed_object_ids.items():
            setattr(application, field_name, new_object_id)

    async def verify_access_groups(self, current_user: CurrentUser, application_id: str) -> AccessVerificationResponse:
        """Check that the admin and reader groups exist (SailPoint has provisioned them) and who is in them — before owners sign in.
        Fills in missing group object IDs so sign-in also works when tokens carry only group IDs."""
        from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient
        from keigan.services.authentication_service import load_local_users

        application = await self.application_repository.get_required(application_id, "application")
        uses_entra = self.settings.auth_mode == AuthenticationMode.ENTRA
        graph_client = MicrosoftGraphClient(application_context.azure_credential_provider()) if uses_entra else None
        results: list[GroupVerificationResult] = []
        for role, name_field, object_id_field in (("admin", "admin_group_name", "admin_group_object_id"), ("reader", "reader_group_name", "reader_group_object_id")):
            group_name, stored_object_id = getattr(application, name_field), getattr(application, object_id_field)
            if graph_client is None:
                member_names = [user.display_name for user in load_local_users() if group_name.lower() in {name.lower() for name in user.group_names}]
                results.append(GroupVerificationResult(
                    role=role, group_name=group_name, exists=bool(member_names), member_count=len(member_names), sample_member_names=member_names[:5],
                    message="Checked against the local demo users (AUTH_MODE=local)." if member_names else "No local demo user is in this group.",
                ))
                continue
            try:
                group = await graph_client.find_group(group_name, stored_object_id)
                if group is None:
                    results.append(GroupVerificationResult(role=role, group_name=group_name, exists=False, object_id=stored_object_id,
                                                           message="Not found in Entra ID yet. Request it in SailPoint, then check again."))
                    continue
                member_count, member_names = await graph_client.describe_group_members(group["id"])
                object_id_saved = False
                if not stored_object_id:
                    setattr(application, object_id_field, group["id"])
                    object_id_saved = True
                name_note = "" if (group.get("displayName") or "").lower() == group_name.lower() else f" The object ID belongs to '{group.get('displayName')}', not '{group_name}'."
                results.append(GroupVerificationResult(
                    role=role, group_name=group_name, exists=True, object_id=group["id"], member_count=member_count, sample_member_names=member_names,
                    object_id_saved=object_id_saved, message=f"Found in Entra ID with {member_count} member(s).{name_note}",
                ))
            except AmbiguousGroupNameException as ambiguous_name:
                results.append(GroupVerificationResult(role=role, group_name=group_name, exists=None, object_id=stored_object_id, message=ambiguous_name.detail))
            except Exception as graph_error:  # noqa: BLE001 — reported to the admin, not a server error
                results.append(GroupVerificationResult(
                    role=role, group_name=group_name, exists=None, object_id=stored_object_id,
                    message=f"Could not check Entra ID: {str(graph_error)[:200]}. Keigan's identity needs the Microsoft Graph application permission GroupMember.Read.All.",
                ))
        await self.session.flush()
        await self.audit_service.record(current_user, "application.access_verify", target_entity_type="application", target_entity_id=application_id, application_id=application_id,
                                        action_details={result.role: result.exists for result in results})
        return AccessVerificationResponse(results=results, checked_at=datetime.now(UTC), directory="entra" if uses_entra else "local_demo_users")

    async def get_platform_identity(self) -> PlatformIdentityResponse:
        settings = self.settings
        keigan_identity = await application_context.azure_credential_provider().resolve_keigan_identity()
        return PlatformIdentityResponse(
            tenant_id=keigan_identity.tenant_id,
            client_id=keigan_identity.client_id,
            object_id=keigan_identity.object_id,
            display_name=keigan_identity.display_name,
            multi_tenant_client_id=settings.keigan_multi_tenant_app_client_id or None,
            is_simulated=settings.telemetry_mode == IntegrationMode.SIMULATED,
            is_complete=keigan_identity.is_complete,
            missing_values=list(keigan_identity.missing_values),
            identity_source=keigan_identity.source,
        )

    # ── Mapping ────────────────────────────────────────────────────────────────
    @staticmethod
    def _to_response(application: Application, can_edit: bool) -> ApplicationResponse:
        excluded_field_names = {"incident_creation_policy", "onboarding_progress", "can_edit"}
        response_values: dict[str, Any] = {
            field_name: getattr(application, field_name) for field_name in ApplicationResponse.model_fields if field_name not in excluded_field_names
        }
        return ApplicationResponse(
            **response_values,
            incident_creation_policy=IncidentCreationPolicy.model_validate(application.incident_creation_policy_json).model_dump(by_alias=True) if application.incident_creation_policy_json else None,
            onboarding_progress=application.onboarding_progress_json,
            can_edit=can_edit,
        )
