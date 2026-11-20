"""Structured outputs and offline mocks for Teams chat digestion and predictive intelligence narratives."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from keigan.ai.llm_gateway import PromptSection, register_mock_response


class ChatDigestFact(BaseModel):
    fact_title: str = Field(description="One short sentence stating what the responders did, decided or observed (max 140 characters).")
    fact_details: str = Field(default="", description="Optional one or two sentences of context taken only from the messages.")


class TeamsChatDigestResult(BaseModel):
    facts: list[ChatDigestFact] = Field(default_factory=list, description="Facts worth adding to the incident timeline. Empty when the messages are only chatter.")
    should_comment: bool = Field(default=False, description="True only when Keigan has a concrete, useful observation to add unprompted.")
    comment_markdown: str = Field(default="", description="The unprompted comment (max 3 sentences). Empty when should_comment is false.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class IntelligenceNarrativeResult(BaseModel):
    narrative_markdown: str = Field(description="Two to four sentences explaining the signal in plain language, citing the numbers provided, with one recommended next step.")


class IntelligenceReportResult(BaseModel):
    executive_summary: str = Field(description="Three to five sentences summarising reliability posture for the period, citing the numbers provided.")
    recommendations: list[str] = Field(default_factory=list, description="Up to four concrete recommendations ordered by priority.")


_ACTION_PATTERN = re.compile(r"\b(restart(ed)?|rolled? back|rollback|scaled?|increased|failover|fail(ed)? over|redeploy(ed)?|applied|fixed|disabled|enabled|cleared)\b|(再起動|ロールバック|スケール|適用|修正|復旧)", re.IGNORECASE)


def deterministic_chat_facts(message_lines: list[str]) -> list[ChatDigestFact]:
    """Fallback and mock: a message that names an action becomes a timeline fact."""
    facts: list[ChatDigestFact] = []
    for line in message_lines:
        author, _, text = line.partition(": ")
        if _ACTION_PATTERN.search(text) and not text.strip().endswith("?"):
            facts.append(ChatDigestFact(fact_title=f"{author}: {text.strip()}"[:140], fact_details=""))
    return facts[:3]


def _mock_chat_digest(output_schema: type[TeamsChatDigestResult], prompt_sections: list[PromptSection]) -> TeamsChatDigestResult:
    messages_section = next((section.content for section in prompt_sections if section.title.startswith("New chat messages")), "")
    facts = deterministic_chat_facts([line for line in messages_section.splitlines() if line.strip()])
    return output_schema(facts=facts, should_comment=False, comment_markdown="", confidence=0.6 if facts else 0.2)


def _mock_narrative(output_schema: type[IntelligenceNarrativeResult], prompt_sections: list[PromptSection]) -> IntelligenceNarrativeResult:
    facts = next((section.content for section in prompt_sections if section.title == "Signal facts"), "")
    return output_schema(narrative_markdown=f"{facts.strip()}\n\nRecommended next step: review the trend with the service owner before it affects customers.".strip())


def _mock_report(output_schema: type[IntelligenceReportResult], prompt_sections: list[PromptSection]) -> IntelligenceReportResult:
    facts = next((section.content for section in prompt_sections if section.title == "Report facts"), "")
    lines = [line.lstrip("- ").strip() for line in facts.splitlines()]
    summary_lines = [line for line in lines if line.startswith(("Health score", "Incidents:", "Alert noise:"))]
    first_lines = " ".join(summary_lines)
    return output_schema(
        executive_summary=f"{first_lines} Overall reliability is acceptable, with the open predictive signals below deserving attention this week.",
        recommendations=["Review open predictive signals with the owning teams.", "Check that error budgets for at-risk SLOs are still meaningful.", "Confirm on-call runbooks cover the recurring incident categories."],
    )


register_mock_response("teams_chat_digest", _mock_chat_digest)  # type: ignore[arg-type]
register_mock_response("intelligence_narrative", _mock_narrative)  # type: ignore[arg-type]
register_mock_response("intelligence_report", _mock_report)  # type: ignore[arg-type]
