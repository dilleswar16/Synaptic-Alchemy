"""Structured output of the alert features (group title and summary) and its offline mock."""

from __future__ import annotations

from pydantic import BaseModel, Field

from keigan.ai.llm_gateway import PromptSection, register_mock_response


class AlertGroupTitleResult(BaseModel):
    group_title: str = Field(description="At most 90 characters: affected service or symptom in plain language.")
    group_summary: str = Field(description="One sentence about what the grouped alerts have in common. No root-cause guesses.")


def deterministic_group_title(service_names: list[str], rule_names: list[str], alert_count: int) -> tuple[str, str]:
    """Fallback used when the model is unavailable, over budget or switched off (seed replay)."""
    primary_service = service_names[0] if service_names else "Application"
    primary_rule = rule_names[0] if rule_names else "alert"
    title = f"{primary_service}: {primary_rule}"[:90]
    other_services = len(service_names) - 1
    summary = f"{alert_count} alert{'s' if alert_count != 1 else ''} on {primary_service}" + (f" and {other_services} related service{'s' if other_services != 1 else ''}" if other_services > 0 else "") + "."
    return title, summary


def _mock_group_title(output_schema: type[AlertGroupTitleResult], prompt_sections: list[PromptSection]) -> AlertGroupTitleResult:
    facts = "\n".join(section.content for section in prompt_sections)
    services = next((line.split(":", 1)[1].strip() for line in facts.splitlines() if line.startswith("Services:")), "")
    rules = next((line.split(":", 1)[1].strip() for line in facts.splitlines() if line.startswith("Rules:")), "")
    service_names = [name.strip() for name in services.split(",") if name.strip()]
    rule_names = [name.strip() for name in rules.split(";") if name.strip()]
    title, summary = deterministic_group_title(service_names, rule_names, max(1, len(rule_names)))
    return output_schema(group_title=title, group_summary=summary)


register_mock_response("alert_group_title", _mock_group_title)  # type: ignore[arg-type]
