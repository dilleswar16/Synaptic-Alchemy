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
    graph_runner = InvestigationGraphRunner(None, SimpleNamespace(investigation_id="investigation-1"), offline_ai=True)  # type: ignore[arg-type]
    graph_runner.evidence_rows = [  # type: ignore[list-item]
        SimpleNamespace(evidence_code="E1", check_outcome="signal", signal_strength="high", baseline_comparison="compared"),
        SimpleNamespace(evidence_code="E2", check_outcome="no_signal", signal_strength="low", baseline_comparison="compared"),
    ]
    graph_runner.runbook_matches = [SimpleNamespace(reference_code="R1", runbook_title="Restart the pool", runbook_steps_markdown="1. Restart")]
    graph_runner.knowledge_reference_codes = {"K1", "K2"}
    graph_runner.knowledge_markdown = "[K1] Claims API\nThe handler is src/main/java/com/acme/ClaimsController.java and config is in deploy/values.yaml"
    return graph_runner


def hypothesis_result(**overrides: object) -> HypothesisResult:
    values: dict[str, object] = dict(
        hypothesis_title="Pool exhausted", hypothesis_statement_markdown="The pool is exhausted [E1] [K1] [K9].", reasoning_markdown="See [E2], [R1], [K2] and [E7].",
        confidence_score=0.6, assessment="supported", assessment_reason_markdown="The pool is exhausted [E1] and [E9].", supporting_evidence_codes=["E1", "E7"], contradicting_evidence_codes=["E2"], proposed_fix=ProposedFix(summary="Raise the pool size"),
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


class TestAHypothesisStateIsCheckedAgainstTheEvidence:
    def test_a_supported_hypothesis_with_a_decisive_signal_keeps_its_state_and_its_reason_is_cleaned(self, runner: InvestigationGraphRunner) -> None:
        validated = runner._validated_hypothesis("application", hypothesis_result())
        assert (validated["hypothesis_state"], validated["proposed_hypothesis_state"], validated["state_guard_code"]) == ("supported", "supported", None)
        assert validated["state_reason_markdown"] == "The pool is exhausted [E1] and ."  # the invented [E9] is removed

    def test_support_that_cites_only_a_healthy_item_is_lowered_and_says_which_rule_did_it(self, runner: InvestigationGraphRunner) -> None:
        validated = runner._validated_hypothesis("application", hypothesis_result(supporting_evidence_codes=["E2"]))
        assert (validated["hypothesis_state"], validated["proposed_hypothesis_state"], validated["state_guard_code"]) == ("inconclusive", "supported", "support_not_in_evidence")

    def test_a_rule_out_that_cites_no_evidence_is_lowered(self, runner: InvestigationGraphRunner) -> None:
        validated = runner._validated_hypothesis("application", hypothesis_result(assessment="ruled_out", confidence_score=0.1, supporting_evidence_codes=[], contradicting_evidence_codes=["E9"]))
        assert (validated["hypothesis_state"], validated["state_guard_code"]) == ("inconclusive", "rule_out_not_in_evidence")

    def test_the_decision_is_kept_for_the_decision_trace(self, runner: InvestigationGraphRunner) -> None:
        assert runner._validated_hypothesis("application", hypothesis_result())["state_decision"].decisive_codes == ("E1",)


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

    @pytest.mark.parametrize(("command", "language", "reason"), [
        ("az webapp restart --name claims-web --resource-group <resource-group>", "bash", "unsafe_shell_syntax"),
        ("kubectl get pods; kubectl delete pod x", "bash", "unsafe_shell_syntax"),
        ("kubectl get secret db -o yaml > secret.txt", "bash", "unsafe_shell_syntax"),
        ("az webapp config appsettings set --name a --resource-group r --settings Db=Password=hunter2;X=1", "bash", "unsafe_shell_syntax"),
        ("UPDATE claims SET status = 'x' WHERE id = 1", "sql", "data_changing_sql"),
    ])
    def test_an_unsafe_command_is_withheld_but_its_risk_still_counts(self, runner: InvestigationGraphRunner, command: str, language: str, reason: str) -> None:
        fix = ProposedFix(summary="s", steps=[FixStep(description="Do the thing", command_text=command, command_language=language)])
        validated = runner._validated_hypothesis("application", hypothesis_result(proposed_fix=fix, fix_risk_level="low"))
        step = validated["proposed_fix"]["steps"][0]
        assert step["command_text"] is None and step["command_withheld_reason"] == reason and step["description"] == "Do the thing"
        assert step["command_risk_level"] is not None and validated["fix_risk_level"] != "low"

    def test_a_plain_command_is_kept_and_a_command_that_prints_secrets_is_marked(self, runner: InvestigationGraphRunner) -> None:
        fix = ProposedFix(summary="s", steps=[FixStep(description="a", command_text="kubectl get pods -n prod"), FixStep(description="b", command_text="kubectl get secret db -o yaml")])
        steps = runner._validated_hypothesis("application", hypothesis_result(proposed_fix=fix))["proposed_fix"]["steps"]
        assert steps[0]["command_text"] == "kubectl get pods -n prod" and steps[0]["command_withheld_reason"] is None and steps[0]["command_warnings"] == []
        assert steps[1]["command_risk_level"] == "high" and steps[1]["command_warnings"] == ["prints_secrets"]

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

    def test_an_unsafe_command_block_in_the_synthesis_is_replaced_by_a_note(self, runner: InvestigationGraphRunner) -> None:
        cleaned = runner._clean_synthesis_text("Restart it.\n\n```bash\naz webapp restart --name a --resource-group <resource-group>\n```\n\nThen check.", {})
        assert "Command not shown" in cleaned and "<resource-group>" not in cleaned and "```" not in cleaned and "Then check." in cleaned

    def test_a_safe_block_stays_and_a_secret_printing_one_is_marked(self, runner: InvestigationGraphRunner) -> None:
        safe = runner._clean_synthesis_text("```bash\nkubectl get pods -n prod\n```", {})
        assert "kubectl get pods -n prod" in safe and "Command not shown" not in safe
        secret = runner._clean_synthesis_text("```bash\nkubectl get secret db -o yaml\n```", {})
        assert "**Prints secrets.**" in secret and "**High risk.**" in secret

    def test_the_allowed_hosts_come_from_settings(self, runner: InvestigationGraphRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_ai_safety_settings(), "ai_output_allowed_link_hosts", "docs.example.org")
        assert "[d](https://docs.example.org/a)" in runner._clean_synthesis_text("[d](https://docs.example.org/a)", {})


class TestEvidenceStageWiring:
    """The planner prompt and the change evidence share what the validators and the masking context know (V10, V12)."""

    @staticmethod
    def _runner_with_stubs() -> tuple[InvestigationGraphRunner, dict[str, object]]:
        from datetime import UTC, datetime, timedelta

        from keigan.services.evidence_service import EvidenceService
        from keigan.utils.pii_masker import MaskingContext

        seen: dict[str, object] = {}
        window_end = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

        class EvidenceServiceStub:
            describe_query_limits_for_planner = staticmethod(EvidenceService.describe_query_limits_for_planner)

            async def collect_evidence(self, *_arguments: object) -> list[object]:
                return []

            async def collect_change_evidence(self, *arguments: object, **keyword_arguments: object) -> tuple[list[object], None]:
                seen["change_evidence_arguments"] = (arguments, keyword_arguments)
                return [], None

            async def run_planned_queries(self, *_arguments: object) -> list[object]:
                return []

        async def ask(feature_name: str, prompt_sections: list[object], output_schema: type) -> object:
            seen["prompt_section_titles"] = [section.title for section in prompt_sections]  # type: ignore[attr-defined]
            return output_schema(queries=[])

        async def update_progress(*_arguments: object) -> None:
            return None

        graph_runner = InvestigationGraphRunner(None, SimpleNamespace(investigation_id="investigation-1"), offline_ai=True)  # type: ignore[arg-type]
        graph_runner.investigation = SimpleNamespace(  # type: ignore[assignment]
            investigation_window_start=window_end - timedelta(hours=1), investigation_window_end=window_end,
            baseline_window_start=window_end - timedelta(days=1), baseline_window_end=window_end - timedelta(hours=23),
        )
        graph_runner.application = SimpleNamespace(application_id="application-1")  # type: ignore[assignment]
        graph_runner.services, graph_runner.service_contexts, graph_runner.evidence_drafts = [], [], []
        graph_runner.incident_text = "checkout failing"
        graph_runner.masking_context = MaskingContext()
        graph_runner.evidence_service = EvidenceServiceStub()  # type: ignore[assignment]
        graph_runner._ask = ask  # type: ignore[method-assign]
        graph_runner._update_progress = update_progress  # type: ignore[method-assign]
        graph_runner._describe_services = lambda _services: "none"  # type: ignore[method-assign]
        return graph_runner, seen

    async def test_planner_is_told_what_each_log_source_allows(self) -> None:
        graph_runner, seen = self._runner_with_stubs()

        await graph_runner.planner_node({})  # type: ignore[arg-type]

        assert "Query limits per service" in seen["prompt_section_titles"]  # type: ignore[operator]

    async def test_change_evidence_shares_the_masking_context_of_the_investigation(self) -> None:
        graph_runner, seen = self._runner_with_stubs()

        await graph_runner.evidence_node({})  # type: ignore[arg-type]

        _arguments, keyword_arguments = seen["change_evidence_arguments"]  # type: ignore[misc]
        assert keyword_arguments["masking_context"] is graph_runner.masking_context


class TestFailedSloGuardrailIsLogged:
    async def test_a_tier_one_guardrail_that_cannot_read_slos_is_a_warning_that_names_the_application(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from keigan.entities.status_values import CriticalityTier
        from keigan.services.slo_service import SloService

        async def unavailable(self: SloService, application_ids: list[str]) -> list[dict[str, object]]:
            raise RuntimeError("slo store unavailable")

        monkeypatch.setattr(SloService, "summarize_slos", unavailable)
        graph_runner = InvestigationGraphRunner(None, SimpleNamespace(investigation_id="investigation-1"), offline_ai=True)  # type: ignore[arg-type]
        graph_runner.application = SimpleNamespace(application_id="application-42", criticality_tier=CriticalityTier.TIER_1)  # type: ignore[assignment]
        assert await graph_runner._guardrail_priority() is None
        assert any(record.levelno == logging.WARNING and "application-42" in record.getMessage() for record in caplog.records)


class TestFailedImpactedSloLookupIsLoggedAndTheBlastRadiusStillBuilds:
    async def test_the_blast_radius_is_built_without_slos_and_the_failure_is_a_warning_that_names_the_application(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from keigan.entities.status_values import CriticalityTier
        from keigan.services.slo_service import SloService

        async def unavailable(self: SloService, application_ids: list[str]) -> list[dict[str, object]]:
            raise RuntimeError("slo store unavailable")

        class NoStakeholdersSession:
            async def scalars(self, statement: object) -> SimpleNamespace:
                return SimpleNamespace(all=lambda: [])

            async def commit(self) -> None:
                return None

            async def flush(self) -> None:
                return None

        monkeypatch.setattr(SloService, "summarize_slos", unavailable)
        graph_runner = InvestigationGraphRunner(None, SimpleNamespace(investigation_id="investigation-1"), offline_ai=True)  # type: ignore[arg-type]
        graph_runner.session = NoStakeholdersSession()  # type: ignore[assignment]
        from keigan.entities.application_entities import Application

        graph_runner.application = Application(application_id="application-43", application_name="Claims", application_code="CLM", criticality_tier=CriticalityTier.TIER_2, region_code="eu")  # type: ignore[assignment]
        graph_runner.all_services = []
        graph_runner.services = []
        graph_runner.dependencies = []
        graph_runner.evidence_rows = []
        graph_runner.evidence_only = True  # no narrative model call in this test
        from keigan.entities.incident_entities import Investigation

        graph_runner.investigation = Investigation(investigation_id="investigation-44", application_id="application-43")  # type: ignore[assignment]
        await graph_runner.blast_radius_node({})  # type: ignore[arg-type]
        assert graph_runner.investigation.blast_radius_json["impactedSlos"] == []  # the blast radius is still written, without SLOs
        assert any(record.levelno == logging.WARNING and "application-43" in record.getMessage() for record in caplog.records)
