"""Checks one suggested fix step before it is stored and shown (spec 33, 4.4).

The model writes a command as a template with named slots and says where each value came from. This module decides, in code, whether the step may be shown: every value must be a valid value
of its kind and is checked against the source it claims (found there: *verified*; not found: *assumed*, kept and highlighted; not known: *missing*, a fill-in field; not valid: *refused*,
cleared and never shown), the shape and the secrets are checked, the command is rendered for each shell, and the risk is computed. Risk can only go up from what the model said. A command
that fails a rule is *withheld*: its step keeps its description, the command is not shown, and the reason is stored. Pure functions: no model, no database.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from keigan.ai.command_risk_classifier import RISK_RANK, classify_command_risk, reveals_secrets
from keigan.ai.fix_command_check import contains_secret
from keigan.ai.fix_command_renderer import ParameterValue, RenderedCommand, render_command
from keigan.ai.fix_command_shape import SLOT_PATTERN, FixCommandTool, FixWithheldReason, check_template_shape
from keigan.ai.fix_configuration_command import ServiceFacts, command_for_change
from keigan.ai.fix_parameter_kinds import ValueRefusal, check_value, is_secret_setting_name
from keigan.ai.investigation_ai_schemas import ConfigurationChangeOutput, FixActionOutput, FixCommandOutput, FixParameterOutput, FixStepOutput
from keigan.ai.prompt_safety import strip_invisible_characters
from keigan.entities.status_values import (
    ConfigurationTargetKind, FixActionKind, FixStepPurpose, FixValueSource, FixValueStatus, FixWarning, RiskLevel, ShellDialect,
)

NEUTRAL_VALUE = "VALUE"  # stands for a missing value when a command is rated: the classifier reads the command, not the value
_RESTARTING_TARGETS = frozenset({ConfigurationTargetKind.APP_SETTING, ConfigurationTargetKind.KUBERNETES_ENVIRONMENT_VARIABLE})
_RISK_BY_RANK = {rank: level for level, rank in RISK_RANK.items()}


@dataclass(frozen=True)
class FixValidationContext:
    """What a value may be checked against: the application's catalogue, this investigation's evidence, and the knowledge the model was given."""

    catalogue_values: frozenset[str]  # service names, namespaces, resource groups and resource ids of the application
    evidence_texts: Mapping[str, str]  # evidence code -> the text a value may be found in (title, summary, condensed patterns)
    evidence_codes_with_query: frozenset[str]  # evidence codes whose stored query can be run again
    knowledge_text: str  # the knowledge documents and matched runbooks the model was given
    maximum_command_characters: int
    maximum_parameters_per_command: int
    clean_markdown: Callable[[str], str]  # descriptions: citations that do not exist removed, markdown neutralised
    clean_line: Callable[[str], str]  # titles and one-line texts
    services: Mapping[str, ServiceFacts] = field(default_factory=dict)  # service name -> type, resource group and namespace: what a setting change's command is built from


def _higher(first: RiskLevel, second: RiskLevel) -> RiskLevel:
    return first if RISK_RANK[first] >= RISK_RANK[second] else second


# ── Values ───────────────────────────────────────────────────────────────────────────────────────


def check_parameter(parameter: FixParameterOutput, context: FixValidationContext) -> dict[str, Any]:
    """The stored form of one value: its (cleared when unusable) value, its status and why."""
    stored: dict[str, Any] = {"name": parameter.name, "value_kind": parameter.value_kind, "value": None, "value_source": parameter.value_source, "source_code": parameter.source_code}
    value = strip_invisible_characters(parameter.value).strip() if parameter.value else ""
    if not value:
        return {**stored, "status": FixValueStatus.MISSING, "status_reason": "not_known"}
    refusal = check_value(parameter.value_kind, value)
    if refusal == ValueRefusal.MASKED:
        return {**stored, "status": FixValueStatus.MASKED, "status_reason": ValueRefusal.MASKED}
    if refusal is not None:
        return {**stored, "status": FixValueStatus.REFUSED, "status_reason": refusal}  # the value is not kept or shown: it may be the attack
    status, reason = _source_check(parameter, value, context)
    return {**stored, "value": value, "status": status, "status_reason": reason}


def _source_check(parameter: FixParameterOutput, value: str, context: FixValidationContext) -> tuple[FixValueStatus, str | None]:
    source = FixValueSource(parameter.value_source)
    if source == FixValueSource.SERVICE_CATALOGUE:
        return (FixValueStatus.VERIFIED, None) if value in context.catalogue_values else (FixValueStatus.ASSUMED, "not_in_catalogue")
    if source == FixValueSource.EVIDENCE:
        text = context.evidence_texts.get(parameter.source_code or "")
        if text is None:
            return FixValueStatus.ASSUMED, "unknown_evidence_code"
        return (FixValueStatus.VERIFIED, None) if value in text else (FixValueStatus.ASSUMED, f"not_found_in_{parameter.source_code}")
    if source in (FixValueSource.RUNBOOK, FixValueSource.KNOWLEDGE):
        return (FixValueStatus.VERIFIED, None) if value in context.knowledge_text else (FixValueStatus.ASSUMED, "not_found_in_knowledge")
    return FixValueStatus.ASSUMED, "source_not_stated"


# ── Commands ─────────────────────────────────────────────────────────────────────────────────────


def _dialects_of(command: FixCommandOutput) -> list[str]:
    if command.dialect != "any":
        return [command.dialect]
    if command.tool == FixCommandTool.POWERSHELL:
        return [ShellDialect.POWERSHELL]
    if command.tool == FixCommandTool.SHELL:
        return [ShellDialect.BASH]
    return [ShellDialect.BASH, ShellDialect.POWERSHELL]  # az, kubectl, helm and sql read the same in both shells


def _segment_dicts(rendering: RenderedCommand, parameters: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for segment in rendering.segments:
        if segment.kind == "literal":
            segments.append({"kind": "literal", "text": segment.text, "parameter_name": None})
        elif segment.kind == "value":
            assumed = parameters[segment.parameter_name or ""]["status"] == FixValueStatus.ASSUMED
            segments.append({"kind": "assumed_value" if assumed else "value", "text": segment.text, "parameter_name": segment.parameter_name})
        else:
            segments.append({"kind": "missing_value", "text": "", "parameter_name": segment.parameter_name})
    return segments


def validate_command(command: FixCommandOutput, context: FixValidationContext) -> dict[str, Any]:
    """The stored form of one command: its parameters, its renderings per shell (or why it is withheld) and its computed risk."""
    template = strip_invisible_characters(command.template).strip()
    slot_names = list(dict.fromkeys(SLOT_PATTERN.findall(template)))
    checked = {parameter.name: check_parameter(parameter, context) for parameter in command.parameters if parameter.name in slot_names}
    withheld: FixWithheldReason | None = None
    if any(name not in checked for name in slot_names):
        withheld = FixWithheldReason.UNKNOWN_SLOT
    elif len(slot_names) > context.maximum_parameters_per_command:
        withheld = FixWithheldReason.UNSAFE_SHELL_SYNTAX
    else:
        withheld = check_template_shape(template, command.tool, command.dialect)
    if withheld is None and (contains_secret(template) or any(entry["value"] and contains_secret(entry["value"]) for entry in checked.values())):
        withheld = FixWithheldReason.SECRET_IN_COMMAND
    values = {name: ParameterValue(entry["value_kind"], entry["value"]) for name, entry in checked.items()}
    renderings: list[dict[str, Any]] = []
    risk = RiskLevel(classify_command_risk(SLOT_PATTERN.sub(NEUTRAL_VALUE, template)))
    warnings: list[FixWarning] = []
    if withheld is None:
        for dialect in _dialects_of(command):
            rendered = render_command(template, values, dialect)
            if rendered.withheld_reason is not None:
                withheld = rendered.withheld_reason
                renderings = []
                break
            rated_text = "".join(segment.text or NEUTRAL_VALUE for segment in rendered.segments)
            if len(rated_text) > context.maximum_command_characters:
                withheld, renderings = FixWithheldReason.COMMAND_TOO_LONG, []
                break
            rendering_risk = RiskLevel(classify_command_risk(rated_text))
            if reveals_secrets(rated_text):
                rendering_risk, warnings = RiskLevel.HIGH, [FixWarning.PRINTS_SECRETS]
            risk = _higher(risk, rendering_risk)
            renderings.append({"dialect": dialect, "text": rendered.text, "risk_level": rendering_risk, "segments": _segment_dicts(rendered, checked)})
    if withheld is None and command.tool == FixCommandTool.SQL and risk != RiskLevel.LOW:
        withheld, renderings = FixWithheldReason.DATA_CHANGING_SQL, []
    return {
        "tool": command.tool, "dialect": command.dialect, "template": template, "parameters": list(checked.values()), "withheld_reason": withheld, "renderings": renderings,
        "risk_level": risk, "warnings": warnings,
    }


# ── Configuration changes ────────────────────────────────────────────────────────────────────────


def validate_configuration_change(change: ConfigurationChangeOutput, context: FixValidationContext, restrict_file_path: Callable[[str], str]) -> dict[str, Any]:
    """A configuration change is shown as a before and after edit of a named setting. For a service the configuration command catalogue knows, the command that makes the change is stored with it
    (it is checked like any command; when it cannot be shown safely, the change stays an edit). A secret-looking setting name or value is withheld."""
    setting = check_parameter(change.setting_name.model_copy(update={"value_kind": "configuration_key"}), context)
    before = check_parameter(change.before_value.model_copy(update={"value_kind": "configuration_value"}), context) if change.before_value else None
    after = check_parameter(change.after_value.model_copy(update={"value_kind": "configuration_value"}), context)
    withheld: FixWithheldReason | None = None
    if setting["value"] and is_secret_setting_name(setting["value"]):
        withheld = FixWithheldReason.SECRET_SETTING_NAME
    elif any(entry and entry["value"] and contains_secret(entry["value"]) for entry in (setting, before, after)):
        withheld = FixWithheldReason.SECRET_IN_COMMAND
    return {
        "target_kind": change.target_kind, "service_name": context.clean_line(change.service_name), "service_in_catalogue": change.service_name in context.catalogue_values,
        "setting_name": setting, "before_value": before, "after_value": after, "file_path": restrict_file_path(change.file_path) if change.file_path else None,
        "withheld_reason": withheld, "risk_level": RiskLevel.MEDIUM,
        "warnings": [FixWarning.RESTARTS_SERVICE] if change.target_kind in _RESTARTING_TARGETS else [],
        "command": None if withheld is not None else _command_for(change, context),
    }


def _command_for(change: ConfigurationChangeOutput, context: FixValidationContext) -> dict[str, Any] | None:
    """The command from the catalogue for ``change``, checked like any other; None when there is none or it may not be shown (a value that needs quotes next to the ``=`` is the usual reason)."""
    command = command_for_change(change, context.services)
    if command is None:
        return None
    checked = validate_command(command, context)
    return checked if checked["withheld_reason"] is None else None


# ── Actions and steps ────────────────────────────────────────────────────────────────────────────


def _validate_action(action: FixActionOutput, context: FixValidationContext, restrict_file_path: Callable[[str], str]) -> dict[str, Any]:
    stored: dict[str, Any] = {
        "action_kind": action.action_kind, "description": context.clean_markdown(action.description), "expected_result": context.clean_markdown(action.expected_result) if action.expected_result else "",
        "risk_level": RiskLevel.LOW, "command": None, "configuration_change": None, "evidence_code": None, "withheld_reason": None,
    }
    if action.action_kind == FixActionKind.COMMAND and action.command is not None:
        command = validate_command(action.command, context)
        return {**stored, "command": command, "risk_level": command["risk_level"], "withheld_reason": command["withheld_reason"]}
    if action.action_kind == FixActionKind.CONFIGURATION_CHANGE and action.configuration_change is not None:
        change = validate_configuration_change(action.configuration_change, context, restrict_file_path)
        return {**stored, "configuration_change": change, "risk_level": change["risk_level"], "withheld_reason": change["withheld_reason"]}
    if action.action_kind == FixActionKind.RERUN_EVIDENCE_QUERY:
        if action.evidence_code in context.evidence_codes_with_query:
            return {**stored, "evidence_code": action.evidence_code}
        return {**stored, "withheld_reason": FixWithheldReason.UNKNOWN_EVIDENCE_CODE}
    if action.action_kind == FixActionKind.MANUAL_ACTION:
        return stored
    # A command or a configuration change that came without its content cannot be shown as either: it stays a description.
    return {**stored, "action_kind": FixActionKind.MANUAL_ACTION}


def _withhold(action: dict[str, Any], reason: FixWithheldReason) -> None:
    """The command or the configuration change is not shown; the description, expected result and computed risk stay."""
    action["withheld_reason"] = reason
    if action["command"] is not None:
        action["command"]["withheld_reason"] = reason
        action["command"]["renderings"] = []
    if action["configuration_change"] is not None:
        action["configuration_change"]["withheld_reason"] = reason


def _derived_revert(action: dict[str, Any]) -> dict[str, Any] | None:
    """When the model gave no way back for a configuration change: set the setting back to its before-value (a manual edit), or tell the person to set it back to what they saw."""
    change = action["configuration_change"]
    if change is None:
        return None
    before = change["before_value"]
    knows_before = before is not None and before["value"] is not None
    description = "Set the setting back to its previous value." if knows_before else "Set the setting back to the value you read before changing it."
    revert_change = {**change, "before_value": change["after_value"], "after_value": before, "withheld_reason": None, "command": None} if knows_before else None  # an edit, never the forward command
    return {
        "action_kind": FixActionKind.CONFIGURATION_CHANGE if knows_before else FixActionKind.MANUAL_ACTION, "description": description, "expected_result": "", "risk_level": RiskLevel.MEDIUM,
        "command": None, "configuration_change": revert_change, "evidence_code": None, "withheld_reason": None,
    }


def _missing_value_count(action: dict[str, Any]) -> int:
    parameters: list[dict[str, Any]] = []
    if action["command"] is not None:
        parameters += action["command"]["parameters"]
    change = action["configuration_change"]
    if change is not None:
        parameters += [entry for entry in (change["setting_name"], change["after_value"]) if entry is not None]
        parameters += change["command"]["parameters"] if change["command"] is not None else []
    return sum(1 for entry in parameters if entry["status"] != FixValueStatus.VERIFIED and entry["status"] != FixValueStatus.ASSUMED)


def _has_assumed_values(action: dict[str, Any]) -> bool:
    parameters: list[dict[str, Any]] = list(action["command"]["parameters"]) if action["command"] is not None else []
    change = action["configuration_change"]
    if change is not None:
        parameters += [entry for entry in (change["setting_name"], change["before_value"], change["after_value"]) if entry is not None]
        parameters += change["command"]["parameters"] if change["command"] is not None else []
        parameters += [] if change["service_in_catalogue"] else [{"status": FixValueStatus.ASSUMED}]
    return any(entry["status"] == FixValueStatus.ASSUMED for entry in parameters)


def validate_fix_step(step: FixStepOutput, step_id: str, context: FixValidationContext, restrict_file_path: Callable[[str], str] = lambda path: path) -> dict[str, Any]:
    """The stored form of one step (spec 33, 4.2.5), with the risk computed and the rules across its parts applied."""
    action = _validate_action(step.action, context, restrict_file_path)
    check = _validate_action(step.check, context, restrict_file_path) if step.check else None
    revert = _validate_action(step.revert, context, restrict_file_path) if step.revert else None
    reasons = [f"model:{step.risk_level}", f"computed:{action['risk_level']}"]
    risk = _higher(RiskLevel(step.risk_level), action["risk_level"])  # the model may understate the risk; it can never lower code's rating
    if revert is None:
        revert = _derived_revert(action)
    warnings: list[FixWarning] = []
    for part in (action["command"], action["configuration_change"]):
        warnings += [warning for warning in (part["warnings"] if part else []) if warning not in warnings]
    if risk == RiskLevel.HIGH and revert is None and action["withheld_reason"] is None and (action["command"] is not None or action["configuration_change"] is not None):
        _withhold(action, FixWithheldReason.DESTRUCTIVE_WITHOUT_REVERT)
    if revert is None and risk == RiskLevel.MEDIUM and action["action_kind"] != FixActionKind.MANUAL_ACTION:
        warnings.append(FixWarning.NO_REVERT)
    if step.purpose != FixStepPurpose.DIAGNOSE and (check is None or check["withheld_reason"] == FixWithheldReason.UNKNOWN_EVIDENCE_CODE):
        warnings.append(FixWarning.NO_VALIDATION)
    if check is not None and RISK_RANK[check["risk_level"]] > RISK_RANK[RiskLevel.LOW]:
        warnings.append(FixWarning.VALIDATION_CHANGES_STATE)
    if revert is not None and revert["risk_level"] == RiskLevel.HIGH:
        warnings.append(FixWarning.REVERT_IS_HIGH_RISK)
    has_assumed = _has_assumed_values(action) or bool(step.assumptions)
    if has_assumed:
        warnings.append(FixWarning.CONTAINS_ASSUMPTIONS)
    return {
        "step_id": step_id, "title": context.clean_line(step.title), "purpose": step.purpose, "risk_level": risk, "risk_reasons": reasons, "warnings": list(dict.fromkeys(warnings)),
        "assumptions": [context.clean_line(text) for text in step.assumptions], "has_assumed_values": has_assumed, "missing_value_count": _missing_value_count(action),
        "action": action, "check": check, "revert": revert,
    }
