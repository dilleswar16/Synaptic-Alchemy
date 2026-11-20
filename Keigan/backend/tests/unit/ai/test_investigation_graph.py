"""keigan/ai/investigation_graph.py: how model output is validated before it is stored (V8, V9, V20)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.investigation_ai_schemas import CodeChange, FixStep, HypothesisResult, ProposedFix
from keigan.ai.investigation_graph import InvestigationGraphRunner
from keigan.ai.prompt_safety import build_valid_citation_codes, restrict_to_known_file_path


@pytest.fixture
def runner() -> InvestigationGraphRunner:
    graph_runner = InvestigationGraphRunner(None, SimpleNamespace(), offline_ai=True)  # type: ignore[arg-type]
    graph_runner.evidence_rows = [SimpleNamespace(evidence_code="E1"), SimpleNamespace(evidence_code="E2")]  # type: ignore[list-item]
    graph_runner.runbook_matches = [SimpleNamespace(reference_code="R1", runbook_title="Restart the pool", runbook_steps_markdown="1. Restart")]
    graph_runner.knowledge_reference_codes = {"K1", "K2"}
    graph_runner.knowledge_markdown = "[K1] Claims API\nThe handler is src/main/java/com/acme/ClaimsController.java and config is in deploy/values.yaml"
    return graph_runner


def hypothesis_result(**overrides: object) -> HypothesisResult:
    values: dict[str, object] = dict(
        hypothesis_title="Pool exhausted", hypothesis_statement_markdown="The pool is exhausted [E1] [K1] [K9].", reasoning_markdown="See [E2], [R1], [K2] and [E7].",
        confidence_score=0.6, supporting_evidence_codes=["E1", "E7"], contradicting_evidence_codes=["E2"], proposed_fix=ProposedFix(summary="Raise the pool size"),
    )
    values.update(overrides)
    return HypothesisResult(**values)  # type: ignore[arg-type]


class TestBuildValidCitationCodes:
    def test_combines_evidence_runbook_and_knowledge_codes(self) -> None:
        assert build_valid_citation_codes(["E1"], ["R1"], ["K1", "K2"]) == {"E1", "R1", "K1", "K2"}

    def test_without_knowledge_no_knowledge_code_is_valid(self) -> None:
        assert "K1" not in build_valid_citation_codes(["E1"], [], [])


class TestRestrictToKnownFilePath:
    KNOWLEDGE = "Handler: src/main/java/com/acme/ClaimsController.java\nConfig: deploy\\values.yaml"

    def test_keeps_a_path_that_appears_in_the_knowledge(self) -> None:
        assert restrict_to_known_file_path("src/main/java/com/acme/ClaimsController.java", self.KNOWLEDGE) == "src/main/java/com/acme/ClaimsController.java"

    def test_accepts_a_leading_dot_slash_and_other_slash_style(self) -> None:
        assert restrict_to_known_file_path("./deploy/values.yaml", self.KNOWLEDGE) == "./deploy/values.yaml"

    def test_replaces_an_invented_path(self) -> None:
        assert restrict_to_known_file_path("src/main/java/com/acme/Invented.java", self.KNOWLEDGE) == "file not identified"

    def test_keeps_the_placeholder(self) -> None:
        assert restrict_to_known_file_path("file not identified", self.KNOWLEDGE) == "file not identified"


class TestValidatedHypothesis:
    def test_knowledge_citations_that_exist_are_kept_and_invented_ones_removed(self, runner: InvestigationGraphRunner) -> None:
        validated = runner._validated_hypothesis("application", hypothesis_result())
        assert validated["hypothesis_statement_markdown"] == "The pool is exhausted [E1] [K1] ."
        assert validated["reasoning_markdown"] == "See [E2], [R1], [K2] and ."

    def test_evidence_code_lists_keep_only_codes_that_exist(self, runner: InvestigationGraphRunner) -> None:
        validated = runner._validated_hypothesis("application", hypothesis_result())
        assert validated["supporting_evidence_codes"] == ["E1"]

    def test_code_change_file_paths_must_appear_in_the_knowledge(self, runner: InvestigationGraphRunner) -> None:
        fix = ProposedFix(summary="s", code_changes=[
            CodeChange(file_path="src/main/java/com/acme/ClaimsController.java", change_description="a"),
            CodeChange(file_path="src/invented/Other.java", change_description="b"),
        ])
        validated = runner._validated_hypothesis("application", hypothesis_result(proposed_fix=fix))
        assert [change["file_path"] for change in validated["proposed_fix"]["code_changes"]] == ["src/main/java/com/acme/ClaimsController.java", "file not identified"]

    def test_links_and_images_in_fix_texts_are_neutralised(self, runner: InvestigationGraphRunner) -> None:
        fix = ProposedFix(
            summary="Read [this](https://evil.example/x) ![p](https://evil.example/p.png)", verification_steps=["Open https://evil.example/y"], rollback_steps=["[r](https://evil.example/z)"],
            steps=[FixStep(description="See <https://evil.example/s>")],
        )
        validated = runner._validated_hypothesis("application", hypothesis_result(proposed_fix=fix, hypothesis_title="[t](https://evil.example/t)"))
        serialised = str(validated)
        assert "](https://evil.example" not in serialised
        assert "![" not in serialised

    def test_a_namespaced_delete_command_raises_the_risk_to_high(self, runner: InvestigationGraphRunner) -> None:
        fix = ProposedFix(summary="s", steps=[FixStep(description="d", command_text="kubectl -n prod delete pod claims-api-0")])
        validated = runner._validated_hypothesis("application", hypothesis_result(proposed_fix=fix, fix_risk_level="low"))
        assert validated["fix_risk_level"] == "high"
        assert validated["proposed_fix"]["steps"][0]["command_risk_level"] == "high"

    def test_an_unknown_command_is_at_least_medium(self, runner: InvestigationGraphRunner) -> None:
        fix = ProposedFix(summary="s", steps=[FixStep(description="d", command_text="mytool --reset-everything")])
        assert runner._validated_hypothesis("application", hypothesis_result(proposed_fix=fix, fix_risk_level="low"))["fix_risk_level"] == "medium"


class TestSanitizedSynthesisText:
    def test_synthesis_text_keeps_real_knowledge_codes_and_drops_invented_ones(self, runner: InvestigationGraphRunner) -> None:
        cleaned = runner._clean_synthesis_text("Cause [E1] per [K2], not [K17] nor [R3].", {"R1": None})  # type: ignore[arg-type]
        assert cleaned == "Cause [E1] per [K2], not  nor ."

    def test_synthesis_text_has_links_neutralised_and_high_risk_blocks_flagged(self, runner: InvestigationGraphRunner) -> None:
        cleaned = runner._clean_synthesis_text("[x](https://evil.example)\n\n```bash\nkubectl -n prod delete pod a\n```", {})
        assert "](https://evil.example" not in cleaned
        assert "**High risk.**" in cleaned

    def test_the_allowed_hosts_come_from_settings(self, runner: InvestigationGraphRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_ai_safety_settings(), "ai_output_allowed_link_hosts", "docs.example.org")
        assert "[d](https://docs.example.org/a)" in runner._clean_synthesis_text("[d](https://docs.example.org/a)", {})
