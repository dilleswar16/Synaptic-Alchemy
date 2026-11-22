"""keigan/services/chat_data_query_service.py: chat does not query logs of an onboarding request, and does not spend an LLM call on it (V2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.ai.llm_gateway import LlmUsageContext
from keigan.config.database_config import open_session
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.services.chat_data_query_service import ChatDataQueryService, QueryNotAnswerableError
from support.telemetry_scope import OWN_WORKSPACE_CUSTOMER_ID, OWN_WORKSPACE_RESOURCE_ID, create_log_tool_connection, create_scoped_application

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


class LlmGatewayWritingAPlainSplunkSearch:
    """Answers the query-writing call with one plain SPL search and remembers the prompt it was given."""

    def __init__(self) -> None:
        self.prompt_section_titles: list[str] = []
        self.prompt_section_bodies: dict[str, str] = {}

    async def generate_structured(self, *, prompt_sections: list, output_schema: type, **_arguments: object) -> object:
        for prompt_section in prompt_sections:
            self.prompt_section_titles.append(prompt_section.title)
            self.prompt_section_bodies[prompt_section.title] = prompt_section.content
        return output_schema(query_text="error", explanation="Counts error events.")


async def create_splunk_service(application_id: str, index_name: str) -> MonitoredService:
    connection_id = await create_log_tool_connection(application_id, tool_type="splunk")
    async with open_session() as session:
        service = MonitoredService(application_id=application_id, service_name="polaris-batch", service_type="app_service", created_by_user_principal_name="system:test")
        session.add(service)
        await session.flush()
        session.add(ServiceLogSource(
            service_id=service.service_id, source_kind="log_tool", log_tool_connection_id=connection_id, query_scope_json={"index": index_name}, is_primary_source=True,
        ))
        return service


async def test_chat_search_on_a_splunk_service_is_limited_to_the_index_of_its_log_source() -> None:
    approved = await create_scoped_application()
    service = await create_splunk_service(approved.application_id, "payments_prod")
    now = datetime.now(UTC)
    async with open_session() as session:
        chat_query_service = ChatDataQueryService(session)
        language_model = LlmGatewayWritingAPlainSplunkSearch()
        chat_query_service.gateway = language_model  # type: ignore[assignment]
        outcome = await chat_query_service.run(
            service=service, question_text="show errors", wants_failures=True, wants_pattern=False, time_range_start=now - timedelta(hours=1), time_range_end=now,
            requested_by="reader@example.com", usage_context=LlmUsageContext(),
        )
    assert outcome.query_language == "spl"
    assert "index=payments_prod" in outcome.query_text
    assert "index=*" not in outcome.query_text


async def test_the_caller_is_told_the_query_as_soon_as_it_is_written() -> None:
    approved = await create_scoped_application()
    service = await create_splunk_service(approved.application_id, "payments_prod")
    now = datetime.now(UTC)
    announced: list[tuple[str, str]] = []

    async def announce(query_language: str, query_text: str) -> None:
        announced.append((query_language, query_text))

    async with open_session() as session:
        chat_query_service = ChatDataQueryService(session)
        chat_query_service.gateway = LlmGatewayWritingAPlainSplunkSearch()  # type: ignore[assignment]
        outcome = await chat_query_service.run(
            service=service, question_text="show errors", wants_failures=True, wants_pattern=False, time_range_start=now - timedelta(hours=1), time_range_end=now,
            requested_by="reader@example.com", usage_context=LlmUsageContext(), on_query_generated=announce,
        )
    assert announced == [("spl", outcome.query_text)]


class LlmGatewayThatCannotWriteAQuery:
    """Answers the query-writing call the way the prompt allows: an empty query and a sentence on what is missing."""

    async def generate_structured(self, *, output_schema: type, **_arguments: object) -> object:
        return output_schema(query_text="", explanation="The question asks about user accounts, which are not in the logs of this service.")


async def test_chat_explains_why_it_cannot_write_a_query_instead_of_reporting_an_empty_query() -> None:
    approved = await create_scoped_application()
    service = await create_splunk_service(approved.application_id, "payments_prod")
    now = datetime.now(UTC)
    async with open_session() as session:
        chat_query_service = ChatDataQueryService(session)
        chat_query_service.gateway = LlmGatewayThatCannotWriteAQuery()  # type: ignore[assignment]
        with pytest.raises(QueryNotAnswerableError) as refusal:
            await chat_query_service.run(
                service=service, question_text="how many users signed up", wants_failures=False, wants_pattern=False, time_range_start=now - timedelta(hours=1), time_range_end=now,
                requested_by="reader@example.com", usage_context=LlmUsageContext(),
            )
    assert refusal.value.detail == "I can't answer that from the logs of polaris-batch. The question asks about user accounts, which are not in the logs of this service."


async def test_chat_gives_a_generic_reason_when_the_model_returns_an_empty_query_without_an_explanation() -> None:
    approved = await create_scoped_application()
    service = await create_splunk_service(approved.application_id, "payments_prod")
    now = datetime.now(UTC)

    class LlmGatewayReturningNothing:
        async def generate_structured(self, *, output_schema: type, **_arguments: object) -> object:
            return output_schema(query_text="  ")

    async with open_session() as session:
        chat_query_service = ChatDataQueryService(session)
        chat_query_service.gateway = LlmGatewayReturningNothing()  # type: ignore[assignment]
        with pytest.raises(QueryNotAnswerableError) as refusal:
            await chat_query_service.run(
                service=service, question_text="anything", wants_failures=False, wants_pattern=False, time_range_start=now - timedelta(hours=1), time_range_end=now,
                requested_by="reader@example.com", usage_context=LlmUsageContext(),
            )
    assert refusal.value.detail == "I can't answer that from the logs of polaris-batch. Try asking about the requests, errors or latency of this service."


async def test_chat_query_prompt_tells_the_model_the_limits_of_the_log_source() -> None:
    approved = await create_scoped_application()
    service = await create_splunk_service(approved.application_id, "payments_prod")
    now = datetime.now(UTC)
    async with open_session() as session:
        chat_query_service = ChatDataQueryService(session)
        language_model = LlmGatewayWritingAPlainSplunkSearch()
        chat_query_service.gateway = language_model  # type: ignore[assignment]
        await chat_query_service.run(
            service=service, question_text="show errors", wants_failures=True, wants_pattern=False, time_range_start=now - timedelta(hours=1), time_range_end=now,
            requested_by="reader@example.com", usage_context=LlmUsageContext(),
        )
    assert "Query limits" in language_model.prompt_section_titles
    assert '"index": "payments_prod"' in language_model.prompt_section_bodies["Query limits"]
