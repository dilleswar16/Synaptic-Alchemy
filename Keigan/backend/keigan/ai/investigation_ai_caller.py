"""One place that renders a prompt, calls the LLM gateway (or the offline mock factories) and accounts tokens for an investigation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from keigan.ai.investigation_mock_responses import OFFLINE_FACTORIES, MockInvestigationContext, mock_investigation_context
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection, estimate_token_count
from keigan.config import application_context
from keigan.entities.status_values import Priority


class InvestigationAiCaller:
    def __init__(
        self, application_id: str, application_name: str, criticality_tier: str, investigation_id: str | None, requested_by: str | None,
        mock_context: MockInvestigationContext | None, offline_ai: bool = False,
    ):
        self.application_id, self.application_name, self.criticality_tier = application_id, application_name, criticality_tier
        self.investigation_id, self.requested_by = investigation_id, requested_by
        self.mock_context, self.offline_ai = mock_context, offline_ai
        self.gateway = application_context.llm_gateway()
        self.prompt_library = application_context.prompt_library()
        self.estimated_input_tokens = 0
        self.estimated_output_tokens = 0
        self.model_names: set[str] = set()

    @property
    def uses_estimated_tokens(self) -> bool:
        return self.offline_ai or self.gateway.is_mock

    async def ask(self, feature_name: str, prompt_sections: list[PromptSection], output_schema: type[BaseModel], **template_variables: Any) -> Any:
        model_tier = ModelTier(self.prompt_library.model_tier_for_call(feature_name))  # refuses prompts that are written for people
        system_prompt = self.prompt_library.render(feature_name, application_name=self.application_name, criticality_tier=self.criticality_tier, **template_variables)
        mock_investigation_context.set(self.mock_context)
        if self.offline_ai:
            result = output_schema.model_validate(OFFLINE_FACTORIES[feature_name](output_schema, prompt_sections).model_dump())
            self.model_names.add("offline-factory")
        else:
            result = await self.gateway.generate_structured(
                feature_name=feature_name, model_tier=model_tier, system_prompt=system_prompt, prompt_sections=prompt_sections, output_schema=output_schema,
                usage_context=LlmUsageContext(application_id=self.application_id, investigation_id=self.investigation_id, requested_by_user_principal_name=self.requested_by),
            )
            self.model_names.add("mock" if self.gateway.is_mock else self.gateway.model_name_for(model_tier))
        if self.uses_estimated_tokens:  # real providers are accounted from llm_usage_record
            self.estimated_input_tokens += estimate_token_count(system_prompt) + sum(estimate_token_count(section.content) for section in prompt_sections)
            self.estimated_output_tokens += estimate_token_count(result.model_dump_json())
        return result


async def build_mock_context(
    investigation: Any, incident: Any, application_name: str, all_services: list[Any], evidence_rows: list[Any] | None = None
) -> MockInvestigationContext:
    """Match the investigation to the simulator's scenario window (mock mode and offline factories only) and publish the real evidence."""
    from keigan.ai.investigation_mock_responses import MockServiceInfo
    from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
    from keigan.services.incident_priority_rules import map_servicenow_priority

    simulator = application_context.telemetry_simulator()
    await simulator.refresh_configuration(force=True)
    names_by_id = {service.service_id: service.service_name for service in all_services}
    matching_windows = [
        window for window in simulator.active_scenario_windows()
        if window.application_id == investigation.application_id and window.overlaps(investigation.investigation_window_start, investigation.investigation_window_end)
    ]
    incident_number = incident.external_incident_number if incident else None
    scenario_window = next((window for window in matching_windows if incident_number and window.external_incident_number == incident_number), None) or (
        max(matching_windows, key=lambda window: window.started_at) if matching_windows else None
    )
    return MockInvestigationContext(
        application_name=application_name,
        services=[MockServiceInfo(service.service_id, service.service_name, service.service_type, service.aks_namespace_filter, None, service.external_resource_identifier) for service in all_services],
        evidence=[
            {"code": row.evidence_code, "service_name": names_by_id.get(row.service_id or "", "Azure Activity Log"), "category": row.evidence_category, "strength": row.signal_strength,
             "title": row.evidence_title, "summary": row.evidence_summary or "", "is_rule_out": row.matched_record_count == 0 or (row.evidence_summary or "").startswith(("Rule-out", "Not available"))}
            for row in (evidence_rows or [])
        ],
        scenario_key=scenario_window.scenario_key if scenario_window else None,
        primary_service_name=names_by_id.get(scenario_window.primary_service_ids[0]) if scenario_window and scenario_window.primary_service_ids else None,
        dependency_service_name=names_by_id.get(scenario_window.dependency_service_ids[0]) if scenario_window and scenario_window.dependency_service_ids else None,
        priority=(incident.keigan_priority or map_servicenow_priority(incident.servicenow_impact, incident.servicenow_urgency, incident.servicenow_priority)) if incident else Priority.P3,
        incident_title=(incident.incident_title if incident else None) or (SCENARIO_CATALOG[scenario_window.scenario_key].title if scenario_window else "Manual investigation"),
    )
