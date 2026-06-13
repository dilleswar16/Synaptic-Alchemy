"""
Slice 5 – Knowledge layer injection tests.

Tests PromptBuilder.build() in isolation using fake KnowledgeLoader instances
plus a small number of real-loader integration checks.  Tests cover:

  - System prompt includes site knowledge content.
  - System prompt includes matched runbook content with precedence note.
  - System prompt excludes runbook section when no keyword matches.
  - System prompt includes learnings content.
  - Empty site knowledge skips the Site Knowledge section header.
  - Empty learnings skips the Learnings section header.
  - All sections present when all knowledge sources are populated.
  - Runbook section contains the 'takes precedence' note.
    - Real catalog.json matching uses keyword patterns, not markdown filenames.
    - PromptBuilder forwards raw alert rule/title metadata for matching.
"""

from __future__ import annotations

from corvin.core.contracts import InvestigationRequest, TriggerSource
from corvin.core.knowledge_loader import KnowledgeLoader
from corvin.investigation.prompt_builder import PromptBuilder


# ---------------------------------------------------------------------------
# Fake KnowledgeLoader
# ---------------------------------------------------------------------------


class FakeKnowledgeLoader:
    """Controllable stand-in for KnowledgeLoader used in unit tests."""

    def __init__(
        self,
        site_knowledge: str = "",
        matching_runbooks: list[str] | None = None,
        learnings: str = "",
    ) -> None:
        self._site_knowledge = site_knowledge
        self._matching_runbooks = matching_runbooks if matching_runbooks is not None else []
        self._learnings = learnings
        # Track what alert_text was passed to load_matching_runbooks
        self.last_alert_text: str = ""

    def load_site_knowledge(self, service_name: str | None = None) -> str:
        return self._site_knowledge

    def load_matching_runbooks(self, alert_text: str, service_name: str | None = None) -> list[str]:
        self.last_alert_text = alert_text
        return self._matching_runbooks

    def load_learnings(self) -> str:
        return self._learnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SITE = "## AKS Cluster\n- Cluster: my-aks\n- Region: eastus"
_RUNBOOK = "# APIM 5xx Runbook\n## Step 1: Check APIM logs"
_LEARNINGS = "## Incident 2026-01-15\n- Root cause was a bad deploy"


def _make_request(description: str = "APIM 5xx spike on order-service") -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="order-service",
        environment="production",
        description=description,
    )


def _builder_with(
    site: str = "",
    runbooks: list[str] | None = None,
    learnings: str = "",
) -> PromptBuilder:
    loader = FakeKnowledgeLoader(
        site_knowledge=site,
        matching_runbooks=runbooks,
        learnings=learnings,
    )
    return PromptBuilder(knowledge_loader=loader)


def _real_loader() -> KnowledgeLoader:
    return KnowledgeLoader(
        config={
            "knowledge_path": "knowledge/site.md",
            "runbooks_path": "knowledge/runbooks",
            "learnings_path": "knowledge/learnings",
            "learnings_max_chars": 4000,
            "runbook_max_chars": 3000,
        }
    )


# ---------------------------------------------------------------------------
# Section presence tests
# ---------------------------------------------------------------------------


def test_prompt_includes_site_knowledge():
    """When site.md has content, it appears in the prompt under Site Knowledge."""
    builder = _builder_with(site=_SITE)
    prompt = builder.build(_make_request())

    assert "## Site Knowledge" in prompt
    assert "my-aks" in prompt


def test_prompt_includes_matched_runbook():
    """When a runbook matches, it appears in the prompt under Relevant Runbook."""
    builder = _builder_with(runbooks=[_RUNBOOK])
    prompt = builder.build(_make_request())

    assert "## Relevant Runbook" in prompt
    assert "APIM 5xx Runbook" in prompt


def test_prompt_runbook_section_has_precedence_note():
    """The runbook section must include the 'takes precedence' note."""
    builder = _builder_with(runbooks=[_RUNBOOK])
    prompt = builder.build(_make_request())

    assert "takes precedence" in prompt


def test_prompt_includes_learnings():
    """When learnings exist, they appear in prompt under Learnings from Past Incidents."""
    builder = _builder_with(learnings=_LEARNINGS)
    prompt = builder.build(_make_request())

    assert "## Learnings from Past Incidents" in prompt
    assert "Incident 2026-01-15" in prompt


def test_prompt_all_sections_present_when_all_populated():
    """When all three sources have content, all three section headers appear."""
    builder = _builder_with(site=_SITE, runbooks=[_RUNBOOK], learnings=_LEARNINGS)
    prompt = builder.build(_make_request())

    assert "## Site Knowledge" in prompt
    assert "## Relevant Runbook" in prompt
    assert "## Learnings from Past Incidents" in prompt


# ---------------------------------------------------------------------------
# Empty section exclusion tests
# ---------------------------------------------------------------------------


def test_prompt_skips_site_knowledge_section_when_empty():
    """Empty site knowledge must not produce a Site Knowledge section header."""
    builder = _builder_with(site="", runbooks=[_RUNBOOK], learnings=_LEARNINGS)
    prompt = builder.build(_make_request())

    assert "## Site Knowledge" not in prompt


def test_prompt_skips_runbook_section_when_no_match():
    """When no runbooks match, the Relevant Runbook section must be absent."""
    builder = _builder_with(site=_SITE, runbooks=[], learnings=_LEARNINGS)
    prompt = builder.build(_make_request())

    assert "## Relevant Runbook" not in prompt
    assert "takes precedence" not in prompt


def test_prompt_skips_learnings_section_when_empty():
    """Empty learnings must not produce a Learnings section header."""
    builder = _builder_with(site=_SITE, runbooks=[_RUNBOOK], learnings="")
    prompt = builder.build(_make_request())

    assert "## Learnings from Past Incidents" not in prompt


def test_prompt_is_empty_string_when_all_sources_empty(monkeypatch):
    """With no content in any source and a default description, build() returns an empty string."""
    # PromptBuilder also injects DB-backed predictive penalties; other tests in
    # the same run may have written penalty rows for this fixture service, so
    # pin that source to empty too.
    monkeypatch.setattr(
        "corvin.triggers.prediction_penalty.load_penalties_for_service",
        lambda service_name, limit=10: [],
    )
    builder = _builder_with(site="", runbooks=[], learnings="")
    # Use a blank/default description so no Operator Context section is injected either.
    request = _make_request(description="manual investigation")
    prompt = builder.build(request)

    assert prompt == ""


def test_operator_context_section_injected_for_meaningful_description():
    """A non-default description is injected as an ## Operator Context section."""
    builder = _builder_with(site="", runbooks=[], learnings="")
    request = _make_request(description="APIM 5xx spike on order-service")
    prompt = builder.build(request)

    assert "## Operator Context" in prompt
    assert "APIM 5xx spike on order-service" in prompt


# ---------------------------------------------------------------------------
# Alert text forwarding test
# ---------------------------------------------------------------------------


def test_alert_text_includes_service_name_and_description():
    """The text passed to load_matching_runbooks includes both service name and description."""
    fake_loader = FakeKnowledgeLoader(site_knowledge=_SITE)
    builder = PromptBuilder(knowledge_loader=fake_loader)
    request = _make_request(description="crashloop pod restarting")
    builder.build(request)

    assert "order-service" in fake_loader.last_alert_text
    assert "crashloop" in fake_loader.last_alert_text


def test_alert_text_includes_raw_alert_rule_when_present():
    """PromptBuilder must forward raw alert rule metadata for runbook matching."""
    fake_loader = FakeKnowledgeLoader(site_knowledge=_SITE)
    builder = PromptBuilder(knowledge_loader=fake_loader)
    request = InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="order-service",
        environment="production",
        description="generic threshold alert",
        raw_payload={
            "data": {
                "essentials": {
                    "alertRule": "APIM Gateway 5xx Spike",
                }
            }
        },
    )

    builder.build(request)

    assert "APIM Gateway 5xx Spike" in fake_loader.last_alert_text


def test_real_loader_matches_catalog_pattern_not_filename():
    """Real loader must match via catalog patterns even when filename stem is absent."""
    loader = _real_loader()

    runbooks = loader.load_matching_runbooks("gateway 5xx error spike")

    assert len(runbooks) == 1
    assert "APIM 5xx Spike Investigation" in runbooks[0]


def test_real_prompt_match_uses_raw_alert_rule_from_payload():
    """Real catalog match should work when the keyword only exists in raw alert metadata."""
    builder = PromptBuilder(knowledge_loader=_real_loader())
    request = InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="order-service",
        environment="production",
        description="generic threshold alert",
        raw_payload={
            "data": {
                "essentials": {
                    "alertRule": "APIM Gateway 5xx Spike",
                }
            }
        },
    )

    prompt = builder.build(request)

    assert "## Relevant Runbook" in prompt
    assert "APIM 5xx Spike Investigation" in prompt


# ---------------------------------------------------------------------------
# Engine integration test
# ---------------------------------------------------------------------------


def test_engine_calls_prompt_builder(monkeypatch):
    """InvestigationEngine.run() calls PromptBuilder.build() with the request."""
    from unittest.mock import MagicMock

    from corvin.core.contracts import (
        EvidenceBundle,
        FixStrategyOutput,
        RCAOutput,
    )
    from corvin.investigation.engine import InvestigationEngine

    mock_builder = MagicMock()
    mock_builder.build.return_value = "system prompt text"

    request = _make_request()

    fake_evidence = EvidenceBundle(request_id=request.id)
    fake_rca = RCAOutput(
        request_id=request.id,
        summary="test rca",
        root_cause="test cause",
    )
    fake_fix = FixStrategyOutput(
        request_id=request.id,
        summary="test fix",
        justification="test justification",
    )

    mock_enrichment = MagicMock()
    mock_enrichment.enrich.return_value = fake_evidence
    mock_rca = MagicMock()
    mock_rca.generate.return_value = fake_rca
    mock_fix = MagicMock()
    mock_fix.generate.return_value = fake_fix

    engine = InvestigationEngine(
        enrichment=mock_enrichment,
        rca=mock_rca,
        fix_strategy=mock_fix,
        prompt_builder=mock_builder,
    )
    engine.run(request)

    mock_builder.build.assert_called_once_with(request)
