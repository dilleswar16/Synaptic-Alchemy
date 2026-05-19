"""
Post-Mortem Auto-Generator — V3

Produces a blameless post-mortem Markdown document from a completed
InvestigationResult.  The document follows blameless SRE culture: it focuses
on systems, processes, and timelines — not individuals.

The LLM is called once (prevention recommendations section only).
Everything else is deterministically assembled from persisted data so the
document is fully reproducible even if the LLM changes.

The generated PostMortemOutput is cached in Postgres (post_mortems table).
Repeat calls return the cached version without re-invoking the LLM.
"""

from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime, timezone
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult, PostMortemOutput

_log = logging.getLogger(__name__)

_SECTION_SEP = "\n\n---\n\n"

_PREVENTION_PROMPT = """\
You are a senior SRE writing the "Prevention & Future Actions" section of a
blameless post-mortem.  Based on the incident context below, write 3-5
concrete, actionable prevention recommendations.

Rules:
- Be specific to the technology and failure mode described.
- Use blameless language: focus on systems and processes, never individuals.
- Format as a numbered Markdown list.
- Do not include any markdown fence or extra commentary — output the list only.

Incident Context:
{context}
"""


class PostMortemService:
    """Generate and cache blameless post-mortem documents."""

    def __init__(
        self,
        model_config: dict[str, Any] | None = None,
    ) -> None:
        self._model_config = (
            model_config if model_config is not None else load_config("models/llm", get_env())
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        result: InvestigationResult,
        approved_by: str | None = None,
    ) -> PostMortemOutput:
        """
        Build a PostMortemOutput from a completed InvestigationResult.

        Parameters
        ----------
        result:      The full investigation result (must be complete — has rca + fix_strategy).
        approved_by: Optional SRE name from the approval audit trail.
        """
        detection_timeline = self._build_detection_timeline(result)
        investigation_findings = self._build_investigation_findings(result)
        actions_taken = self._build_actions_taken(result)
        incident_summary = self._build_incident_summary(result)
        prevention = self._generate_prevention(result)

        markdown = self._assemble_markdown(
            result=result,
            approved_by=approved_by,
            incident_summary=incident_summary,
            detection_timeline=detection_timeline,
            investigation_findings=investigation_findings,
            actions_taken=actions_taken,
            prevention=prevention,
        )

        return PostMortemOutput(
            request_id=result.request_id,
            service_name=result.request.service_name,
            environment=result.request.environment,
            incident_summary=incident_summary,
            detection_timeline=detection_timeline,
            investigation_findings=investigation_findings,
            actions_taken=actions_taken,
            prevention_recommendations=prevention,
            approved_by=approved_by,
            markdown=markdown,
        )

    # ── Section builders (deterministic) ─────────────────────────────────────

    def _build_incident_summary(self, result: InvestigationResult) -> str:
        confidence = result.rca.confidence.value.upper()
        action_count = len(result.fix_strategy.actions)
        
        warning_block = ""
        if result.confidence_warning:
            warning_block = (
                "> ⚠️ **LOW CONFIDENCE WARNING**  \n"
                "> Corvin generated this RCA with low confidence due to insufficient or ambiguous evidence. Manual review is strongly recommended.\n\n"
            )

        return (
            f"{warning_block}"
            f"**Service:** {result.request.service_name}  \n"
            f"**Environment:** {result.request.environment}  \n"
            f"**Trigger:** {result.request.trigger_source.value.replace('_', ' ').title()}  \n"
            f"**RCA Confidence:** {confidence}  \n"
            f"**Fix Actions Proposed:** {action_count}  \n\n"
            f"{result.rca.summary}"
        )

    def _build_detection_timeline(self, result: InvestigationResult) -> str:
        created = result.request.created_at
        completed = result.completed_at
        delta = completed - created
        minutes = int(delta.total_seconds() // 60)
        seconds = int(delta.total_seconds() % 60)
        duration = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        lines = [
            f"| Timestamp (UTC) | Event |",
            f"|---|---|",
            f"| `{_fmt_ts(created)}` | Alert / trigger received — investigation started |",
            f"| `{_fmt_ts(result.evidence.collected_at)}` | Evidence collection complete |",
            f"| `{_fmt_ts(result.rca.generated_at)}` | RCA generated |",
            f"| `{_fmt_ts(result.fix_strategy.generated_at)}` | Fix strategy generated |",
            f"| `{_fmt_ts(completed)}` | Investigation pipeline complete |",
            f"",
            f"**Time to investigate (pipeline):** {duration}",
        ]
        if result.request.description:
            lines.insert(2, f"| `{_fmt_ts(created)}` | Description: _{result.request.description}_ |")
        return "\n".join(lines)

    def _build_investigation_findings(self, result: InvestigationResult) -> str:
        rca = result.rca
        lines = [
            f"**Root Cause**\n\n{rca.root_cause}",
        ]
        
        if rca.confidence_reasoning:
            lines.append(
                f"> 🧠 **What Would a Senior SRE Do? · Corvin's Rationale**  \n"
                f"> {rca.confidence_reasoning}"
            )

        if rca.contributing_factors:
            factors = "\n".join(f"- {f}" for f in rca.contributing_factors)
            lines.append(f"**Contributing Factors**\n\n{factors}")
        if rca.evidence_references:
            refs = "\n".join(f"- {r}" for r in rca.evidence_references)
            lines.append(f"**Evidence References**\n\n{refs}")
        return "\n\n".join(lines)

    def _build_actions_taken(self, result: InvestigationResult) -> str:
        actions = result.fix_strategy.actions
        if not actions:
            return "_No automated fix actions were included in the fix strategy._"

        rows = [
            "| # | Action | Type | Risk | Estimated Impact |",
            "|---|---|---|---|---|",
        ]
        for i, a in enumerate(actions, 1):
            risk_emoji = "🔴" if a.risk_level.value == "high" else "🟡" if a.risk_level.value == "medium" else "🟢"
            rows.append(
                f"| {i} | {a.title} | `{a.action_type.value}` "
                f"| {risk_emoji} {a.risk_level.value.upper()} | {a.estimated_impact} |"
            )

        rows.append("")
        rows.append(f"**Fix Strategy Summary**\n\n{result.fix_strategy.summary}")
        rows.append(f"\n**Justification**\n\n{result.fix_strategy.justification}")
        return "\n".join(rows)

    # ── LLM section (prevention recommendations) ──────────────────────────────

    def _generate_prevention(self, result: InvestigationResult) -> str:
        context = json.dumps(
            {
                "service_name": result.request.service_name,
                "environment": result.request.environment,
                "trigger": result.request.description,
                "root_cause": result.rca.root_cause,
                "contributing_factors": result.rca.contributing_factors,
                "fix_actions": [a.title for a in result.fix_strategy.actions],
            },
            indent=2,
        )
        prompt = _PREVENTION_PROMPT.format(context=context)
        # Use fallback_model (regular completion path, no Responses API) so that
        # api_base is resolved from AZURE_API_BASE env var automatically.
        model = self._model_config.get("fallback_model") or self._model_config["model"]
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._model_config.get("temperature", 0.3),
                max_tokens=600,
            )
            text = response.choices[0].message.content or ""
            return text.strip()
        except Exception as exc:
            _log.warning("PostMortemService: LLM prevention call failed (%s) — using fallback", exc)
            return textwrap.dedent("""\
                1. Add automated alerting thresholds for the failure mode identified in the RCA.
                2. Review runbooks to ensure on-call engineers have clear remediation steps.
                3. Conduct a team walkthrough of this incident to share learnings.
                4. Validate that monitoring coverage is adequate for this service.
                5. Schedule a follow-up review in 30 days to confirm the fix remains effective.\
            """)

    # ── Markdown assembler ────────────────────────────────────────────────────

    def _assemble_markdown(
        self,
        result: InvestigationResult,
        approved_by: str | None,
        incident_summary: str,
        detection_timeline: str,
        investigation_findings: str,
        actions_taken: str,
        prevention: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        header_lines = [
            f"# Blameless Post-Mortem — {result.request.service_name}",
            f"",
            f"> **Generated by Corvin** · {_fmt_ts(now)} UTC  ",
        ]
        if approved_by:
            header_lines.append(f"> **Approved by:** {approved_by}  ")
        header_lines += [
            f"> **Investigation ID:** `{result.request_id}`  ",
            f"> **Environment:** {result.request.environment}",
            f"",
            f"---",
            f"",
            f"*This document follows blameless post-mortem principles.*  ",
            f"*Focus is on systems and processes — not individuals.*",
        ]

        sections = [
            "\n".join(header_lines),
            f"## 1. Incident Summary\n\n{incident_summary}",
            f"## 2. Detection & Investigation Timeline\n\n{detection_timeline}",
            f"## 3. Root Cause & Investigation Findings\n\n{investigation_findings}",
            f"## 4. Actions Taken\n\n{actions_taken}",
            f"## 5. Prevention & Future Actions\n\n{prevention}",
        ]

        return _SECTION_SEP.join(sections)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_ts(dt: datetime) -> str:
    """Format a datetime as a readable UTC string for Markdown tables."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")
