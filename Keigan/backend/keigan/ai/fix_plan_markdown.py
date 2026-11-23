"""The fix plan as Markdown, written by code (spec 33, 4.5).

``Investigation.how_to_fix_markdown`` is read by the email to technical roles, the Teams chat, the postmortem prompt and Ask Keigan, none of which can show a fill-in field. This text is what they
get: the overview, then each step with its command in the default shell, warnings, and how to check and undo it. A command with a missing value is not shown with a gap in it; the text says to open
Keigan to fill the values in. A withheld command says why. English: the consumers of this text are English today.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from keigan.entities.status_values import FixActionKind, FixWarning

_WARNING_TEXT = {
    FixWarning.NO_REVERT: "No way back was given for this step.",
    FixWarning.NO_VALIDATION: "No check was given for this step.",
    FixWarning.PRINTS_SECRETS: "This command shows secrets on the screen.",
    FixWarning.RESTARTS_SERVICE: "This restarts the service.",
    FixWarning.CONTAINS_ASSUMPTIONS: "This step contains values Keigan assumed and could not verify.",
    FixWarning.VALIDATION_CHANGES_STATE: "The check itself changes something.",
    FixWarning.REVERT_IS_HIGH_RISK: "Undoing this step is high risk.",
}


def _words(code: str) -> str:
    return code.replace("_", " ")


def _action_lines(action: Mapping[str, Any], default_dialect: str, label: str | None = None) -> list[str]:
    """One action as paragraphs: its description, then what to copy or what to see."""
    lines = [f"{label}: {action['description']}" if label else action["description"]]
    command, change = action["command"], action["configuration_change"]
    if action["withheld_reason"] is not None:
        lines.append(f"Command withheld: {_words(action['withheld_reason'])}. The step stays; work out the exact values and write it yourself.")
    elif command is not None:
        rendering = next((candidate for candidate in command["renderings"] if candidate["dialect"] == default_dialect), command["renderings"][0] if command["renderings"] else None)
        if rendering is not None and rendering["text"] is not None:
            lines.append(f"```{'powershell' if rendering['dialect'] == 'powershell' else 'bash'}\n{rendering['text']}\n```")
        elif rendering is not None:
            missing = sum(1 for segment in rendering["segments"] if segment["kind"] == "missing_value")
            lines.append(f"Open this investigation in Keigan to fill in {missing} value{'s' if missing != 1 else ''} before copying the command.")
    elif change is not None:
        before, after = change["before_value"], change["after_value"]
        shown = lambda entry: entry["value"] if entry and entry["value"] is not None else "(not known)"  # noqa: E731
        lines.append(f"Change the setting {shown(change['setting_name'])} on {change['service_name']} from {shown(before)} to {shown(after)}.")
    elif action["action_kind"] == FixActionKind.RERUN_EVIDENCE_QUERY and action["evidence_code"]:
        lines.append(f"Run the query behind [{action['evidence_code']}] again.")
    if action["expected_result"]:
        lines.append(f"Expected: {action['expected_result']}")
    return lines


def render_fix_plan_markdown(overview_markdown: str, steps: Sequence[Mapping[str, Any]], default_dialect: str) -> str:
    paragraphs = [overview_markdown.strip()] if overview_markdown.strip() else []
    for number, step in enumerate(steps, start=1):
        paragraphs.append(f"**Step {number}. {step['title']}** ({_words(step['purpose'])}; {step['risk_level']} risk)")
        paragraphs += _action_lines(step["action"], default_dialect)
        paragraphs += [_WARNING_TEXT[FixWarning(warning)] for warning in step["warnings"]]
        if step["check"] is not None and step["check"]["withheld_reason"] is None:
            paragraphs += _action_lines(step["check"], default_dialect, "Check")
        if step["revert"] is not None:
            paragraphs += _action_lines(step["revert"], default_dialect, "Undo")
    return "\n\n".join(paragraphs)
