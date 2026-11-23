"""keigan/ai/fix_plan.py and fix_plan_markdown.py: which steps an investigation recommends and how the plan reads where nothing can be filled in (spec 33, 4.5; AC-14 to AC-17)."""

from __future__ import annotations

from typing import Any

from keigan.ai.fix_plan import build_fix_plan, resolve_plan_steps, step_is_usable
from keigan.ai.fix_plan_markdown import render_fix_plan_markdown
from keigan.ai.fix_step_validator import FixValidationContext, validate_fix_step
from keigan.ai.investigation_ai_schemas import FixActionOutput, FixCommandOutput, FixParameterOutput, FixStepOutput

CONTEXT = FixValidationContext(
    catalogue_values=frozenset({"claims-web-jp", "rg-claims-jp-prod"}), evidence_texts={"E3": "pool"}, evidence_codes_with_query=frozenset({"E3"}), knowledge_text="",
    maximum_command_characters=300, maximum_parameters_per_command=6, clean_markdown=lambda text: text, clean_line=lambda text: text,
)


def stored_step(perspective: str, number: int, *, resource_group: str | None = "rg-claims-jp-prod", withheld: bool = False, title: str = "Restart the app") -> dict[str, Any]:
    template = "az webapp restart --name {{service}} && x" if withheld else "az webapp restart --name {{service}} --resource-group {{rg}}"
    action = FixActionOutput(action_kind="command", description="Restart it", expected_result="Healthy again", command=FixCommandOutput(tool="az", template=template, parameters=[
        FixParameterOutput(name="service", value_kind="azure_resource_name", value="claims-web-jp", value_source="service_catalogue"),
        FixParameterOutput(name="rg", value_kind="azure_resource_group", value=resource_group, value_source="service_catalogue" if resource_group else "unknown"),
    ]))
    step = FixStepOutput(
        title=title, purpose="mitigate", risk_level="medium", action=action,
        check=FixActionOutput(action_kind="rerun_evidence_query", description="See the errors stop", evidence_code="E3", expected_result="No rows"),
        revert=FixActionOutput(action_kind="manual_action", description="Nothing to undo."),
    )
    return validate_fix_step(step, f"{perspective}-{number}", CONTEXT)


def hypothesis(perspective: str, *steps: dict[str, Any]) -> dict[str, Any]:
    return {"analysis_perspective": perspective, "proposed_fix": {"schema_version": 2, "summary": "s", "steps": list(steps)}}


HYPOTHESES = [
    hypothesis("application", stored_step("application", 1), stored_step("application", 2, withheld=True)),
    hypothesis("dependencies", stored_step("dependencies", 1, title="Raise the timeout")),
    hypothesis("infrastructure"),
]


# ── The plan ─────────────────────────────────────────────────────────────────────────────────────


def references_of(plan: dict[str, Any]) -> list[tuple[str, str]]:
    return [(reference["perspective"], reference["step_id"]) for reference in plan["step_references"]]


def test_the_plan_keeps_the_references_in_the_order_the_synthesis_gave_them() -> None:
    plan = build_fix_plan("Overview.", [("dependencies", 1), ("application", 1)], HYPOTHESES, "application", 8)
    assert plan["schema_version"] == 2 and plan["overview_markdown"] == "Overview." and references_of(plan) == [("dependencies", "dependencies-1"), ("application", "application-1")]


def test_a_reference_that_does_not_resolve_repeats_or_points_at_a_withheld_step_is_dropped() -> None:
    assert step_is_usable(HYPOTHESES[0]["proposed_fix"]["steps"][0]) and not step_is_usable(HYPOTHESES[0]["proposed_fix"]["steps"][1])
    plan = build_fix_plan("", [("application", 2), ("application", 9), ("nowhere", 1), ("application", 0), ("application", 1), ("application", 1), ("infrastructure", 1)], HYPOTHESES, "application", 8)
    assert references_of(plan) == [("application", "application-1")]


def test_the_plan_is_capped() -> None:
    plan = build_fix_plan("", [("application", 1), ("dependencies", 1)], HYPOTHESES, "application", 1)
    assert references_of(plan) == [("application", "application-1")]


def test_when_nothing_usable_is_left_the_plan_is_the_leading_analysts_usable_steps() -> None:
    plan = build_fix_plan("Fallback.", [("application", 2)], HYPOTHESES, "dependencies", 8)
    assert references_of(plan) == [("dependencies", "dependencies-1")]
    assert references_of(build_fix_plan("", [], HYPOTHESES, None, 8)) == [("application", "application-1")]  # no leader: the first analyst
    assert references_of(build_fix_plan("", [], [hypothesis("application")], "application", 8)) == []


def test_a_plan_resolves_to_the_stored_steps_with_their_analyst() -> None:
    plan = build_fix_plan("", [("dependencies", 1), ("application", 1)], HYPOTHESES, "application", 8)
    steps = resolve_plan_steps(plan, HYPOTHESES)
    assert [(step["perspective"], step["title"]) for step in steps] == [("dependencies", "Raise the timeout"), ("application", "Restart the app")]
    assert resolve_plan_steps({"step_references": [{"perspective": "application", "step_id": "gone-9"}]}, HYPOTHESES) == []


# ── The Markdown the other channels read ─────────────────────────────────────────────────────────


def test_the_plan_markdown_has_the_overview_the_command_in_the_default_shell_and_how_to_check_and_undo() -> None:
    steps = resolve_plan_steps(build_fix_plan("", [("application", 1)], HYPOTHESES, "application", 8), HYPOTHESES)
    markdown = render_fix_plan_markdown("Restart first [E3].", steps, "bash")
    assert markdown.startswith("Restart first [E3].\n\n**Step 1. Restart the app** (mitigate; medium risk)")
    assert "```bash\naz webapp restart --name claims-web-jp --resource-group rg-claims-jp-prod\n```" in markdown
    assert "Expected: Healthy again" in markdown and "Check: See the errors stop" in markdown and "Run the query behind [E3] again." in markdown and "Undo: Nothing to undo." in markdown


def test_a_command_with_a_missing_value_says_to_open_keigan_instead_of_showing_a_gap() -> None:
    gap = hypothesis("application", stored_step("application", 1, resource_group=None))
    markdown = render_fix_plan_markdown("", resolve_plan_steps(build_fix_plan("", [("application", 1)], [gap], "application", 8), [gap]), "bash")
    assert "Open this investigation in Keigan to fill in 1 value before copying the command." in markdown and "```" not in markdown and "--resource-group" not in markdown


def test_a_withheld_command_is_not_shown_and_says_why() -> None:
    markdown = render_fix_plan_markdown("", [{**HYPOTHESES[0]["proposed_fix"]["steps"][1], "perspective": "application"}], "bash")
    assert "Command withheld: unsafe shell syntax." in markdown and "```" not in markdown and "&&" not in markdown


def test_the_default_shell_picks_the_matching_rendering() -> None:
    steps = resolve_plan_steps(build_fix_plan("", [("application", 1)], HYPOTHESES, "application", 8), HYPOTHESES)
    assert "```powershell\naz webapp restart" in render_fix_plan_markdown("", steps, "powershell")


def _setting_change_step(resource_group: str | None) -> dict[str, Any]:
    from dataclasses import replace

    from keigan.ai.fix_configuration_command import ServiceFacts
    from keigan.ai.investigation_ai_schemas import ConfigurationChangeOutput

    context = replace(CONTEXT, services={"claims-web-jp": ServiceFacts("app_service", resource_group, None)})
    change = ConfigurationChangeOutput(
        target_kind="app_setting", service_name="claims-web-jp",
        setting_name=FixParameterOutput(name="setting", value_kind="configuration_key", value="Database__MaxPoolSize", value_source="knowledge"),
        before_value=None, after_value=FixParameterOutput(name="after", value_kind="configuration_value", value="16", value_source="knowledge"),
    )
    action = FixActionOutput(action_kind="configuration_change", description="Raise the pool", configuration_change=change)
    return validate_fix_step(FixStepOutput(title="Raise the pool", purpose="mitigate", risk_level="medium", action=action), "application-1", context)


def test_a_setting_change_with_a_command_shows_the_edit_and_the_command_in_the_default_shell() -> None:
    markdown = render_fix_plan_markdown("", [{**_setting_change_step("rg-claims-jp-prod"), "perspective": "application"}], "bash")
    assert "Change the setting Database__MaxPoolSize on claims-web-jp from (not known) to 16." in markdown
    assert "```bash\naz webapp config appsettings set --name claims-web-jp --resource-group rg-claims-jp-prod --settings Database__MaxPoolSize=16\n```" in markdown


def test_a_setting_change_command_with_a_missing_value_says_to_open_keigan() -> None:
    markdown = render_fix_plan_markdown("", [{**_setting_change_step(None), "perspective": "application"}], "bash")
    assert "Open this investigation in Keigan to fill in 1 value before copying the command." in markdown and "```" not in markdown
