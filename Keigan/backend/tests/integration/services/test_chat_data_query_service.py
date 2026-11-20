"""keigan/services/chat_data_query_service.py: chat does not query logs of an onboarding request, and does not spend an LLM call on it (V2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.ai.llm_gateway import LlmUsageContext
from keigan.config.database_config import open_session
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.services.chat_data_query_service import ChatDataQueryService
from support.telemetry_scope import OWN_WORKSPACE_CUSTOMER_ID, OWN_WORKSPACE_RESOURCE_ID, create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")


class LlmGatewayThatMustNotBeCalled:
    async def generate_structured(self, **_arguments: object) -> object:
        raise AssertionError("The LLM must not be called for an application that is not approved.")


async def create_service_with_workspace_source(application_id: str, component_id: str) -> MonitoredService:
    async with open_session() as session:
        service = MonitoredService(application_id=application_id, component_id=component_id, service_name="polaris-api", service_type="app_service", created_by_user_principal_name="system:test")
        session.add(service)
        await session.flush()
        session.add(ServiceLogSource(
            service_id=service.service_id, source_kind="log_analytics", log_analytics_workspace_resource_id=OWN_WORKSPACE_RESOURCE_ID,
            log_analytics_workspace_customer_id=OWN_WORKSPACE_CUSTOMER_ID, is_primary_source=True,
        ))
        return service


async def test_chat_refuses_an_onboarding_request_before_calling_the_llm() -> None:
    requested = await create_scoped_application(lifecycle_status="requested")
    service = await create_service_with_workspace_source(requested.application_id, requested.component_id)
    now = datetime.now(UTC)
    async with open_session() as session:
        chat_query_service = ChatDataQueryService(session)
        chat_query_service.gateway = LlmGatewayThatMustNotBeCalled()  # type: ignore[assignment]
        with pytest.raises(ForbiddenException) as refusal:
            await chat_query_service.run(
                service=service, question_text="show errors", wants_failures=True, wants_pattern=False, time_range_start=now - timedelta(hours=1), time_range_end=now,
                requested_by="requester@example.com", usage_context=LlmUsageContext(),
            )
    assert refusal.value.detail == "Keigan reads telemetry only for approved applications. Ask a Keigan admin to approve the onboarding request."
