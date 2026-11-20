"""keigan/services/alert_source_service.py: webhook secrets live in the secret store and key the HMAC signature (V1b)."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import select

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.integrations.azure_client import AlertRuleReadResult
from keigan.entities.alert_entities import AlertSource
from keigan.services.alert_source_service import hash_secret
from support import users
from support.alerts import generic_alert_payload
from support.http import AuthHeaders


async def _create_source(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> dict:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    response = await client.post(f"/api/applications/{clmjp}/alert-sources", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={"sourceTool": "generic", "sourceName": "Signature test source"})
    assert response.status_code == 201, response.text
    return {**response.json(), "applicationId": clmjp}


async def _post_signed(client: httpx.AsyncClient, alert_source_id: str, signing_key: str, *, token: str | None = None) -> httpx.Response:
    body = json.dumps(generic_alert_payload("signed-rule")).encode()
    headers = {"Content-Type": "application/json", "X-Keigan-Signature": "sha256=" + hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()}
    if token:
        headers["X-Keigan-Token"] = token
    return await client.post(f"/api/alerts/in/{alert_source_id}", content=body, headers=headers)


async def test_new_source_keeps_its_plaintext_secret_in_the_secret_store_under_a_generated_name(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    async with open_session() as session:
        source = await session.get(AlertSource, created["alertSource"]["alertSourceId"])
    assert source is not None and source.webhook_secret_name and created["webhookSecret"] not in source.webhook_secret_name
    assert await application_context.secret_store().get_secret(source.webhook_secret_name) == created["webhookSecret"]
    assert source.webhook_secret_hash == hash_secret(created["webhookSecret"])


async def test_webhook_accepts_a_signature_keyed_with_the_secret_and_no_token(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    response = await _post_signed(client, created["alertSource"]["alertSourceId"], created["webhookSecret"])
    assert response.status_code == 202, response.text


async def test_webhook_rejects_a_signature_keyed_with_the_stored_hash(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    response = await _post_signed(client, created["alertSource"]["alertSourceId"], hash_secret(created["webhookSecret"]))
    assert response.status_code == 401


async def test_rotation_keeps_the_previous_signing_secret_valid_and_adds_the_new_one(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    source_id = created["alertSource"]["alertSourceId"]
    rotation = await client.post(f"/api/applications/{created['applicationId']}/alert-sources/{source_id}/rotate-secret", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER))
    assert rotation.status_code == 200, rotation.text
    new_secret = rotation.json()["webhookSecret"]
    assert (await _post_signed(client, source_id, new_secret)).status_code == 202
    assert (await _post_signed(client, source_id, created["webhookSecret"])).status_code == 202


async def test_source_created_before_signing_keys_were_stored_accepts_its_token_but_no_signature(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    source_id = created["alertSource"]["alertSourceId"]
    async with open_session() as session:
        source = (await session.scalars(select(AlertSource).where(AlertSource.alert_source_id == source_id))).one()
        source.webhook_secret_name = None
    assert (await _post_signed(client, source_id, created["webhookSecret"])).status_code == 401
    assert (await _post_signed(client, source_id, "ignored", token=created["webhookSecret"])).status_code == 202


async def test_setup_instructions_explain_how_to_sign_requests_with_the_secret(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    signature_tab = next(tab for tab in created["setupInstructions"]["tabs"] if tab["tabKey"] == "signature")
    text = " ".join(signature_tab["steps"]) + " ".join(block["content"] for block in signature_tab["codeBlocks"])
    assert "X-Keigan-Signature" in text and created["webhookSecret"] in text and "SHA-256" in text


async def test_setup_instructions_of_a_source_without_a_signing_secret_say_to_rotate_first(client, auth_headers, seed_context) -> None:
    created = await _create_source(client, auth_headers, seed_context)
    source_id = created["alertSource"]["alertSourceId"]
    async with open_session() as session:
        (await session.get(AlertSource, source_id)).webhook_secret_name = None  # type: ignore[union-attr]
    response = await client.get(f"/api/applications/{created['applicationId']}/alert-sources/{source_id}/setup-instructions", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER))
    signature_tab = next(tab for tab in response.json()["tabs"] if tab["tabKey"] == "signature")
    assert "rotate the secret" in " ".join(signature_tab["steps"]).lower()


class TestAzureRuleDiscoveryNamesTheResourceGroupsItCannotRead:
    async def test_a_resource_group_that_cannot_be_read_is_named_in_the_response_and_logged(self, seed_context, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from keigan.entities.application_entities import ApplicationComponent
        from keigan.exceptions.keigan_exceptions import IntegrationException
        from keigan.entities.status_values import ComponentType
        from keigan.services.alert_source_service import AlertSourceService

        application_id = seed_context.application_ids_by_code["CLMJP"]
        async with open_session() as session:
            resource_group_names = (await session.scalars(select(ApplicationComponent.azure_resource_group_name).where(
                ApplicationComponent.application_id == application_id, ApplicationComponent.component_type == ComponentType.AZURE_RESOURCE_GROUP, ApplicationComponent.azure_resource_group_name.is_not(None),
            ))).all()
        unreadable_group = resource_group_names[0]

        class LiveGateway:
            def is_simulated(self) -> bool:
                return False

        class PartlyReadableClient:
            async def list_alert_rules(self, tenant_id: str | None, subscription_id: str, resource_group_name: str) -> object:
                if resource_group_name == unreadable_group:
                    raise IntegrationException("Azure refused the read")
                return AlertRuleReadResult(rules_by_collection={}, failure_codes=())

        monkeypatch.setattr(application_context, "telemetry_gateway", lambda: LiveGateway())
        monkeypatch.setattr(application_context, "azure_client", lambda: PartlyReadableClient())
        async with open_session() as session:
            response = await AlertSourceService(session).discover_azure_rules(application_id)
        assert [(group.resource_group_name, group.reason_code) for group in response.unreadable_resource_groups] == [(unreadable_group, "failed")]
        assert any(record.levelno == logging.WARNING and unreadable_group in record.getMessage() for record in caplog.records)

    @pytest.mark.parametrize(("failure_codes", "reason_code"), [
        (("azure_forbidden",), "forbidden"),
        (("azure_not_found",), "not_found"),
        (("azure_throttled", "azure_forbidden"), "forbidden"),
        (("azure_throttled",), "throttled"),
        (("azure_request_failed",), "failed"),
    ])
    async def test_a_group_with_refused_collections_is_listed_with_the_most_useful_reason(self, seed_context, monkeypatch: pytest.MonkeyPatch, failure_codes: tuple[str, ...], reason_code: str) -> None:
        from keigan.entities.application_entities import ApplicationComponent
        from keigan.entities.status_values import ComponentType
        from keigan.services.alert_source_service import AlertSourceService

        application_id = seed_context.application_ids_by_code["CLMJP"]
        async with open_session() as session:
            resource_group_names = (await session.scalars(select(ApplicationComponent.azure_resource_group_name).where(
                ApplicationComponent.application_id == application_id, ApplicationComponent.component_type == ComponentType.AZURE_RESOURCE_GROUP, ApplicationComponent.azure_resource_group_name.is_not(None),
            ))).all()
        refused_group = resource_group_names[0]

        class LiveGateway:
            def is_simulated(self) -> bool:
                return False

        class RefusingCollectionsClient:
            async def list_alert_rules(self, tenant_id: str | None, subscription_id: str, resource_group_name: str) -> object:
                return AlertRuleReadResult(rules_by_collection={}, failure_codes=failure_codes if resource_group_name == refused_group else ())

        monkeypatch.setattr(application_context, "telemetry_gateway", lambda: LiveGateway())
        monkeypatch.setattr(application_context, "azure_client", lambda: RefusingCollectionsClient())
        async with open_session() as session:
            response = await AlertSourceService(session).discover_azure_rules(application_id)
        assert [(group.resource_group_name, group.reason_code) for group in response.unreadable_resource_groups] == [(refused_group, reason_code)]
