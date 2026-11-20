"""Alert sources: creation and secrets, public intake, setup instructions, Azure rule discovery, mapping preview, test alerts and the live listener."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.dtos.alert_dtos import (
    AlertSourceCreatedResponse, AlertSourceCreateRequest, AlertSourceResponse, AlertSourceUpdateRequest, AzureAlertRuleResponse, AzureAlertRulesResponse, MappingPreviewRequest,
    MappingPreviewResponse, RecentAlertEventResponse, SecretRotationResponse, SetupCodeBlock, SetupInstructionsResponse, SetupTab, TestAlertResponse,
)
from keigan.dtos.common_dtos import ApiModel
from keigan.entities.alert_entities import Alert, AlertEvent, AlertGroup, AlertSource
from keigan.entities.application_entities import Application, ApplicationComponent, MonitoredService
from keigan.exceptions.keigan_exceptions import AuthenticationException, BusinessValidationException, NotFoundException
from keigan.integrations.secret_store import build_secret_name
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
from keigan.security.current_user import CurrentUser
from keigan.security.security_middleware import rate_limiter
from keigan.services import alert_rules
from keigan.services.alert_pipeline_service import AlertPipelineService
from keigan.services.audit_service import AuditService
from keigan.utils.json_path_utils import list_json_paths, read_json_path
from keigan.utils.pii_masker import PiiMasker
from keigan.workers.job_queue import JobQueue

SECRET_PREFIX = "kgn_"
SECRET_ROTATION_OVERLAP = timedelta(hours=24)
INTERNAL_SOURCE_TOOL = "keigan_slo"
FIELD_NAME_HINTS = {
    "ruleName": ["rulename", "rule_name", "alertname", "alert_name", "title", "check", "name"], "ruleId": ["ruleid", "rule_id", "rule"],
    "externalId": ["alertid", "alert_id", "incidentid", "uuid", "fingerprint", "id"], "status": ["status", "state", "condition"], "severity": ["severity", "priority", "level"],
    "resourceRef": ["resource", "host", "entity", "target", "instance"], "serviceHint": ["service", "application", "app", "namespace", "component"],
    "summary": ["summary", "message", "text", "reason"], "description": ["description", "details"], "startedAt": ["started", "firedat", "timestamp", "time", "date", "created"],
    "link": ["url", "link"], "environment": ["environment", "env"],
}


def hash_secret(secret_value: str) -> str:
    return hashlib.sha256(secret_value.encode("utf-8")).hexdigest()


async def store_webhook_secret(secret_value: str, application_id: str) -> str:
    """Keep the plaintext webhook secret (the HMAC signing key) in the secret store and return its generated name. Only the name goes in the database."""
    secret_name = build_secret_name("alert-webhook")
    await application_context.secret_store().set_secret(secret_name, secret_value, f"Alert webhook secret for application {application_id}")
    return secret_name


class AlertSourceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    # ── Helpers ────────────────────────────────────────────────────────────────
    def webhook_url(self, alert_source_id: str, secret_value: str | None = None, include_token: bool = False) -> str:
        base_url = f"{self.settings.public_base_url.rstrip('/')}/api/alerts/in/{alert_source_id}"
        return f"{base_url}?token={secret_value or '<YOUR_SECRET>'}" if include_token else base_url

    async def _get_source(self, application_id: str, alert_source_id: str) -> AlertSource:
        source = await self.session.get(AlertSource, alert_source_id)
        if source is None or source.application_id != application_id or source.source_tool == INTERNAL_SOURCE_TOOL:
            raise NotFoundException("Alert source not found.")
        return source

    async def _to_response(self, source: AlertSource) -> AlertSourceResponse:
        since = alert_rules.utc_now() - timedelta(days=7)
        alert_count = await self.session.scalar(select(func.count()).select_from(Alert).where(Alert.alert_source_id == source.alert_source_id, Alert.first_seen_at >= since)) or 0
        group_ids = select(Alert.alert_group_id).where(Alert.alert_source_id == source.alert_source_id, Alert.first_seen_at >= since, Alert.alert_group_id.is_not(None)).distinct()
        group_count = await self.session.scalar(select(func.count()).select_from(group_ids.subquery())) or 0
        investigated_count = await self.session.scalar(select(func.count()).select_from(AlertGroup).where(AlertGroup.alert_group_id.in_(group_ids), AlertGroup.investigation_id.is_not(None))) or 0
        return AlertSourceResponse(
            alert_source_id=source.alert_source_id, application_id=source.application_id, source_tool=source.source_tool, source_name=source.source_name, source_status=source.source_status,
            webhook_url=self.webhook_url(source.alert_source_id), field_mapping=source.field_mapping_json, severity_mapping=source.severity_mapping_json, service_mapping=source.service_mapping_json,
            last_received_at=source.last_received_at, received_alert_count=source.received_alert_count, authentication_failure_count=source.authentication_failure_count,
            previous_secret_valid_until=source.previous_secret_valid_until if source.previous_secret_valid_until and source.previous_secret_valid_until > alert_rules.utc_now() else None,
            seven_day_alert_count=alert_count, seven_day_group_count=group_count, seven_day_investigated_count=investigated_count, created_at=source.created_at,
        )

    # ── CRUD ───────────────────────────────────────────────────────────────────
    async def list_sources(self, application_id: str) -> list[AlertSourceResponse]:
        sources = (await self.session.scalars(select(AlertSource).where(AlertSource.application_id == application_id, AlertSource.source_tool != INTERNAL_SOURCE_TOOL).order_by(AlertSource.created_at))).all()
        return [await self._to_response(source) for source in sources]

    async def create_source(self, current_user: CurrentUser, application_id: str, request: AlertSourceCreateRequest) -> AlertSourceCreatedResponse:
        secret_value = SECRET_PREFIX + secrets.token_urlsafe(32)
        secret_name = await store_webhook_secret(secret_value, application_id)  # before any write in this session: the secret store commits in its own session
        source = AlertSource(
            application_id=application_id, source_tool=request.source_tool, source_name=request.source_name.strip(), webhook_secret_hash=hash_secret(secret_value), webhook_secret_name=secret_name,
            field_mapping_json=request.field_mapping, severity_mapping_json=request.severity_mapping, service_mapping_json=request.service_mapping,
            created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name,
        )
        self.session.add(source)
        await self.session.flush()
        await AuditService(self.session).record(current_user, "alert_source.create", target_entity_type="alert_source", target_entity_id=source.alert_source_id, application_id=application_id, action_details={"tool": request.source_tool, "name": source.source_name})
        instructions = await self.build_setup_instructions(source, secret_value)
        return AlertSourceCreatedResponse(alert_source=await self._to_response(source), webhook_url=self.webhook_url(source.alert_source_id, secret_value, include_token=True), webhook_secret=secret_value, setup_instructions=instructions)

    async def update_source(self, current_user: CurrentUser, application_id: str, alert_source_id: str, request: AlertSourceUpdateRequest) -> AlertSourceResponse:
        source = await self._get_source(application_id, alert_source_id)
        provided = request.model_fields_set
        if request.source_name is not None:
            source.source_name = request.source_name.strip()
        if "field_mapping" in provided:
            source.field_mapping_json = request.field_mapping
        if "severity_mapping" in provided:
            source.severity_mapping_json = request.severity_mapping
        if "service_mapping" in provided:
            source.service_mapping_json = request.service_mapping
        if request.is_paused is not None:
            source.source_status = "paused" if request.is_paused else ("receiving" if source.last_received_at else "waiting_for_first_alert")
        source.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "alert_source.update", target_entity_type="alert_source", target_entity_id=alert_source_id, application_id=application_id, action_details=request.model_dump(exclude_none=True, by_alias=False))
        return await self._to_response(source)

    async def delete_source(self, current_user: CurrentUser, application_id: str, alert_source_id: str) -> None:
        source = await self._get_source(application_id, alert_source_id)
        for secret_name in (source.webhook_secret_name, source.previous_webhook_secret_name):
            await self._delete_stored_secret(secret_name)
        await self.session.delete(source)
        await AuditService(self.session).record(current_user, "alert_source.delete", target_entity_type="alert_source", target_entity_id=alert_source_id, application_id=application_id, action_details={"name": source.source_name})

    async def rotate_secret(self, current_user: CurrentUser, application_id: str, alert_source_id: str) -> SecretRotationResponse:
        source = await self._get_source(application_id, alert_source_id)
        new_secret = SECRET_PREFIX + secrets.token_urlsafe(32)
        new_secret_name = await store_webhook_secret(new_secret, application_id)
        await self._delete_stored_secret(source.previous_webhook_secret_name)  # the secret from two rotations ago is no longer accepted
        source.previous_webhook_secret_hash = source.webhook_secret_hash
        source.previous_webhook_secret_name = source.webhook_secret_name
        source.previous_secret_valid_until = alert_rules.utc_now() + SECRET_ROTATION_OVERLAP
        source.webhook_secret_hash = hash_secret(new_secret)
        source.webhook_secret_name = new_secret_name
        await AuditService(self.session).record(current_user, "alert_source.rotate_secret", target_entity_type="alert_source", target_entity_id=alert_source_id, application_id=application_id)
        return SecretRotationResponse(alert_source=await self._to_response(source), webhook_url=self.webhook_url(alert_source_id, new_secret, include_token=True), webhook_secret=new_secret, previous_secret_valid_until=source.previous_secret_valid_until)

    @staticmethod
    async def _delete_stored_secret(secret_name: str | None) -> None:
        if not secret_name:
            return
        try:
            await application_context.secret_store().delete_secret(secret_name)
        except NotFoundException:
            pass

    async def get_or_create_internal_source(self, application_id: str) -> AlertSource:
        source = await self.session.scalar(select(AlertSource).where(AlertSource.application_id == application_id, AlertSource.source_tool == INTERNAL_SOURCE_TOOL).limit(1))
        if source is None:
            source = AlertSource(application_id=application_id, source_tool=INTERNAL_SOURCE_TOOL, source_name="Keigan SLO burn alerts", webhook_secret_hash=hash_secret(secrets.token_urlsafe(32)), source_status="receiving", created_by_user_principal_name="system:keigan")
            self.session.add(source)
            await self.session.flush()
        return source

    async def get_or_create_simulation_source(self, application_id: str) -> AlertSource:
        source = await self.session.scalar(select(AlertSource).where(AlertSource.application_id == application_id, AlertSource.source_tool == "azure_monitor").order_by(AlertSource.created_at).limit(1))
        if source is None:
            source = AlertSource(application_id=application_id, source_tool="azure_monitor", source_name="Azure Monitor (simulated)", webhook_secret_hash=hash_secret(secrets.token_urlsafe(32)), created_by_user_principal_name="system:keigan")
            self.session.add(source)
            await self.session.flush()
        return source

    # ── Public intake ──────────────────────────────────────────────────────────
    async def receive(self, alert_source_id: str, body_bytes: bytes, supplied_token: str | None, supplied_signature: str | None, client_key: str) -> str:
        """Verify, store the raw event and enqueue processing. Returns the alert event id. Raises 401 on bad credentials (without saying why)."""
        rate_limiter.check(f"alert-intake:{alert_source_id}", self.settings.alert_intake_rate_limit_per_minute)
        rate_limiter.check(f"alert-intake-client:{client_key}", self.settings.alert_intake_rate_limit_per_minute)
        source = await self.session.get(AlertSource, alert_source_id)
        signing_secrets = await self._signing_secrets(source) if source is not None and supplied_signature else []
        if not self._credentials_are_valid(source, body_bytes, supplied_token, supplied_signature, signing_secrets):
            if source is not None:
                source.authentication_failure_count += 1
                if source.source_status != "paused":
                    source.source_status = "authentication_failures"
                await self.session.commit()
            raise AuthenticationException("The alert source token is missing or not valid.")
        if len(body_bytes) > self.settings.alert_intake_max_payload_bytes:
            raise BusinessValidationException(f"The payload exceeds {self.settings.alert_intake_max_payload_bytes} bytes.")
        try:
            payload = json.loads(body_bytes.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BusinessValidationException("The body must be a JSON document.") from None
        if not isinstance(payload, dict):
            raise BusinessValidationException("The body must be a JSON object.")
        source.last_received_at = alert_rules.utc_now()
        source.received_alert_count += 1
        event = AlertEvent(
            alert_source_id=source.alert_source_id, application_id=source.application_id, received_at=alert_rules.utc_now(), raw_payload_json=payload, payload_size_bytes=len(body_bytes),
            processing_status="ignored_paused" if source.source_status == "paused" else "received",
        )
        self.session.add(event)
        await self.session.flush()
        if event.processing_status == "received":
            await JobQueue(self.session).enqueue("process_alert_event", {"alert_event_id": event.alert_event_id}, deduplication_key=f"alert_event:{event.alert_event_id}", priority_number=10)
        return event.alert_event_id

    @staticmethod
    def _previous_secret_is_accepted(source: AlertSource) -> bool:
        return bool(source.previous_secret_valid_until and source.previous_secret_valid_until > alert_rules.utc_now())

    @classmethod
    def _accepted_secret_hashes(cls, source: AlertSource) -> list[str]:
        """The stored secret hashes that may authenticate a token now: the current one, plus the previous one during rotation."""
        accepted_hashes = [source.webhook_secret_hash]
        if source.previous_webhook_secret_hash and cls._previous_secret_is_accepted(source):
            accepted_hashes.append(source.previous_webhook_secret_hash)
        return accepted_hashes

    @classmethod
    async def _signing_secrets(cls, source: AlertSource) -> list[str]:
        """Plaintext webhook secrets (HMAC keys) from the secret store: the current one, plus the previous one during rotation.

        Empty for a source created before signing keys were stored: it stays token-only until its secret is rotated.
        """
        secret_names = [source.webhook_secret_name]
        if cls._previous_secret_is_accepted(source):
            secret_names.append(source.previous_webhook_secret_name)
        secret_store = application_context.secret_store()
        return [secret_value for secret_value in [await secret_store.get_secret_or_none(name) for name in secret_names] if secret_value]

    @classmethod
    def _credentials_are_valid(
        cls, source: AlertSource | None, body_bytes: bytes, supplied_token: str | None, supplied_signature: str | None, signing_secrets: Sequence[str] = ()
    ) -> bool:
        """Token (compared by hash) or HMAC-SHA256 signature of the body keyed with the webhook secret itself.

        The key is the plaintext secret from the secret store, never the stored hash, so database read access cannot forge signatures.
        An unknown source is still compared against a random throw-away hash so the response time does not reveal whether the source exists.
        """
        candidate_hashes = cls._accepted_secret_hashes(source) if source is not None else [hash_secret(secrets.token_hex(32))]
        supplied_hash = hash_secret(supplied_token.strip()) if supplied_token else None
        cleaned_signature = supplied_signature.strip().lower().removeprefix("sha256=") if supplied_signature else None
        is_authenticated = False
        for candidate_hash in candidate_hashes:
            if supplied_hash is not None and hmac.compare_digest(supplied_hash, candidate_hash):
                is_authenticated = True
        if cleaned_signature is not None and source is not None:
            for signing_secret in signing_secrets:
                expected_signature = hmac.new(signing_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
                if signing_secret and hmac.compare_digest(cleaned_signature, expected_signature):
                    is_authenticated = True
        return source is not None and is_authenticated

    # ── Setup instructions ─────────────────────────────────────────────────────
    async def get_setup_instructions(self, application_id: str, alert_source_id: str) -> SetupInstructionsResponse:
        return await self.build_setup_instructions(await self._get_source(application_id, alert_source_id), None)

    async def build_setup_instructions(self, source: AlertSource, secret_value: str | None) -> SetupInstructionsResponse:
        url_with_token = self.webhook_url(source.alert_source_id, secret_value, include_token=True)
        plain_url = self.webhook_url(source.alert_source_id)
        secret_text = secret_value or "<YOUR_SECRET>"
        resource_group = await self.session.scalar(
            select(ApplicationComponent.azure_resource_group_name).where(ApplicationComponent.application_id == source.application_id, ApplicationComponent.azure_resource_group_name.is_not(None)).limit(1)
        ) or "<RG_NAME>"
        canonical_example = {
            "externalId": "alert-1042", "ruleId": "checkout-error-rate", "ruleName": "Checkout error rate > 5%", "status": "firing", "severity": 2, "resourceRef": "aks-prod-01",
            "service": "checkout-api", "environment": "prod", "startedAt": "2026-11-19T04:12:00Z", "summary": "Error rate is 7.4% over 5 minutes", "description": "Optional longer text", "link": "https://monitoring.example/alerts/1042", "labels": {"team": "checkout"},
        }
        if source.source_tool == "azure_monitor":
            tabs = [
                SetupTab(tab_key="cli", tab_title="Azure CLI", steps=["Create an action group with a webhook receiver that has the common alert schema enabled.", "Attach the action group to the alert rules you want analysed (the list in Keigan shows which rules already send here).", "Verify the exact flags against the current az documentation."],
                         code_blocks=[
                             SetupCodeBlock(title="Create the action group", language="bash", content=f'az monitor action-group create \\\n  --name keigan-alerts --short-name keigan \\\n  --resource-group "{resource_group}" \\\n  --action webhook keigan "{url_with_token}" usecommonalertschema'),
                             SetupCodeBlock(title="Attach it to a metric alert rule", language="bash", content=f'az monitor metrics alert update \\\n  --name "<ALERT_RULE_NAME>" --resource-group "{resource_group}" \\\n  --add-action keigan-alerts'),
                         ]),
                SetupTab(tab_key="powershell", tab_title="PowerShell", steps=["Create the webhook receiver with the common alert schema, then the action group."],
                         code_blocks=[SetupCodeBlock(title="Create the action group", language="powershell", content=f'$receiver = New-AzActionGroupReceiver -Name "keigan" -WebhookReceiver -ServiceUri "{url_with_token}" -UseCommonAlertSchema\nSet-AzActionGroup -Name "keigan-alerts" -ResourceGroupName "{resource_group}" -ShortName "keigan" -Receiver $receiver')]),
                SetupTab(tab_key="terraform", tab_title="Terraform", steps=["Add the action group to your Terraform and reference it from your alert rules."],
                         code_blocks=[SetupCodeBlock(title="azurerm_monitor_action_group", language="hcl", content=f'resource "azurerm_monitor_action_group" "keigan" {{\n  name                = "keigan-alerts"\n  resource_group_name = "{resource_group}"\n  short_name          = "keigan"\n\n  webhook_receiver {{\n    name                    = "keigan"\n    service_uri             = "{url_with_token}"\n    use_common_alert_schema = true\n  }}\n}}')]),
                SetupTab(tab_key="portal", tab_title="Azure portal", steps=["Open Monitor, then Alerts, then Action groups, and choose Create.", f'Name it "keigan-alerts" in resource group {resource_group}.', "On the Actions tab choose Webhook, paste the URL below, and switch Enable the common alert schema to Yes.", "Open each alert rule you want analysed and add this action group.", f"Webhook URL: {url_with_token}", "Azure Monitor basic webhooks cannot send custom headers, so the token travels in the URL. Entra ID secure webhook is a later hardening option."]),
            ]
        elif source.source_tool == "elastic":
            body_template = json.dumps({
                "ruleId": "{{rule.id}}", "ruleName": "{{rule.name}}", "externalId": "{{alert.id}}", "status": "{{alert.actionGroup}}", "severity": 2, "service": "{{context.service}}", "environment": "prod",
                "startedAt": "{{date}}", "summary": "{{context.reason}}", "link": "{{kibanaBaseUrl}}", "labels": {"tags": "{{rule.tags}}"},
            }, indent=2)
            tabs = [
                SetupTab(tab_key="connector", tab_title="Elastic connector", steps=["In Kibana open Stack Management, then Connectors, and create a Webhook connector.", "Method POST, the URL below, and the header X-Keigan-Token with your secret. Add Content-Type: application/json.", "Edit your rules and add this connector as an action for both the Alert fired and the Recovered action groups.", "Paste the body template into the action body. Adjust severity and the service field per rule."],
                         code_blocks=[SetupCodeBlock(title="Connector URL", language="text", content=plain_url), SetupCodeBlock(title="Header", language="text", content=f"X-Keigan-Token: {secret_text}"), SetupCodeBlock(title="Action body template", language="json", content=body_template)]),
            ]
        else:
            tabs = [
                SetupTab(tab_key="generic", tab_title="Generic webhook", steps=["Configure your tool (Dynatrace, AppDynamics, Datadog, Grafana, Alertmanager, SolarWinds and so on) to POST JSON to the URL below.", "Send the token in the X-Keigan-Token header when the tool supports headers, otherwise use the URL with ?token=.", "If the payload shape is fixed, use the field mapping step to map its fields; otherwise send the canonical JSON shown here."],
                         code_blocks=[SetupCodeBlock(title="Test with curl", language="bash", content=f"curl -X POST '{plain_url}' \\\n  -H 'Content-Type: application/json' -H 'X-Keigan-Token: {secret_text}' \\\n  -d '{json.dumps(canonical_example)}'")]),
            ]
        tabs.append(self._signature_tab(source, plain_url, secret_text))
        return SetupInstructionsResponse(source_tool=source.source_tool, webhook_url=url_with_token if secret_value else plain_url + "?token=<YOUR_SECRET>", webhook_secret_is_placeholder=secret_value is None, tabs=tabs, canonical_example=canonical_example)

    @staticmethod
    def _signature_tab(source: AlertSource, plain_url: str, secret_text: str) -> SetupTab:
        """How to sign requests instead of sending the token. The key is the webhook secret itself."""
        if not source.webhook_secret_name:
            return SetupTab(
                tab_key="signature", tab_title="Request signature (optional)",
                steps=["Signed requests are not enabled for this source because it was created before signing keys were stored. It keeps working with its token.",
                       "To enable signatures, rotate the secret: the new secret becomes the signing key, and the old token stays valid for 24 hours."],
            )
        return SetupTab(
            tab_key="signature", tab_title="Request signature (optional)",
            steps=["Instead of the token you can sign each request. Compute the HMAC-SHA256 (SHA-256) of the exact request body with your webhook secret as the key, as lowercase hex.",
                   "Send it in the X-Keigan-Signature header, optionally with the prefix sha256=. Keigan keeps the secret in its secret store and accepts the previous secret for 24 hours after a rotation."],
            code_blocks=[SetupCodeBlock(
                title="Sign and send with curl", language="bash",
                content=f"BODY='{{\"ruleId\":\"checkout-error-rate\",\"ruleName\":\"Checkout error rate\",\"status\":\"firing\"}}'\n"
                        f"SIGNATURE=$(printf '%s' \"$BODY\" | openssl dgst -sha256 -hmac '{secret_text}' | sed 's/^.* //')\n"
                        f"curl -X POST '{plain_url}' -H 'Content-Type: application/json' -H \"X-Keigan-Signature: sha256=$SIGNATURE\" -d \"$BODY\"",
            )],
        )

    # ── Mapping preview ────────────────────────────────────────────────────────
    async def preview_mapping(self, application_id: str, request: MappingPreviewRequest) -> MappingPreviewResponse:
        sample = request.sample_payload
        if sample is None:
            latest_event = await self.session.scalar(select(AlertEvent).where(AlertEvent.application_id == application_id).order_by(AlertEvent.received_at.desc()).limit(1))
            sample = latest_event.raw_payload_json if latest_event else None
        if not sample:
            return MappingPreviewResponse(is_parsed=False, error_message="Paste a sample payload, or wait for the first alert to arrive.")
        paths = list_json_paths(sample)
        suggested = self._suggest_mapping(paths)
        try:
            canonical = alert_rules.normalise_payload(request.source_tool, sample, request.field_mapping or suggested, request.severity_mapping)
            alert_rules.mask_alert_text(canonical)
        except ValueError as parse_error:
            return MappingPreviewResponse(is_parsed=False, error_message=str(parse_error), suggested_field_mapping=suggested, available_paths=paths)
        pipeline = AlertPipelineService(self.session)
        context = await pipeline.load_context(application_id)
        transient_source = AlertSource(application_id=application_id, source_tool=request.source_tool, source_name="preview", webhook_secret_hash="", service_mapping_json=request.service_mapping)
        service = pipeline._resolve_service(context, transient_source, canonical, sample)  # noqa: SLF001
        service_path = (request.service_mapping or {}).get("field_path") or (request.field_mapping or suggested).get("serviceHint")
        service_value = read_json_path(sample, service_path) if service_path else None
        return MappingPreviewResponse(
            is_parsed=True, parsed_alert=canonical.to_dictionary(), matched_service_id=service.service_id if service else None, matched_service_name=service.service_name if service else None,
            suggested_field_mapping=suggested, available_paths=paths, distinct_service_values=[str(service_value)] if service_value not in (None, "") else [],
        )

    @staticmethod
    def _suggest_mapping(paths: list[str]) -> dict[str, str]:
        suggestions: dict[str, str] = {}
        for canonical_field, hints in FIELD_NAME_HINTS.items():
            best_path, best_rank = None, 999
            for path in paths:
                last_segment = re.sub(r"\[\d+\]", "", re.split(r"[.\[]", path.replace("']", "").replace("['", "."))[-1] if "." in path else path).lower().replace("_", "")
                for hint_rank, hint in enumerate(hints):
                    compact_hint = hint.replace("_", "")
                    if last_segment == compact_hint or (len(compact_hint) > 3 and compact_hint in last_segment):
                        rank = hint_rank + (0 if last_segment == compact_hint else 20)
                        if rank < best_rank:
                            best_path, best_rank = path, rank
                        break
            if best_path:
                suggestions[canonical_field] = best_path
        return suggestions

    # ── Test alert and live listener ───────────────────────────────────────────
    async def send_test_alert(self, current_user: CurrentUser, application_id: str, alert_source_id: str) -> TestAlertResponse:
        source = await self._get_source(application_id, alert_source_id)
        service = await self.session.scalar(select(MonitoredService).where(MonitoredService.application_id == application_id, MonitoredService.is_monitoring_enabled.is_(True)).order_by(MonitoredService.service_name).limit(1))
        payload = self._build_test_payload(source, service)
        event = AlertEvent(alert_source_id=source.alert_source_id, application_id=application_id, received_at=alert_rules.utc_now(), raw_payload_json=payload, payload_size_bytes=len(json.dumps(payload)))
        self.session.add(event)
        await self.session.flush()
        source.last_received_at = alert_rules.utc_now()
        source.received_alert_count += 1
        job_id = await JobQueue(self.session).enqueue("process_alert_event", {"alert_event_id": event.alert_event_id}, deduplication_key=f"alert_event:{event.alert_event_id}", priority_number=10)
        await AuditService(self.session).record(current_user, "alert_source.test", target_entity_type="alert_source", target_entity_id=alert_source_id, application_id=application_id)
        return TestAlertResponse(alert_event_id=event.alert_event_id, job_id=job_id, message="A simulated alert was sent through the whole pipeline.")

    @staticmethod
    def _build_test_payload(source: AlertSource, service: MonitoredService | None) -> dict[str, Any]:
        now_text = alert_rules.utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        identifier = f"keigan-test-{uuid.uuid4().hex[:8]}"
        resource_reference = (service.external_resource_identifier if service and service.external_resource_identifier else "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/keigan-test/providers/Microsoft.Web/sites/keigan-test")
        if source.source_tool == "azure_monitor":
            return {"schemaId": "azureMonitorCommonAlertSchema", "data": {"essentials": {
                "alertId": f"/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.AlertsManagement/alerts/{identifier}", "alertRule": "Keigan test alert", "severity": "Sev3",
                "signalType": "Metric", "monitorCondition": "Fired", "monitoringService": "Platform", "alertTargetIDs": [resource_reference], "firedDateTime": now_text,
                "description": "Test alert sent from Keigan to verify the connection."}, "alertContext": {"condition": {"allOf": [{"metricName": "Percentage CPU", "operator": "GreaterThan", "threshold": "90", "metricValue": "93"}]}}}}
        base_values = {"externalId": identifier, "ruleId": "keigan-test-alert", "ruleName": "Keigan test alert", "status": "firing", "severity": 3, "resourceRef": resource_reference, "service": service.service_name if service else "",
                       "environment": "prod", "startedAt": now_text, "summary": "Test alert sent from Keigan to verify the connection.", "labels": {"keiganTest": "true"}}
        mapping = {**alert_rules.DEFAULT_GENERIC_FIELD_MAPPING, **(source.field_mapping_json or {})} if source.source_tool == "generic" else {}
        if not mapping or mapping == alert_rules.DEFAULT_GENERIC_FIELD_MAPPING:
            return base_values
        payload: dict[str, Any] = {}
        for canonical_field, path in mapping.items():
            value = base_values.get("service" if canonical_field == "serviceHint" else canonical_field)
            if value is not None and path:
                _set_json_path(payload, path, value)
        return payload

    async def recent_events(self, application_id: str, alert_source_id: str, limit: int = 15) -> list[RecentAlertEventResponse]:
        source = await self._get_source(application_id, alert_source_id)
        events = (await self.session.scalars(select(AlertEvent).where(AlertEvent.alert_source_id == alert_source_id).order_by(AlertEvent.received_at.desc()).limit(min(limit, 50)))).all()
        context = await AlertPipelineService(self.session).load_context(application_id) if events else None
        pipeline = AlertPipelineService(self.session)
        masker = PiiMasker()
        responses: list[RecentAlertEventResponse] = []
        for event in events:
            parsed, service_name, parse_error = None, None, None
            try:
                canonical = alert_rules.normalise_payload(source.source_tool, event.raw_payload_json or {}, source.field_mapping_json, source.severity_mapping_json)
                alert_rules.mask_alert_text(canonical)
                parsed = canonical.to_dictionary()
                service = pipeline._resolve_service(context, source, canonical, event.raw_payload_json or {})  # noqa: SLF001
                service_name = service.service_name if service else None
            except ValueError as error:
                parse_error = str(error)
            responses.append(RecentAlertEventResponse(
                alert_event_id=event.alert_event_id, received_at=event.received_at, processing_status=event.processing_status, processing_error_message=event.processing_error_message,
                payload_size_bytes=event.payload_size_bytes, raw_payload=masker.mask_value(event.raw_payload_json), parsed_alert=parsed, matched_service_name=service_name, parse_error=parse_error,
            ))
        return responses

    # ── Azure alert rule discovery ─────────────────────────────────────────────
    async def discover_azure_rules(self, application_id: str) -> AzureAlertRulesResponse:
        seen_rule_names = set((await self.session.scalars(select(Alert.rule_name).where(Alert.application_id == application_id).distinct())).all())
        gateway = application_context.telemetry_gateway()
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all())
        components = list((await self.session.scalars(select(ApplicationComponent).where(ApplicationComponent.application_id == application_id, ApplicationComponent.component_type == "azure_resource_group"))).all())
        is_simulated = gateway.is_simulated()
        rules: list[AzureAlertRuleResponse] = []
        if is_simulated:
            rules = self._simulated_rules(services, seen_rule_names)
        else:
            for component in components:
                if not (component.azure_subscription_id and component.azure_resource_group_name):
                    continue
                try:
                    discovered = await application_context.azure_client().list_alert_rules(component.azure_tenant_id, component.azure_subscription_id, component.azure_resource_group_name)
                except Exception:  # noqa: BLE001
                    continue
                rules.extend(self._parse_azure_rules(discovered))
        return AzureAlertRulesResponse(is_simulated=is_simulated, total_rule_count=len(rules), sending_to_keigan_count=sum(1 for rule in rules if rule.sends_to_keigan), rules=rules)

    @staticmethod
    def _simulated_rules(services: list[MonitoredService], seen_rule_names: set[str]) -> list[AzureAlertRuleResponse]:
        rules: list[AzureAlertRuleResponse] = []
        names: set[str] = set()
        service_types = {service.service_type for service in services}
        for scenario in SCENARIO_CATALOG.values():
            matching_services = [service for service in services if service.service_type in scenario.primary_service_types]
            if not matching_services:
                continue
            for index, rule_name in enumerate(scenario.alert_rule_names):
                if rule_name not in names:
                    names.add(rule_name)
                    rules.append(AzureAlertRuleResponse(rule_name=rule_name, rule_kind="metric_alert" if index % 2 == 0 else "scheduled_query_rule", severity=1 + index % 3, target_resource=matching_services[0].service_name, sends_to_keigan=rule_name in seen_rule_names, action_group_names=["keigan-alerts"] if rule_name in seen_rule_names else ["oncall-email"]))
        for service in services:
            if service.service_type in ("aks", "app_service", "sql_database", "function_app"):
                rule_name = f"{service.service_name} CPU > 85%"
                rules.append(AzureAlertRuleResponse(rule_name=rule_name, rule_kind="metric_alert", severity=3, target_resource=service.service_name, sends_to_keigan=rule_name in seen_rule_names, action_group_names=["oncall-email"]))
        if service_types:
            rules.append(AzureAlertRuleResponse(rule_name="Resource health: service degraded", rule_kind="activity_log_alert", severity=2, target_resource="resource group", sends_to_keigan=False, action_group_names=["oncall-email"]))
        return rules

    @staticmethod
    def _parse_azure_rules(discovered: dict[str, list[dict[str, Any]]]) -> list[AzureAlertRuleResponse]:
        webhook_group_ids = {
            action_group.get("id", "").lower(): action_group.get("name", "") for action_group in discovered.get("action_groups", [])
            if any("/api/alerts/in/" in str(receiver.get("serviceUri", "")) for receiver in (action_group.get("properties") or {}).get("webhookReceivers", []))
        }
        group_names = {action_group.get("id", "").lower(): action_group.get("name", "") for action_group in discovered.get("action_groups", [])}
        rules: list[AzureAlertRuleResponse] = []
        for collection_name, rule_kind in (("metric_alerts", "metric_alert"), ("scheduled_query_rules", "scheduled_query_rule"), ("activity_log_alerts", "activity_log_alert")):
            for rule in discovered.get(collection_name, []):
                properties = rule.get("properties") or {}
                actions = properties.get("actions")
                group_ids: list[str] = []
                if isinstance(actions, list):
                    group_ids = [str(action.get("actionGroupId", "")) for action in actions]
                elif isinstance(actions, dict):
                    group_ids = [str(item if isinstance(item, str) else item.get("actionGroupId", "")) for item in actions.get("actionGroups", [])]
                scopes = properties.get("scopes") or []
                rules.append(AzureAlertRuleResponse(
                    rule_name=rule.get("name", "unnamed"), rule_kind=rule_kind, severity=properties.get("severity"), target_resource=(scopes[0].rsplit("/", 1)[-1] if scopes else None), is_enabled=bool(properties.get("enabled", True)),
                    sends_to_keigan=any(group_id.lower() in webhook_group_ids for group_id in group_ids), action_group_names=[group_names.get(group_id.lower(), group_id.rsplit("/", 1)[-1]) for group_id in group_ids],
                ))
        return rules


def _set_json_path(document: dict[str, Any], json_path: str, value: Any) -> None:
    segments = [segment for segment in re.split(r"\.|\['|'\]|\[\"|\"\]", json_path.lstrip("$")) if segment]
    current = document
    for segment in segments[:-1]:
        current = current.setdefault(segment, {})
    if segments:
        current[segments[-1]] = value
