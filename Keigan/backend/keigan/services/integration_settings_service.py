"""Connections an application keeps: log tool connections (write-only secrets), CMDB / EI portal / knowledge API integrations,
EAI / CMDB record links and ServiceNow assignment groups."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import RESOURCES_DIRECTORY, IntegrationMode, get_settings
from keigan.dtos.onboarding_dtos import (
    ConnectionTestResponse,
    IntegrationResponse,
    IntegrationUpdateRequest,
    LogToolConnectionCreateRequest,
    LogToolConnectionResponse,
    LogToolConnectionUpdateRequest,
    RecordLinkCreateRequest,
    RecordLinkResponse,
    ServiceNowGroupResponse,
    ServiceNowGroupSearchResult,
)
from keigan.entities.application_entities import ApplicationRecordLink, ExternalIntegration, LogToolConnection, MonitoredService, ServiceLogSource
from keigan.entities.incident_entities import ServiceNowAssignmentGroup
from keigan.entities.platform_entities import StoredSecret
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ConflictException, NotFoundException
from keigan.integrations.log_tool_clients import PLACEHOLDER_TOOL_TYPES
from keigan.integrations.log_tool_endpoints import log_tool_endpoint_signature, log_tool_endpoint_urls
from keigan.integrations.secret_store import build_secret_name
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.utils.time_utils import utc_now

FIELD_SCHEMA_PATH = RESOURCES_DIRECTORY / "catalogs" / "integration_field_schemas.yaml"
# The field types the onboarding form knows how to draw; a catalog entry with another type is a mistake caught at load time.
KNOWN_INTEGRATION_FIELD_TYPES = frozenset({"text", "url", "select", "secret", "key_value_list", "textarea"})
DEMO_SERVICENOW_GROUP_NAMES = [
    "Global-Service-Desk", "Network-Operations-L2", "Database-Support-L2", "Platform-Engineering-SRE",
    "Mainframe-Operations", "Cloud-Infrastructure-L2", "Application-Support-JP", "Application-Support-AU",
]
MAXIMUM_SERVICENOW_GROUPS = 20
CREDENTIAL_REMOVED_MESSAGE = "The address or sign-in method changed, so the saved credential was removed. Enter the credential again."


def _camelize_keys(value: Any) -> Any:
    """Field schema keys become camelCase like every other API payload (``field_type`` to ``fieldType``); field *keys* such as ``base_url`` stay as data."""
    if isinstance(value, dict):
        return {to_camel(str(key)): _camelize_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize_keys(item) for item in value]
    return value


@lru_cache(maxsize=1)
def load_integration_field_schemas() -> dict[str, Any]:
    raw_kinds = (yaml.safe_load(FIELD_SCHEMA_PATH.read_text(encoding="utf-8")) or {}).get("integration_kinds", {})
    field_schemas = {
        integration_kind: {**{to_camel(key): _camelize_keys(value) for key, value in schema.items() if key != "fields"}, "fields": [_camelize_keys(field) for field in schema.get("fields", [])]}
        for integration_kind, schema in raw_kinds.items()
    }
    for integration_kind, schema in field_schemas.items():
        for field in schema["fields"]:
            if field.get("fieldType") not in KNOWN_INTEGRATION_FIELD_TYPES:
                raise ValueError(f"{FIELD_SCHEMA_PATH.name}: field '{field.get('key')}' of '{integration_kind}' has the unknown type '{field.get('fieldType')}'.")
    return field_schemas


class IntegrationSettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.audit_service = AuditService(session)
        self.connection_repository = BaseRepository(session, LogToolConnection)

    # ── Log tool connections ───────────────────────────────────────────────────
    async def list_log_tool_connections(self, application_id: str) -> list[LogToolConnectionResponse]:
        connections = await self.connection_repository.find_all(LogToolConnection.application_id == application_id, order_by=LogToolConnection.connection_name)
        return [await self._to_connection_response(connection) for connection in connections]

    async def create_log_tool_connection(self, current_user: CurrentUser, application_id: str, request: LogToolConnectionCreateRequest) -> LogToolConnectionResponse:
        await self._ensure_endpoints_allowed(request.tool_type, request.endpoint_url, request.connection_configuration)
        connection = LogToolConnection(
            application_id=application_id,
            tool_type=request.tool_type,
            connection_name=request.connection_name.strip(),
            endpoint_url=request.endpoint_url,
            authentication_method=request.authentication_method,
            connection_configuration_json=request.connection_configuration or {},
            connection_status="reader_not_available" if request.tool_type in PLACEHOLDER_TOOL_TYPES else "not_tested",
            last_test_message="Reader in development — details saved." if request.tool_type in PLACEHOLDER_TOOL_TYPES else None,
            created_by_user_principal_name=current_user.user_principal_name,
            updated_by_user_principal_name=current_user.user_principal_name,
        )
        if request.credential_value:
            connection.credential_secret_name = build_secret_name(f"logtool-{request.tool_type}")
            await application_context.secret_store().set_secret(connection.credential_secret_name, request.credential_value, f"{request.tool_type} credential for application {application_id}")
        await self.connection_repository.add(connection)
        await self.audit_service.record(
            current_user, "log_tool.create", target_entity_type="log_tool_connection", target_entity_id=connection.log_tool_connection_id, application_id=application_id,
            action_details={"toolType": request.tool_type, "credentialProvided": bool(request.credential_value)},
        )
        return await self._to_connection_response(connection)

    async def update_log_tool_connection(
        self, current_user: CurrentUser, application_id: str, connection_id: str, request: LogToolConnectionUpdateRequest
    ) -> LogToolConnectionResponse:
        connection = await self._get_connection(application_id, connection_id)
        changes = request.model_dump(exclude_unset=True)
        credential_value = changes.pop("credential_value", None)
        signature_before = self._endpoint_signature(connection)
        if "connection_configuration" in changes:
            connection.connection_configuration_json = changes.pop("connection_configuration") or {}
        for field_name, field_value in changes.items():
            if field_value is not None:
                setattr(connection, field_name, field_value)
        credential_cleared = False
        if self._endpoint_signature(connection) != signature_before:
            await self._ensure_endpoints_allowed(connection.tool_type, connection.endpoint_url, connection.connection_configuration_json)
            credential_cleared = not credential_value and await self._clear_credential(connection)
        if credential_value:
            connection.credential_secret_name = connection.credential_secret_name or build_secret_name(f"logtool-{connection.tool_type}")
            await application_context.secret_store().set_secret(connection.credential_secret_name, credential_value, f"{connection.tool_type} credential for application {application_id}")
        if connection.tool_type not in PLACEHOLDER_TOOL_TYPES:
            connection.connection_status = "not_tested"
        connection.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "log_tool.update", target_entity_type="log_tool_connection", target_entity_id=connection_id, application_id=application_id,
            action_details={"changedFields": sorted(request.model_dump(exclude_unset=True).keys() - {"credential_value"}), "credentialRotated": bool(credential_value), "credentialCleared": credential_cleared},
        )
        return await self._to_connection_response(connection)

    async def delete_log_tool_connection(self, current_user: CurrentUser, application_id: str, connection_id: str) -> None:
        connection = await self._get_connection(application_id, connection_id)
        used_by = await self._service_names_using(connection_id)
        if used_by:
            raise ConflictException(f"The connection is used by {', '.join(used_by[:5])}. Remove it from those services first.")
        if connection.credential_secret_name:
            try:
                await application_context.secret_store().delete_secret(connection.credential_secret_name)
            except NotFoundException:
                pass
        await self.audit_service.record(
            current_user, "log_tool.delete", target_entity_type="log_tool_connection", target_entity_id=connection_id, application_id=application_id,
            action_details={"connectionName": connection.connection_name},
        )
        await self.connection_repository.delete(connection)

    async def test_log_tool_connection(self, current_user: CurrentUser, application_id: str, connection_id: str) -> ConnectionTestResponse:
        connection = await self._get_connection(application_id, connection_id)
        if connection.tool_type in PLACEHOLDER_TOOL_TYPES:
            connection.connection_status = "reader_not_available"
            return ConnectionTestResponse(succeeded=False, message="Reader in development — details are saved, testing is not available yet.", reader_not_available=True)
        test_result = await application_context.telemetry_gateway().test_log_tool_connection(connection)
        connection.connection_status = "connected" if test_result.succeeded else "failed"
        connection.last_tested_at = utc_now()
        connection.last_test_message = test_result.message
        connection.newest_log_timestamp_seen_at = test_result.newest_log_timestamp or connection.newest_log_timestamp_seen_at
        await self.audit_service.record(
            current_user, "log_tool.test", target_entity_type="log_tool_connection", target_entity_id=connection_id, application_id=application_id,
            action_details={"succeeded": test_result.succeeded},
        )
        return ConnectionTestResponse(
            succeeded=test_result.succeeded, message=test_result.message, newest_log_timestamp=test_result.newest_log_timestamp,
            reader_not_available=bool(test_result.details.get("readerNotAvailable")),
        )

    @staticmethod
    def _endpoint_signature(connection: LogToolConnection) -> tuple:
        return log_tool_endpoint_signature(connection.tool_type, connection.endpoint_url, connection.connection_configuration_json, connection.authentication_method)

    @staticmethod
    async def _ensure_endpoints_allowed(tool_type: str, endpoint_url: str | None, connection_configuration: dict[str, Any] | None) -> None:
        """Keigan will call these addresses with the saved credential (V16). Tools without a reader are only stored, never called."""
        if tool_type in PLACEHOLDER_TOOL_TYPES:
            return
        for field_name, url in log_tool_endpoint_urls(tool_type, endpoint_url, connection_configuration):
            await application_context.outbound_url_policy().ensure_allowed(url, field_name=field_name)

    @staticmethod
    async def _clear_credential(connection: LogToolConnection) -> bool:
        """The credential was entered for the old address or sign-in method: delete it so it cannot be sent somewhere else (V16)."""
        if not connection.credential_secret_name:
            return False
        try:
            await application_context.secret_store().delete_secret(connection.credential_secret_name)
        except NotFoundException:
            pass
        connection.credential_secret_name = None
        connection.last_test_message = CREDENTIAL_REMOVED_MESSAGE
        connection.connection_status = "not_tested"
        return True

    async def _get_connection(self, application_id: str, connection_id: str) -> LogToolConnection:
        connection = await self.connection_repository.get_required(connection_id, "log tool connection")
        if connection.application_id != application_id:
            raise NotFoundException("The log tool connection was not found.")
        return connection

    async def _service_names_using(self, connection_id: str) -> list[str]:
        rows = await self.session.scalars(
            select(MonitoredService.service_name)
            .join(ServiceLogSource, ServiceLogSource.service_id == MonitoredService.service_id)
            .where(ServiceLogSource.log_tool_connection_id == connection_id)
            .distinct()
        )
        return sorted(rows.all())

    async def _to_connection_response(self, connection: LogToolConnection) -> LogToolConnectionResponse:
        secret_row = await self.session.get(StoredSecret, connection.credential_secret_name) if connection.credential_secret_name else None
        return LogToolConnectionResponse(
            log_tool_connection_id=connection.log_tool_connection_id,
            application_id=connection.application_id,
            tool_type=connection.tool_type,
            connection_name=connection.connection_name,
            endpoint_url=connection.endpoint_url,
            authentication_method=connection.authentication_method,
            connection_configuration=connection.connection_configuration_json,
            has_credential=bool(connection.credential_secret_name),
            credential_set_at=(secret_row.last_rotated_at or secret_row.updated_at) if secret_row else (connection.updated_at if connection.credential_secret_name else None),
            connection_status=connection.connection_status,
            last_tested_at=connection.last_tested_at,
            last_test_message=connection.last_test_message,
            newest_log_timestamp_seen_at=connection.newest_log_timestamp_seen_at,
            reader_available=connection.tool_type not in PLACEHOLDER_TOOL_TYPES,
            used_by_service_names=await self._service_names_using(connection.log_tool_connection_id),
        )

    # ── Generic integrations ───────────────────────────────────────────────────
    @staticmethod
    def get_field_schemas() -> dict[str, Any]:
        return load_integration_field_schemas()

    async def get_integration(self, application_id: str, integration_kind: str) -> IntegrationResponse:
        schema = self._schema_for(integration_kind)
        row = await self.session.scalar(select(ExternalIntegration).where(ExternalIntegration.application_id == application_id, ExternalIntegration.integration_kind == integration_kind))
        return self._to_integration_response(integration_kind, schema, row)

    async def list_integrations(self, application_id: str) -> list[IntegrationResponse]:
        return [await self.get_integration(application_id, integration_kind) for integration_kind in load_integration_field_schemas()]

    async def save_integration(self, current_user: CurrentUser, application_id: str, integration_kind: str, request: IntegrationUpdateRequest) -> IntegrationResponse:
        schema = self._schema_for(integration_kind)
        configuration = request.integration_configuration or {}
        field_errors = [
            {"field": f"integrationConfiguration.{field['key']}", "message": "This field is required."}
            for field in schema["fields"]
            if field.get("required") and not configuration.get(field["key"])
        ]
        if field_errors:
            raise BusinessValidationException("Some integration details are missing.", field_errors=field_errors)
        row = await self.session.scalar(select(ExternalIntegration).where(ExternalIntegration.application_id == application_id, ExternalIntegration.integration_kind == integration_kind))
        if row is None:
            row = ExternalIntegration(application_id=application_id, integration_kind=integration_kind, created_by_user_principal_name=current_user.user_principal_name)
            self.session.add(row)
        # Only plain fields from the catalog are kept: a secret never lands in the configuration JSON, and unknown keys carry no meaning.
        stored_keys = {field["key"] for field in schema["fields"] if field["fieldType"] != "secret"}
        row.integration_configuration_json = {key: value for key, value in configuration.items() if key in stored_keys}
        if request.credential_value:
            row.credential_secret_name = row.credential_secret_name or build_secret_name(f"integration-{integration_kind}")
            await application_context.secret_store().set_secret(row.credential_secret_name, request.credential_value, f"{integration_kind} credential for application {application_id}")
        row.integration_notes = request.integration_notes
        row.integration_status = "configured" if schema.get("readerAvailable") else "saved_reader_in_development"
        row.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "integration.save", target_entity_type="external_integration", target_entity_id=row.external_integration_id, application_id=application_id,
            action_details={"integrationKind": integration_kind, "credentialProvided": bool(request.credential_value)},
        )
        return self._to_integration_response(integration_kind, schema, row)

    @staticmethod
    def _schema_for(integration_kind: str) -> dict[str, Any]:
        schema = load_integration_field_schemas().get(integration_kind)
        if schema is None:
            raise NotFoundException(f"The integration kind {integration_kind} is not known.")
        return schema

    @staticmethod
    def _to_integration_response(integration_kind: str, schema: dict[str, Any], row: ExternalIntegration | None) -> IntegrationResponse:
        return IntegrationResponse(
            integration_kind=integration_kind,
            display_name=schema["displayName"],
            purpose=schema["purpose"],
            reader_available=bool(schema.get("readerAvailable")),
            fields=schema["fields"],
            integration_configuration=(row.integration_configuration_json or {}) if row else {},
            has_credential=bool(row and row.credential_secret_name),
            integration_status=row.integration_status if row else "not_set_up",
            integration_notes=row.integration_notes if row else None,
            updated_at=row.updated_at if row else None,
        )

    # ── Record links ───────────────────────────────────────────────────────────
    async def list_record_links(self, application_id: str) -> list[RecordLinkResponse]:
        links = await BaseRepository(self.session, ApplicationRecordLink).find_all(ApplicationRecordLink.application_id == application_id, order_by=ApplicationRecordLink.created_at)
        return [RecordLinkResponse.model_validate(link) for link in links]

    async def add_record_link(self, current_user: CurrentUser, application_id: str, request: RecordLinkCreateRequest) -> RecordLinkResponse:
        identifier = request.record_identifier.strip().upper()
        repository = BaseRepository(self.session, ApplicationRecordLink)
        if await repository.exists(ApplicationRecordLink.application_id == application_id, ApplicationRecordLink.record_system == request.record_system, ApplicationRecordLink.record_identifier == identifier):
            raise ConflictException("This record is already linked.")
        link = await repository.add(ApplicationRecordLink(application_id=application_id, record_system=request.record_system, record_identifier=identifier))
        await self.audit_service.record(
            current_user, "record_link.add", target_entity_type="application_record_link", target_entity_id=link.application_record_link_id, application_id=application_id,
            action_details={"recordSystem": request.record_system, "recordIdentifier": identifier},
        )
        return RecordLinkResponse.model_validate(link)

    async def delete_record_link(self, current_user: CurrentUser, application_id: str, record_link_id: str) -> None:
        repository = BaseRepository(self.session, ApplicationRecordLink)
        link = await repository.get_required(record_link_id, "record link")
        if link.application_id != application_id:
            raise NotFoundException("The record link was not found.")
        await self.audit_service.record(
            current_user, "record_link.delete", target_entity_type="application_record_link", target_entity_id=record_link_id, application_id=application_id,
            action_details={"recordIdentifier": link.record_identifier},
        )
        await repository.delete(link)

    # ── ServiceNow assignment groups ───────────────────────────────────────────
    async def list_servicenow_groups(self, application_id: str) -> list[ServiceNowGroupResponse]:
        groups = await BaseRepository(self.session, ServiceNowAssignmentGroup).find_all(ServiceNowAssignmentGroup.application_id == application_id, order_by=ServiceNowAssignmentGroup.group_name)
        return [ServiceNowGroupResponse.model_validate(group) for group in groups]

    async def replace_servicenow_groups(self, current_user: CurrentUser, application_id: str, group_names: list[str]) -> list[ServiceNowGroupResponse]:
        desired_names = list(dict.fromkeys(name.strip() for name in group_names if name.strip()))
        if len(desired_names) > MAXIMUM_SERVICENOW_GROUPS:
            raise BusinessValidationException(f"Add at most {MAXIMUM_SERVICENOW_GROUPS} assignment groups.")
        existing_groups = list((await self.session.scalars(select(ServiceNowAssignmentGroup).where(ServiceNowAssignmentGroup.application_id == application_id))).all())
        existing_by_name = {group.group_name.lower(): group for group in existing_groups}
        known_names = {name.lower() for name in await self._known_servicenow_group_names()}
        desired_lower = {name.lower() for name in desired_names}
        for group in existing_groups:
            if group.group_name.lower() not in desired_lower:
                await self.session.delete(group)
        for name in desired_names:
            if name.lower() not in existing_by_name:
                is_verified = self.settings.servicenow_mode == IntegrationMode.SIMULATED and name.lower() in known_names
                self.session.add(ServiceNowAssignmentGroup(application_id=application_id, group_name=name, verification_status="verified" if is_verified else "unverified"))
        await self.session.flush()
        await self.audit_service.record(current_user, "servicenow_groups.update", application_id=application_id, action_details={"groupNames": desired_names})
        return await self.list_servicenow_groups(application_id)

    async def search_servicenow_groups(self, query_text: str) -> list[ServiceNowGroupSearchResult]:
        needle = query_text.strip().lower()
        known_names = await self._known_servicenow_group_names()
        return [
            ServiceNowGroupSearchResult(group_name=name, is_verified=self.settings.servicenow_mode == IntegrationMode.SIMULATED)
            for name in known_names
            if needle in name.lower()
        ][:20]

    async def _known_servicenow_group_names(self) -> list[str]:
        used_names = (await self.session.scalars(select(ServiceNowAssignmentGroup.group_name).distinct())).all()
        return sorted({*used_names, *DEMO_SERVICENOW_GROUP_NAMES})
