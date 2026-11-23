"""Realistic offline AI responses for ``LLM_PROVIDER=mock`` (and for seeding historical investigations).

The graph publishes the real, collected evidence through :data:`mock_investigation_context`; the factories registered at
the bottom of this file turn that evidence plus the matching ``SCENARIO_CATALOG`` entry into plausible, evidence-citing
triage, hypotheses (with ``kubectl`` / ``az`` commands that use real resource names), synthesis, English and Japanese
communications and postmortems. With a real provider none of this runs; the same pipeline produces real analysis.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from keigan.ai.investigation_ai_schemas import (
    AdditionalQueryPlan, BlastRadiusNarrative, CodeChange, CommunicationDraft, CommunicationDraftSet, FixStep, HypothesisResult, PostmortemActionItem,
    PostmortemResult, PostmortemTimelineEntry, ProposedFix, RcaSynthesisResult, TriageResult,
)
from keigan.ai.llm_gateway import PromptSection, register_mock_response
from keigan.ai.prompt_safety import assess_prompt_injection
from keigan.config.settings import get_settings
from keigan.entities.status_values import InvestigationOutcome, Priority, RiskLevel
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG


@dataclass
class MockServiceInfo:
    service_id: str
    name: str
    service_type: str
    namespace: str | None = None
    resource_group: str | None = None
    resource_identifier: str | None = None


@dataclass
class MockInvestigationContext:
    application_name: str
    services: list[MockServiceInfo]
    evidence: list[dict[str, Any]]  # code, service_name, category, strength, title, summary, is_rule_out
    scenario_key: str | None = None
    primary_service_name: str | None = None
    dependency_service_name: str | None = None
    priority: str = Priority.P3
    incident_title: str = ""
    # filled progressively by the graph / postmortem writer
    synthesis: dict[str, Any] = field(default_factory=dict)
    timeline_lines: list[tuple[str, str]] = field(default_factory=list)
    duration_minutes: int | None = None


mock_investigation_context: ContextVar[MockInvestigationContext | None] = ContextVar("mock_investigation_context", default=None)


class _Citations(dict):  # type: ignore[type-arg]
    def __missing__(self, key: str) -> str:
        return ""


# ── Evidence helpers ───────────────────────────────────────────────────────────
def _pick(context: MockInvestigationContext, categories: tuple[str, ...], service_name: str | None = None, include_rule_outs: bool = False) -> str:
    strength_order = {"high": 0, "medium": 1, "low": 2}
    candidates = [
        item for item in context.evidence
        if item["category"] in categories and (service_name is None or item["service_name"] == service_name) and (include_rule_outs or not item.get("is_rule_out"))
    ]
    candidates.sort(key=lambda item: strength_order.get(item["strength"], 3))
    return f"[{candidates[0]['code']}]" if candidates else ""


def _citations(context: MockInvestigationContext) -> _Citations:
    primary, dependency = context.primary_service_name, context.dependency_service_name
    rule_out = next((item for item in context.evidence if item.get("is_rule_out")), None)
    return _Citations(
        p=primary or "the affected service", d=dependency or "its dependency", app=context.application_name,
        c_logs=_pick(context, ("error_logs", "failed_requests", "exceptions", "batch_failures"), primary) or _pick(context, ("error_logs", "failed_requests", "exceptions", "batch_failures")),
        c_exc=_pick(context, ("exceptions", "error_logs"), primary), c_req=_pick(context, ("failed_requests", "slow_requests"), primary) or _pick(context, ("failed_requests",)),
        c_change=_pick(context, ("change_event",)), c_dep=_pick(context, ("failed_dependencies",), primary) or _pick(context, ("failed_dependencies", "error_logs"), dependency),
        c_dep_logs=_pick(context, ("error_logs", "failed_requests", "exceptions"), dependency),
        c_metric=_pick(context, ("metrics",), primary), c_dep_metric=_pick(context, ("metrics",), dependency) or _pick(context, ("metrics",)),
        c_kube=_pick(context, ("kubernetes_events",), primary), c_restart=_pick(context, ("pod_restarts",), primary), c_probe=_pick(context, ("synthetic_probe",)),
        c_slow=_pick(context, ("slow_requests",), primary), c_rule=f"[{rule_out['code']}]" if rule_out else "",
    )


def _service(context: MockInvestigationContext, name: str | None) -> MockServiceInfo | None:
    return next((service for service in context.services if service.name == name), None)


def _restart_command(service: MockServiceInfo | None) -> FixStep:
    if service is None:
        return FixStep(description="Restart the affected service through the normal change process.")
    if service.service_type == "aks":
        return FixStep(description=f"Restart {service.name} so new pods pick up the corrected configuration.", command_text=f"kubectl rollout restart deployment/{service.name} -n {service.namespace or 'default'}", command_language="bash")
    if service.service_type in ("function_app", "app_service"):
        command_group, kind_text = ("functionapp", "function app") if service.service_type == "function_app" else ("webapp", "app service")
        if not service.resource_group:
            return FixStep(description=f"Restart the {kind_text} {service.name}. Look up its resource group first: the service catalogue does not name one.")
        return FixStep(description=f"Restart the {kind_text} {service.name}.", command_text=f"az {command_group} restart --name {service.name} --resource-group {service.resource_group}", command_language="bash")
    return FixStep(description=f"Restart {service.name} through the normal change process.")


def _rollback_command(service: MockServiceInfo | None, release_text: str) -> FixStep:
    if service is not None and service.service_type == "aks":
        return FixStep(description=f"Roll back {service.name} to the previous revision ({release_text}).", command_text=f"kubectl rollout undo deployment/{service.name} -n {service.namespace or 'default'}", command_language="bash")
    if service is not None and service.service_type in ("app_service", "function_app"):
        command_group = "webapp" if service.service_type == "app_service" else "functionapp"
        if not service.resource_group:
            return FixStep(description=f"Swap the previous release back into production ({release_text}). Look up the resource group of {service.name} first: the service catalogue does not name one.")
        return FixStep(
            description=f"Swap the previous release back into production ({release_text}).",
            command_text=f"az {command_group} deployment slot swap --name {service.name} --resource-group {service.resource_group} --slot staging --target-slot production",
            command_language="bash",
        )
    return FixStep(description=f"Roll back the last release ({release_text}) through the release pipeline.")


def _setting_command(service: MockServiceInfo | None, setting: str, value: str) -> FixStep:
    if service is not None and service.service_type == "aks":
        return FixStep(description=f"Restore {setting}={value} on {service.name}.", command_text=f"kubectl set env deployment/{service.name} {setting}={value} -n {service.namespace or 'default'}", command_language="bash")
    if service is None or not service.resource_group:  # no guessed names and no placeholders: the engineer looks the missing value up first
        return FixStep(description=f"Restore {setting}={value}. Look up the app and its resource group first: the service catalogue does not name them.")
    command_group = "functionapp" if service.service_type == "function_app" else "webapp"
    return FixStep(description=f"Restore {setting}={value}.", command_text=f"az {command_group} config appsettings set --name {service.name} --resource-group {service.resource_group} --settings {setting}={value}", command_language="bash")


# ── Scenario scripts ───────────────────────────────────────────────────────────
def _fix_database_connection_pool_exhaustion(context: MockInvestigationContext) -> ProposedFix:
    primary, dependency = _service(context, context.primary_service_name), _service(context, context.dependency_service_name)
    sql_check = (
        f"az monitor metrics list --resource {dependency.resource_identifier} --metric sessions_percent --interval PT5M --aggregation Maximum"
        if dependency and dependency.resource_identifier else None
    )
    return ProposedFix(
        summary="Restore the previous batch import concurrency, restart the service to release saturated connections, then cap parallelism below the pool size.",
        steps=[
            _setting_command(primary, "BATCH_IMPORT_PARALLELISM", "4"),
            _restart_command(primary),
            FixStep(description="Confirm SQL sessions are falling back below 60 percent.", command_text=sql_check, command_language="bash" if sql_check else None),
            FixStep(description="Durable fix: size the connection pool for peak parallelism and reject configuration where parallelism exceeds the pool."),
        ],
        code_changes=[
            CodeChange(
                repository_name=primary.name if primary else None, file_path="file not identified (batch import and connection pool configuration of " + (primary.name if primary else "the service") + ")",
                change_description="Cap batch import parallelism at the connection pool size and fail fast at startup when the configuration exceeds it.",
                before_snippet="batch.import.parallelism: 16\nhikari.maximumPoolSize: 10", after_snippet="batch.import.parallelism: 4\nhikari.maximumPoolSize: 20  # parallelism must stay below pool size",
            )
        ],
        verification_steps=["Failed requests on POST /api/claims return to baseline within 10 minutes.", "SQL sessions stay below 60 percent for 30 minutes."],
        rollback_steps=["If errors persist, scale the service back to its previous replica count and reopen the investigation."],
    )


def _fix_bad_deployment_null_reference(context: MockInvestigationContext) -> ProposedFix:
    primary = _service(context, context.primary_service_name)
    return ProposedFix(
        summary="Roll back to the previous release now; ship a null-safe fix and a regression test before redeploying.",
        steps=[
            _rollback_command(primary, "release 2026.11.19.1"),
            FixStep(description="Verify the policy lookup operation returns HTTP 200 for a legacy policy (one without riders)."),
            FixStep(description="Hot-fix: handle policies whose riders list is null, add a regression test with a legacy policy, redeploy through the pipeline."),
        ],
        code_changes=[
            CodeChange(
                repository_name=primary.name if primary else None, file_path="file not identified (PolicyMapper.MapRiders, line 87 in the stack trace)",
                change_description="Treat a missing riders list as empty.",
                before_snippet="var riders = policy.Riders.Select(MapRider).ToList();", after_snippet="var riders = (policy.Riders ?? Enumerable.Empty<Rider>()).Select(MapRider).ToList();",
            )
        ],
        verification_steps=["Exception count for System.NullReferenceException drops to zero.", "Failed requests for GET /api/policies/{id} return to baseline."],
        rollback_steps=["Redeploy release 2026.11.19.1 only after the hot-fix is verified in a staging slot."],
    )


def _fix_downstream_api_timeout(context: MockInvestigationContext) -> ProposedFix:
    return ProposedFix(
        summary="Stop amplifying the partner slowdown: enable the circuit-breaker fallback, add jitter to retries and engage the partner.",
        steps=[
            FixStep(description="Check the partner endpoint latency from a trusted host (read-only).", command_text='curl -s -o /dev/null -w "%{time_total}s\\n" https://api.partner-bank.example/payments/v2/health', command_language="bash"),
            FixStep(description="Enable the payment gateway circuit-breaker fallback so confirmations are queued instead of retried synchronously."),
            FixStep(description="Raise the incident with the partner bank's operations contact and share the timeout timestamps from the evidence."),
        ],
        code_changes=[
            CodeChange(
                repository_name=context.primary_service_name, file_path="file not identified (PaymentGatewayClient retry policy)",
                change_description="Use exponential back-off with jitter and a total retry budget instead of five immediate retries.",
                before_snippet="Policy.Handle<TaskCanceledException>().WaitAndRetryAsync(5, _ => TimeSpan.FromSeconds(1))",
                after_snippet="Policy.Handle<TaskCanceledException>().WaitAndRetryAsync(Backoff.DecorrelatedJitterBackoffV2(TimeSpan.FromSeconds(2), 3))",
            )
        ],
        verification_steps=["Outbound HTTP client pool usage falls below 70 percent.", "Confirmation latency returns below 10 seconds once the partner recovers."],
        rollback_steps=["Disable the fallback queue once the partner is healthy and drain deferred confirmations."],
    )


def _fix_node_memory_pressure_oom(context: MockInvestigationContext) -> ProposedFix:
    primary = _service(context, context.primary_service_name)
    namespace = (primary.namespace if primary else None) or "default"
    name = primary.name if primary else "the deployment"
    return ProposedFix(
        summary="Relieve memory pressure with a temporary limit increase and restart; fix the renderer's unreleased image buffers.",
        steps=[
            FixStep(description="Confirm which pods are close to the limit (read-only).", command_text=f"kubectl top pods -n {namespace}", command_language="bash"),
            FixStep(description=f"Temporarily raise the memory limit of {name} to 2Gi.", command_text=f"kubectl set resources deployment/{name} -n {namespace} --limits=memory=2Gi", command_language="bash"),
            FixStep(description="Restart the deployment to clear leaked memory.", command_text=f"kubectl rollout restart deployment/{name} -n {namespace}", command_language="bash"),
            FixStep(description="Durable fix: release image buffers after each render and add a memory-based alert at 80 percent of the limit."),
        ],
        code_changes=[
            CodeChange(
                repository_name=name, file_path="file not identified (document renderer image pipeline)", change_description="Dispose image buffers after each render.",
                before_snippet="var bitmap = Render(document);\nreturn bitmap.ToPng();", after_snippet="using var bitmap = Render(document);\nreturn bitmap.ToPng();",
            )
        ],
        verification_steps=[f"kubectl get pods -n {namespace} shows no new OOMKilled restarts for 30 minutes.", "Gateway 502 rate returns to baseline."],
        rollback_steps=[f"kubectl rollout undo deployment/{name} -n {namespace}  # if the restart makes things worse"],
    )


def _fix_certificate_expiry(context: MockInvestigationContext) -> ProposedFix:
    return ProposedFix(
        summary="Rotate the expired mutual-TLS client certificate and restart the dependent services so they load it.",
        steps=[
            FixStep(description="Confirm the expiry date of the certificate presented to policy-core (read-only).", command_text="openssl s_client -connect policy-core.internal.example:443 -servername policy-core.internal.example </dev/null 2>/dev/null | openssl x509 -noout -enddate", command_language="bash"),
            FixStep(description="Issue a replacement certificate and import it into Key Vault (vault and certificate names are not recorded in the knowledge base; confirm them with the platform team)."),
            _restart_command(_service(context, context.primary_service_name)),
            FixStep(description="Durable fix: add a certificate-expiry alert at 30, 14 and 7 days and automate rotation."),
        ],
        verification_steps=["TLS handshake errors disappear from the logs.", "Channel API availability returns above 99 percent."],
        rollback_steps=["No rollback is possible for an expired certificate; escalate to the certificate authority team if issuance is delayed."],
    )


def _fix_apim_backend_throttling(context: MockInvestigationContext) -> ProposedFix:
    return ProposedFix(
        summary="Raise the rate limit temporarily to stop user-facing 429 responses, then restore the 60 second polling interval in the mobile app.",
        steps=[
            FixStep(description="Raise the per-subscription limit in the inbound policy of the mobile policy-summary operation (change process applies)."),
            FixStep(description="Ship the mobile hot-fix that restores the 60 second polling interval and add client-side back-off on 429."),
            FixStep(description="After the hot-fix reaches most users, restore the original rate limit."),
        ],
        code_changes=[
            CodeChange(
                repository_name=context.primary_service_name, file_path="file not identified (API Management inbound policy for GET /mobile/v3/policy-summary)",
                change_description="Temporary increase of the rate limit.", before_snippet='<rate-limit-by-key calls="100" renewal-period="60" counter-key="@(context.Subscription.Id)" />',
                after_snippet='<rate-limit-by-key calls="400" renewal-period="60" counter-key="@(context.Subscription.Id)" />',
            )
        ],
        verification_steps=["429 responses drop below 1 percent.", "Request volume per subscription returns to the baseline rate."],
        rollback_steps=["Restore the previous policy revision of the API in API Management."],
    )


def _fix_batch_job_abend(context: MockInvestigationContext) -> ProposedFix:
    return ProposedFix(
        summary="Correct or skip the malformed input record, then restart the job from the failed step as the runbook describes.",
        steps=[
            FixStep(description="Identify the malformed packed-decimal premium amount in PBIL.INPUT.D1119 from the dump of step STEP030."),
            FixStep(description="Correct or remove the record in a copy of the input data set (data change, requires batch operations approval)."),
            FixStep(description="Restart PBIL0400 from STEP030.", command_text="//PBIL0400 JOB (ACCT),'PREMIUM BILLING',RESTART=STEP030", command_language="text"),
            FixStep(description="Check that downstream statement generation starts and completes."),
        ],
        verification_steps=["PBIL0400 ends with condition code 0000.", "Downstream statements are produced for the billing cycle."],
        rollback_steps=["Keep the original input data set untouched so the run can be repeated."],
    )


def _fix_saas_vendor_outage(context: MockInvestigationContext) -> ProposedFix:
    return ProposedFix(
        summary="Nothing can be fixed on the Keigan side; track the vendor incident, inform employees and agree an ETA.",
        steps=[
            FixStep(description="Subscribe to the vendor status page incident and share the link with the incident channel."),
            FixStep(description="Post a banner or intranet notice that enrolment may be slow or unavailable."),
            FixStep(description="Open a priority ticket with the vendor support channel quoting the synthetic probe failure times."),
        ],
        verification_steps=["Synthetic probes succeed for three consecutive runs."],
        rollback_steps=["Not applicable: no change is made to MetLife systems."],
    )


SCENARIO_SCRIPTS: dict[str, dict[str, Any]] = {
    "database_connection_pool_exhaustion": {
        "lead": "application", "confidence": {"application": 0.86, "dependencies": 0.52, "infrastructure": 0.14}, "fix": _fix_database_connection_pool_exhaustion,
        "title": {"application": "Release raised batch import parallelism and exhausted the SQL connection pool", "dependencies": "Azure SQL reached its session limit", "infrastructure": "Compute saturation on the claims cluster"},
        "statement": {
            "application": "A configuration change shortly before onset raised parallel batch imports from 4 to 16 threads. {p} then ran out of pooled SQL connections and began timing out. {c_change} {c_logs}",
            "dependencies": "{d} hit its session and request limit, so {p} could not obtain connections. The database is the place where the failure surfaces, but the evidence points to the caller creating the load. {c_dep_metric} {c_dep}",
            "infrastructure": "There is no sign of node, memory or CPU saturation. Infrastructure is unlikely to be the cause. {c_rule}",
        },
        "reasoning": {
            "application": "1. Errors on {p} are connection acquisition timeouts, a pattern new compared with the baseline {c_logs}. 2. A configuration change preceded onset by minutes {c_change}. 3. {d} session usage rose in step with the errors {c_dep_metric}. The change explains both the new pattern and the timing.",
            "dependencies": "1. {d} shows elevated sessions {c_dep_metric} and errors {c_dep_logs}. 2. However the session growth starts after the configuration change {c_change}, which makes the database a victim rather than the origin. Confidence is moderate because the saturation itself is real.",
            "infrastructure": "1. Compute metrics stay within the baseline range {c_rule}. 2. Nothing in the evidence connects node-level resources to the connection timeouts.",
        },
        "what_went_wrong": "Claim submissions on {app} began failing with timeouts. Error patterns on {p} that did not exist before the incident ({c_logs}) show requests waiting for a database connection until they time out, and {d} was running at its session limit {c_dep_metric}.",
        "why": "A configuration change raised batch import parallelism from 4 to 16 {c_change}. Each import thread holds a database connection, so the connection pool of {p} was exhausted and normal requests queued behind the imports {c_logs}. {d} reached its session limit as a result {c_dep_metric}. Timing of the change, the first errors and the session growth line up within minutes.",
        "executive": "Claim submissions in {app} are failing because a recent configuration change overloaded the claims database connections. Customers see long waits and errors when submitting claims. The change can be reverted and the service restarted; recovery is expected within minutes of doing so.",
        "ja_cause": "直前の設定変更でバッチ取込の並列数が4から16に増え、データベース接続プールが枯渇したことが原因の可能性が高いと見ています。",
        "ja_impact": "保険金請求の送信が遅延またはエラーになっています。",
        "open_questions": ["Was the change to BATCH_IMPORT_PARALLELISM approved and tested against the SQL session limit?", "Are other services sharing the same database session limit?"],
        "actions": [("Add a startup validation that rejects batch parallelism greater than the connection pool size", "Claims platform team", 14, "prevent"), ("Alert when SQL sessions exceed 80 percent for 5 minutes", "Claims SRE team", 7, "detect"), ("Document and rehearse reverting configuration releases within 10 minutes", "Claims platform team", 21, "mitigate")],
        "lessons": ["Configuration changes can be as risky as code changes and need the same capacity review."],
    },
    "bad_deployment_null_reference": {
        "lead": "application", "confidence": {"application": 0.91, "dependencies": 0.1, "infrastructure": 0.06}, "fix": _fix_bad_deployment_null_reference,
        "title": {"application": "Release 2026.11.19.1 throws NullReferenceException for policies without riders", "dependencies": "A downstream dependency returning unexpected data", "infrastructure": "Platform or capacity problem"},
        "statement": {
            "application": "The latest release assumes every policy has a riders list. Legacy policies return null, and the mapper throws a NullReferenceException on every such request. {c_change} {c_exc}",
            "dependencies": "No dependency failures stand out; the exception is raised inside the service's own mapping code. {c_rule}",
            "infrastructure": "Resource metrics are normal and no restarts occurred; the failure is deterministic per request, which does not fit a capacity problem. {c_rule}",
        },
        "reasoning": {
            "application": "1. A deployment preceded onset {c_change}. 2. The only new exception type is System.NullReferenceException in the mapping code {c_exc}. 3. Failures concentrate on one operation, which points to a code path rather than a platform issue {c_req}.",
            "dependencies": "1. No new failed dependency calls appear. 2. The stack trace is inside application code. The dependency lens is excluded with moderate certainty.",
            "infrastructure": "1. No pod restarts or saturation signals. 2. Errors are proportional to a specific operation, not to load.",
        },
        "what_went_wrong": "Roughly one in five policy lookups on {app} returned HTTP 500 after the latest release {c_req}. The failing operation throws System.NullReferenceException {c_exc}.",
        "why": "Release 2026.11.19.1 was deployed shortly before the first errors {c_change}. It assumes every policy has a list of riders, but legacy policies return null, so the mapper dereferences null {c_exc}. Only legacy policies fail, which explains why the failure rate is a fraction of requests.",
        "executive": "A release this morning broke policy lookups for some older policies in {app}. Affected users see an error instead of the policy. Rolling back the release removes the problem; a corrected release will follow with a test for this case.",
        "ja_cause": "本日のリリースで、特定の古い契約（特約情報がない契約）の処理でエラーが発生していることが原因と見ています。",
        "ja_impact": "一部の契約照会でエラー（HTTP 500）が発生しています。",
        "open_questions": ["Which policy types lack riders in production data?", "Why did pre-production data not include a legacy policy?"],
        "actions": [("Add legacy policies (no riders) to the regression test data set", "Policy platform team", 10, "prevent"), ("Alert on a new exception type after every deployment", "Policy SRE team", 14, "detect"), ("Enable automatic rollback when error rate doubles within 10 minutes of a release", "Release engineering", 30, "mitigate")],
        "lessons": ["Test data must represent legacy shapes of production data."],
    },
    "downstream_api_timeout": {
        "lead": "dependencies", "confidence": {"application": 0.45, "dependencies": 0.84, "infrastructure": 0.12}, "fix": _fix_downstream_api_timeout,
        "title": {"application": "Retries without jitter amplify the partner slowdown", "dependencies": "The partner payment gateway is responding in more than 25 seconds", "infrastructure": "Network or compute limits on the payments platform"},
        "statement": {
            "application": "The payment client retries five times without jitter, multiplying the load on a slow partner and exhausting its own outbound HTTP pool. This worsens the incident but is not its trigger. {c_logs}",
            "dependencies": "The partner bank gateway is timing out calls to its confirm endpoint (more than 25 seconds). Every payment confirmation that depends on it is delayed. {c_dep} {c_logs}",
            "infrastructure": "Platform metrics are in range; nothing suggests the payments platform itself is constrained. {c_rule}",
        },
        "reasoning": {
            "application": "1. Retry attempts 1 to 5 appear in the logs {c_logs}. 2. Retries without jitter amplify an external slowdown, but the slowdown existed first {c_dep}.",
            "dependencies": "1. Calls to the partner endpoint time out after 25 s {c_logs}. 2. Dependency failures are new compared with the baseline {c_dep}. 3. Latency increased several-fold only on operations that call the partner {c_slow}.",
            "infrastructure": "1. CPU, memory and restart counters are normal {c_rule}. 2. Latency is confined to calls toward the partner.",
        },
        "what_went_wrong": "Payment confirmations in {app} are delayed by minutes. Outbound calls to the partner payment gateway time out after about 25 seconds {c_logs}, and dependency failures to that target are new {c_dep}.",
        "why": "The partner bank gateway slowed down. {p} retries each call up to five times without jitter, which amplifies load and exhausts the outbound HTTP client pool {c_logs}. The partner slowdown is the trigger; the retry design makes the effect worse and longer.",
        "executive": "Payment confirmations in {app} are delayed because our partner bank's service is responding very slowly. Payments are not lost but confirmations arrive late. We are engaging the partner and changing how our system retries so it does not add load.",
        "ja_cause": "提携銀行の決済ゲートウェイの応答遅延（25秒以上）が原因とみられ、再試行の仕組みが影響を拡大させています。",
        "ja_impact": "支払確認の通知が数分遅延しています。",
        "open_questions": ["Has the partner acknowledged a degradation on their side?", "Are deferred confirmations queued durably so none are lost?"],
        "actions": [("Add jitter and a total retry budget to the payment gateway client", "Payments platform team", 14, "prevent"), ("Alert on partner call latency p95 above 10 seconds", "Payments SRE team", 7, "detect"), ("Add a circuit-breaker fallback that queues confirmations", "Payments platform team", 30, "mitigate")],
        "lessons": ["Retries are load; unbounded retries convert a partner slowdown into our own outage."],
    },
    "node_memory_pressure_oom": {
        "lead": "infrastructure", "confidence": {"application": 0.55, "dependencies": 0.18, "infrastructure": 0.82}, "fix": _fix_node_memory_pressure_oom,
        "title": {"application": "A memory leak in the document renderer", "dependencies": "A dependency causing 502 responses at the gateway", "infrastructure": "Containers hit their 1 GiB memory limit and are OOMKilled"},
        "statement": {
            "application": "Memory in the document renderer grows steadily until the container limit is reached, which points at unreleased buffers in the application. This is the underlying defect. {c_metric} {c_restart}",
            "dependencies": "The 502 responses originate at the gateway because backend pods restart; no dependency fails first. {c_rule}",
            "infrastructure": "Containers of {p} reach their 1 GiB limit, are OOMKilled, back off and restart, so the gateway intermittently returns 502. {c_kube} {c_metric}",
        },
        "reasoning": {
            "application": "1. Memory climbs steadily across the window rather than spiking {c_metric}. 2. A leak explains why restarts help only temporarily {c_restart}. The code location is not identified in the knowledge base.",
            "dependencies": "1. Gateway errors follow the pod restarts in time {c_kube}. 2. No dependency shows its own failures first.",
            "infrastructure": "1. OOMKilled events and BackOff restarts are new {c_kube}. 2. Memory working set approaches the limit {c_metric}. 3. Restart counters rose in the same minutes {c_restart}. Timing aligns with the 502s.",
        },
        "what_went_wrong": "{app} saw intermittent 502 errors while pods of {p} restarted repeatedly. Kubernetes reports containers OOMKilled and backing off {c_kube}, and restart counts increased {c_restart}.",
        "why": "Containers of {p} reach their 1 GiB memory limit and are killed by the kernel {c_kube} {c_metric}. Memory grows by roughly 300 MB per hour, which indicates a leak in the document renderer rather than a one-off spike. While pods restart the gateway has no healthy backend and returns 502.",
        "executive": "Parts of {app} intermittently fail because a service keeps running out of memory and restarting. Users see occasional errors when documents are rendered. A temporary memory increase and restart stabilise it; the underlying memory leak needs a code fix.",
        "ja_cause": "ドキュメントレンダラーのコンテナがメモリ上限（1GiB）に達してOOMKilledとなり、再起動を繰り返していることが原因と見ています。",
        "ja_impact": "ゲートウェイで断続的に502エラーが発生しています。",
        "open_questions": ["Which release introduced the memory growth?", "Can the renderer be load tested with a memory profile before the next release?"],
        "actions": [("Fix the image buffer leak in the document renderer and add a soak test", "Claims platform team", 21, "prevent"), ("Alert when container memory exceeds 80 percent of its limit", "Claims SRE team", 7, "detect"), ("Set pod disruption budgets and a second replica to absorb restarts", "Claims platform team", 14, "mitigate")],
        "lessons": ["Restarts hide leaks; track memory trend, not only restart counts."],
    },
    "certificate_expiry": {
        "lead": "dependencies", "confidence": {"application": 0.3, "dependencies": 0.88, "infrastructure": 0.1}, "fix": _fix_certificate_expiry,
        "title": {"application": "A code or configuration change broke TLS calls", "dependencies": "The mutual-TLS client certificate for the policy core system expired at 00:00 UTC", "infrastructure": "Network or platform failure"},
        "statement": {
            "application": "No release or configuration change is visible near onset, so an application change is unlikely. {c_change}",
            "dependencies": "Every call to the policy core system fails the TLS handshake because the client certificate expired at 00:00 UTC. {c_logs}",
            "infrastructure": "Metrics and platform events are normal; the failure is a certificate validation error rather than a connectivity problem. {c_rule}",
        },
        "reasoning": {
            "application": "1. No deployment near the first error {c_change}. 2. Errors are TLS validation failures, not application exceptions.",
            "dependencies": "1. Errors state that the certificate expired {c_logs}. 2. The pattern is new and appears at exactly 00:00 UTC. 3. Failure ratio is above 60 percent across operations calling the same dependency.",
            "infrastructure": "1. No saturation or restarts {c_rule}. 2. Error text names certificate expiry, not network failure.",
        },
        "what_went_wrong": "Calls from {app} to the policy core system fail with TLS errors, so channel API operations that need policy data are unavailable {c_logs}.",
        "why": "The mutual-TLS client certificate used to call the policy core system expired at 00:00 UTC. The first failure appears at that moment and the error text states that the certificate has expired {c_logs}. No change was deployed, which fits a time-based cause.",
        "executive": "A security certificate that {app} uses to talk to the policy core system expired at midnight UTC, so most calls fail. A new certificate must be issued and loaded; service returns once it is in place.",
        "ja_cause": "ポリシーコアシステムへの接続に使用するクライアント証明書が00:00 UTCに期限切れとなったことが原因です。",
        "ja_impact": "チャネルAPIの多くの操作が利用できません。",
        "open_questions": ["Which team owns renewal of this certificate?", "Are other certificates from the same issuance batch about to expire?"],
        "actions": [("Automate certificate renewal and rotation in Key Vault", "Platform security team", 30, "prevent"), ("Alert 30, 14 and 7 days before any certificate expires", "Channel SRE team", 7, "detect"), ("Document the emergency issuance path and its approvers", "Platform security team", 14, "mitigate")],
        "lessons": ["A certificate inventory with owners and expiry alerts would have prevented a P1."],
    },
    "apim_backend_throttling": {
        "lead": "application", "confidence": {"application": 0.68, "dependencies": 0.25, "infrastructure": 0.62}, "fix": _fix_apim_backend_throttling,
        "title": {"application": "A mobile release polls the policy summary every 5 seconds", "dependencies": "Backend dependency slowness", "infrastructure": "API Management rate-limit policy is too low for current traffic"},
        "statement": {
            "application": "A new mobile app release polls the policy summary every 5 seconds instead of 60, multiplying request volume and tripping the gateway rate limit. {c_req} {c_metric}",
            "dependencies": "Backend responses are healthy; 429 is generated by the gateway itself. {c_rule}",
            "infrastructure": "The API Management rate-limit policy returns 429 once a subscription exceeds its quota, and the quota is now too low for the new traffic pattern. {c_logs}",
        },
        "reasoning": {
            "application": "1. Request volume on one operation rose about fourfold {c_metric}. 2. Throttling messages name the subscription and operation {c_logs}. 3. The increase matches a client polling change, not organic growth.",
            "dependencies": "1. Backend duration is normal {c_rule}. 2. 429 responses are produced by the gateway.",
            "infrastructure": "1. The rate-limit policy is working as configured {c_logs}. 2. Gateway capacity rose to 1.6x but did not saturate {c_metric}. The policy value is a contributing condition, the load change is the trigger.",
        },
        "what_went_wrong": "Mobile app users of {app} see \"too many requests\" when opening the policy summary. The gateway returned HTTP 429 at a much higher rate than before {c_req} {c_logs}.",
        "why": "Request volume to the policy summary operation rose about fourfold {c_metric}, consistent with a mobile release that polls every 5 seconds instead of 60. The API Management rate-limit policy then rejected requests over quota with 429 {c_logs}.",
        "executive": "Users of the mobile app in {app} are being blocked by a request limit after a new app release started contacting our service far more often. We can raise the limit temporarily and the app team will release a fix.",
        "ja_cause": "新しいモバイルアプリのリリースでポリシー概要の取得間隔が60秒から5秒になり、APIゲートウェイのレート制限（429）に達していることが原因と見ています。",
        "ja_impact": "モバイルアプリで「リクエストが多すぎます」と表示されます。",
        "open_questions": ["Which mobile app version introduced the polling interval change?", "Is a staged rollout of the fix available?"],
        "actions": [("Add client-side back-off on HTTP 429 in the mobile app", "Mobile app team", 14, "prevent"), ("Alert on a sudden rise in per-subscription request rate", "Channel SRE team", 7, "detect"), ("Document how to raise API Management rate limits safely", "Channel platform team", 14, "mitigate")],
        "lessons": ["Client release notes should state any change in polling or request frequency."],
    },
    "batch_job_abend": {
        "lead": "application", "confidence": {"application": 0.85, "dependencies": 0.3, "infrastructure": 0.12}, "fix": _fix_batch_job_abend,
        "title": {"application": "PBIL0400 abended S0C7 on a malformed packed-decimal premium amount", "dependencies": "A late or corrupt input feed", "infrastructure": "LPAR or storage problem on the mainframe"},
        "statement": {
            "application": "Job PBIL0400 ended with ABEND S0C7 (data exception) in program PBILCALC while processing a premium amount that is not valid packed decimal. {c_logs}",
            "dependencies": "The malformed record probably originates upstream, so an input feed is a contributing factor. The abend itself is data-driven. {c_logs}",
            "infrastructure": "No system-level problem is visible; S0C7 is a data exception, not a resource failure. {c_rule}",
        },
        "reasoning": {
            "application": "1. IEF450I and $HASP395 both report ABEND=S0C7 for step STEP030 {c_logs}. 2. S0C7 means arithmetic on invalid packed decimal data. 3. CEE3207S names program PBILCALC.",
            "dependencies": "1. A bad value in the input data set had to come from the upstream extract. 2. No evidence shows the feed was late.",
            "infrastructure": "1. No storage, CPU or LPAR events {c_rule}. 2. S0C7 does not indicate resource exhaustion.",
        },
        "what_went_wrong": "The nightly premium billing batch for {app} did not complete: job PBIL0400 abended in step STEP030 {c_logs}, so downstream statements were not produced.",
        "why": "PBIL0400 abended with S0C7, a data exception, in program PBILCALC {c_logs}. This happens when the program does arithmetic on a field that is not valid packed decimal, most likely a malformed premium amount in the input data set.",
        "executive": "The nightly premium billing run in {app} stopped part-way because one input record is malformed. Statements for the billing cycle are delayed until the record is corrected and the job is restarted from the failed step.",
        "ja_cause": "夜間の保険料請求バッチ（PBIL0400）が、入力データの不正な金額（パック10進数）によりS0C7でABENDしたことが原因です。",
        "ja_impact": "保険料の請求明細が作成されていません。",
        "open_questions": ["Which upstream extract produced the malformed premium amount?", "Is it safe to skip the record or must it be corrected first?"],
        "actions": [("Validate packed-decimal fields in the input extract before the billing job starts", "Premium billing team", 21, "prevent"), ("Alert operations within 5 minutes of any ABEND in the billing chain", "Mainframe operations", 7, "detect"), ("Document the restart procedure from STEP030 including data correction approval", "Premium billing team", 14, "mitigate")],
        "lessons": ["Data validation at the start of the batch chain is cheaper than a restart at 3 a.m."],
    },
    "saas_vendor_outage": {
        "lead": "dependencies", "confidence": {"application": 0.1, "dependencies": 0.9, "infrastructure": 0.1}, "fix": _fix_saas_vendor_outage,
        "title": {"application": "A defect in MetLife-owned configuration of the portal", "dependencies": "The SaaS vendor reports degraded performance in its APAC region", "infrastructure": "MetLife network path to the vendor"},
        "statement": {
            "application": "MetLife owns no code in this service and no change was made; an application cause is very unlikely. {c_change}",
            "dependencies": "The vendor is degraded in its APAC region and synthetic probes from Keigan fail intermittently with HTTP 503. {c_probe}",
            "infrastructure": "Failures are HTTP 503 responses from the vendor, not connection errors, so MetLife networking is unlikely to be involved. {c_probe}",
        },
        "reasoning": {
            "application": "1. No MetLife-side change near onset {c_change}. 2. The service is vendor-hosted.",
            "dependencies": "1. A large share of synthetic probes fail with 503 {c_probe}. 2. The vendor status page reports degraded performance in the same period.",
            "infrastructure": "1. Responses arrive, so connectivity works. 2. The 503 body comes from the vendor.",
        },
        "what_went_wrong": "Employees cannot reliably open the benefits portal of {app}; Keigan's synthetic probe fails about 40 percent of the time with HTTP 503 {c_probe}.",
        "why": "The SaaS vendor is experiencing degraded performance in its APAC region, which its status page confirms, and our probes see HTTP 503 and multi-second latency {c_probe}. No MetLife change is involved.",
        "executive": "The benefits portal is slow or unavailable because our vendor is having a service problem in the Asia-Pacific region. We are tracking the vendor's incident and will update employees when it is resolved.",
        "ja_cause": "SaaSベンダーのAPAC地域でパフォーマンス低下が発生しており、当社の監視でも503エラーを確認しています。",
        "ja_impact": "福利厚生ポータルが遅い、または一時的に利用できません。",
        "open_questions": ["What ETA has the vendor committed to?", "Should enrolment deadlines be extended while the vendor recovers?"],
        "actions": [("Negotiate a vendor SLA with regional failover and incident notification commitments", "Vendor management", 60, "prevent"), ("Subscribe operations to the vendor status feed so incidents are known within minutes", "Benefits SRE team", 7, "detect"), ("Prepare a standard employee notice template for vendor outages", "Benefits platform team", 14, "mitigate")],
        "lessons": ["For vendor-hosted services, detection and communication are our main levers."],
    },
}


# ── Generic (unknown scenario) behaviour ───────────────────────────────────────
def _generic_script(context: MockInvestigationContext) -> dict[str, Any]:
    strongest = next((item for item in sorted(context.evidence, key=lambda item: {"high": 0, "medium": 1, "low": 2}[item["strength"]]) if not item.get("is_rule_out")), None)
    lead = "infrastructure" if strongest and strongest["category"] in ("kubernetes_events", "pod_restarts", "metrics", "hardware_status") else "dependencies" if strongest and strongest["category"] in ("failed_dependencies", "synthetic_probe") else "application"
    confidence = {"application": 0.2, "dependencies": 0.2, "infrastructure": 0.2}
    confidence[lead] = 0.5 if strongest and strongest["strength"] == "high" else 0.35 if strongest else 0.15
    summary_text = strongest["summary"] if strongest else "No significant signal was found in the investigation window."
    code = f"[{strongest['code']}]" if strongest else ""
    return {
        "lead": lead, "confidence": confidence, "fix": lambda ctx: ProposedFix(summary="Gather more evidence before changing anything.", steps=[FixStep(description="Review the strongest evidence items and confirm whether the symptom is still present.")], verification_steps=["Re-run the investigation after new telemetry is available."], rollback_steps=[]),
        "title": {perspective: f"{perspective.capitalize()} cause cannot be confirmed from the evidence" for perspective in confidence},
        "statement": {perspective: f"The strongest signal is: {summary_text} {code}" if perspective == lead else f"Nothing in the evidence points to this lens. {{c_rule}}" for perspective in confidence},
        "reasoning": {perspective: f"The collected evidence does not establish a clear cause. {summary_text} {code}" for perspective in confidence},
        "what_went_wrong": "Keigan collected evidence for the affected services but found no decisive failure pattern. " + summary_text + " " + code,
        "why": "The cause is not established. The strongest signal is listed in the evidence section; treat any explanation as an assumption until confirmed. " + code,
        "executive": "Keigan is investigating but has not yet identified a root cause. Responders should review the strongest evidence and add context.",
        "ja_cause": "現時点では根本原因を特定できていません。収集した証拠を確認中です。", "ja_impact": "影響範囲を確認中です。",
        "open_questions": ["Which user-visible symptoms are still occurring?", "Were any changes made shortly before the problem started?"],
        "actions": [("Find why the reported symptom was possible and add a limit or readiness check that stops it from recurring", "Application SRE team", 21, "prevent"), ("Add alerts for the symptom that was reported so it is detected before users report it", "Application SRE team", 14, "detect")], "lessons": ["Telemetry gaps limit how quickly causes can be found."],
    }


def _script_for(context: MockInvestigationContext) -> dict[str, Any]:
    return SCENARIO_SCRIPTS.get(context.scenario_key or "") or _generic_script(context)


def _fill(text: str, context: MockInvestigationContext) -> str:
    citations = _citations(context)
    filled_text = re.sub(r"\{(c_\w+|p|d|app)\}", lambda match: citations[match.group(1)], text)
    return re.sub(r"[ \t]{2,}", " ", filled_text).replace(" .", ".").replace(" ,", ",").strip()


# ── Factories (registered with the LLM gateway) ────────────────────────────────
def _section_text(prompt_sections: list[PromptSection], title: str) -> str:
    return next((section.content for section in prompt_sections if section.title == title), "")


def build_triage(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = mock_investigation_context.get()
    if context is None:
        return output_schema.model_validate({"suggested_priority": Priority.P3, "priority_rationale": "No context", "incident_category": "errors", "incident_summary": "No context available."})
    scenario = SCENARIO_CATALOG.get(context.scenario_key or "")
    names = [name for name in (context.primary_service_name, context.dependency_service_name) if name]
    has_injection = assess_prompt_injection(_section_text(prompt_sections, "Incident from ServiceNow")).is_suspicious
    return TriageResult(
        suggested_priority=context.priority if context.priority in (Priority.P1, Priority.P2, Priority.P3, Priority.P4) else Priority.P3,  # type: ignore[arg-type]
        priority_rationale=f"Customer-facing impact on a {context.application_name} journey with a recent onset; priority follows the reported impact and urgency.",
        incident_category=scenario.incident_category if scenario else "errors",  # type: ignore[arg-type]
        contains_instruction_like_text=has_injection,
        candidate_service_names=names, incident_summary=f"{context.incident_title}. Users and systems of {context.application_name} are affected.",
        key_symptoms=[symptom for symptom in (context.incident_title.split(":")[-1].strip(),) if symptom], time_of_onset_hint="Shortly before the incident was opened",
    )


def build_query_plan(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    return AdditionalQueryPlan(queries=[])


def build_hypothesis(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = mock_investigation_context.get()
    perspective_text = _section_text(prompt_sections, "Analysis perspective").strip().lower()
    perspective = next((name for name in ("application", "dependencies", "infrastructure") if name in perspective_text), "application")
    assert context is not None
    script = _script_for(context)
    confidence = script["confidence"][perspective]
    fix = script["fix"](context) if perspective == script["lead"] else ProposedFix(
        summary="No change is recommended from this perspective until the leading hypothesis is ruled out.",
        steps=[FixStep(description="Re-check this lens if the leading hypothesis is disproved.")], verification_steps=["Confirm the leading hypothesis fix resolves the symptoms."], rollback_steps=[],
    )
    supporting = [code.strip("[]") for code in re.findall(r"\[E\d+\]", _fill(script["reasoning"][perspective], context))]
    contradicting = [code.strip("[]") for code in re.findall(r"\[E\d+\]", _fill(script["reasoning"][perspective], context)) if confidence < 0.3][:1]
    if confidence < 0.3:
        supporting, contradicting = [], supporting[:2]
    supporting_codes, contradicting_codes = list(dict.fromkeys(supporting)), list(dict.fromkeys(contradicting))
    assessment, assessment_reason = _assess(context, perspective, script, confidence, supporting_codes, contradicting_codes)
    return HypothesisResult(
        hypothesis_title=script["title"][perspective], hypothesis_statement_markdown=_fill(script["statement"][perspective], context), reasoning_markdown=_fill(script["reasoning"][perspective], context),
        confidence_score=confidence, assessment=assessment, assessment_reason_markdown=assessment_reason, supporting_evidence_codes=list(dict.fromkeys(supporting)), contradicting_evidence_codes=list(dict.fromkeys(contradicting)), proposed_fix=fix,
        fix_risk_level=RiskLevel.MEDIUM if perspective == script["lead"] else RiskLevel.LOW,
        matched_runbook_code=_top_runbook_code(prompt_sections) if perspective == script["lead"] else None,
    )


def _is_generic(context: MockInvestigationContext) -> bool:
    """A window the simulator has no scenario for: by construction nothing caused it, so the mock never claims a cause there."""
    return (context.scenario_key or "") not in SCENARIO_SCRIPTS


def _assess(
    context: MockInvestigationContext, perspective: str, script: dict[str, Any], confidence: float, supporting: list[str], contradicting: list[str],
) -> tuple[str, str]:
    """The state and reason the mock proposes, by the same rules the prompt gives a real model (the confidence bands come from the settings)."""
    settings = get_settings()
    cited = lambda codes: " ".join(f"[{code}]" for code in codes)  # noqa: E731
    if _is_generic(context):
        return "inconclusive", "The evidence does not establish a cause in this lens."
    if perspective == script["lead"] and confidence >= settings.investigation_supported_minimum_confidence:
        return "supported", f"Direct evidence that changed against the baseline fits the onset {cited(supporting)}".strip() + "."
    if confidence <= settings.investigation_ruled_out_maximum_confidence and contradicting:
        return "ruled_out", f"A source that was read shows nothing abnormal for this lens {cited(contradicting)}".strip() + "."
    return "inconclusive", "The evidence neither supports nor rules out this lens."


def _top_runbook_code(prompt_sections: list[PromptSection]) -> str | None:
    """Runbook matches arrive ranked best first, so the mock applies [R1] the way the real model is prompted to."""
    runbook_code_match = re.search(r"\[(R\d+)\]", _section_text(prompt_sections, "Known issues (runbooks)"))
    return runbook_code_match.group(1) if runbook_code_match else None


def build_synthesis(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = mock_investigation_context.get()
    assert context is not None
    script = _script_for(context)
    lead_fix = script["fix"](context)
    fix_lines = [f"{index}. {step.description}" + (f"\n```\n{step.command_text}\n```" if step.command_text else "") for index, step in enumerate(lead_fix.steps, start=1)]
    how_to_fix = lead_fix.summary + "\n\n" + "\n".join(fix_lines) + "\n\n**Verify:** " + " ".join(lead_fix.verification_steps) + "\n\n**Rollback:** " + " ".join(lead_fix.rollback_steps or ["Not applicable."])
    confidence = script["confidence"][script["lead"]]
    is_generic = _is_generic(context)
    why_first_sentence = _fill(script["why"], context).split(". ")[0].rstrip(".") + "."
    result = RcaSynthesisResult(
        leading_perspective=None if is_generic else script["lead"], leading_perspective_reason=f"Best supported by direct evidence and timing: {script['title'][script['lead']]}.",
        investigation_outcome=InvestigationOutcome.CAUSE_NOT_VISIBLE if is_generic else InvestigationOutcome.CAUSE_IDENTIFIED,
        outcome_reason_markdown="Nothing Keigan could read changed against the hour before, so the cause is not visible in this data." if is_generic else why_first_sentence,
        overall_confidence_score=confidence,
        executive_summary=_fill(script["executive"], context), what_went_wrong_markdown=_fill(script["what_went_wrong"], context), why_it_happened_markdown=_fill(script["why"], context),
        how_to_fix_markdown=how_to_fix, open_questions=script["open_questions"],
        applied_runbook_codes=[runbook_code] if (runbook_code := _top_runbook_code(prompt_sections)) else [],
    )
    context.synthesis = {**result.model_dump(), "scenario_script_key": context.scenario_key}
    return result


def build_blast_radius_narrative(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = mock_investigation_context.get()
    assert context is not None
    impact_text = _section_text(prompt_sections, "Blast radius (deterministic)")
    directly = re.search(r"Directly impacted: ([^\n]*)", impact_text)
    indirectly = re.search(r"Indirectly impacted: ([^\n]*)", impact_text)
    narrative = f"{context.primary_service_name or 'The affected service'} is the primary point of failure" + (f" ({directly.group(1)})" if directly else "") + "."
    if indirectly and indirectly.group(1).strip() not in ("none", ""):
        narrative += f" Services that depend on it are indirectly affected: {indirectly.group(1)}."
    return BlastRadiusNarrative(narrative_markdown=narrative, user_impact_summary=f"Users of {context.application_name} experience errors or delays in the affected journey.")


JAPANESE_TYPE_LABELS = {"initial_update": "初報", "executive_summary": "経営層向けサマリー", "preliminary_report": "暫定報告", "progress_update": "経過報告", "resolution_update": "復旧のお知らせ"}
ENGLISH_TYPE_LABELS = {"initial_update": "Initial update", "executive_summary": "Executive summary", "preliminary_report": "Preliminary report", "progress_update": "Progress update", "resolution_update": "Resolution update"}


CAUSE_NOT_CONFIRMED_EN = "The cause is not confirmed yet; the team is checking."
CAUSE_NOT_CONFIRMED_JA = "原因はまだ確認できていません。チームが確認を進めています。"


def _cause_is_not_confirmed(prompt_sections: list[PromptSection]) -> bool:
    """The findings the writer receives name the outcome; an unconfirmed cause must not be written up as a cause (spec 27)."""
    outcome_match = re.search(r"Outcome: (\w+)", _section_text(prompt_sections, "Investigation findings"))
    return bool(outcome_match) and outcome_match.group(1) in ("inconclusive", "cause_not_visible")


def build_communications(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = mock_investigation_context.get()
    assert context is not None
    unconfirmed = _cause_is_not_confirmed(prompt_sections)
    script = _script_for(context)
    requested_text = _section_text(prompt_sections, "Requested drafts")
    types = [name for name in ENGLISH_TYPE_LABELS if name in requested_text] or ["initial_update", "executive_summary", "preliminary_report"]
    languages = re.findall(r"\b(en|ja|zh-CN|es|es-MX|nl|fr)\b", requested_text) or ["en", "ja"]
    synthesis = context.synthesis
    confidence_percent = int(round((synthesis.get("overall_confidence_score") or 0.5) * 100))
    services_text = ", ".join(name for name in (context.primary_service_name, context.dependency_service_name) if name) or context.application_name
    drafts: list[CommunicationDraft] = []
    for communication_type in types:
        for language_code in dict.fromkeys(languages):
            if language_code == "ja":
                subject = f"【{context.priority}】{context.application_name}: {JAPANESE_TYPE_LABELS[communication_type]}"
                if communication_type == "resolution_update":
                    body = f"{context.application_name}の障害は復旧しました。\n\n- 原因: {script['ja_cause']}\n- 影響: {script['ja_impact']}\n- 今後: 事後分析（ポストモーテム）を作成し、再発防止策を共有します。"
                elif communication_type == "executive_summary":
                    body = f"{context.application_name}で障害が発生しています。\n\n- 影響: {script['ja_impact']}\n- 想定される原因: {CAUSE_NOT_CONFIRMED_JA if unconfirmed else script['ja_cause']}\n- 対応状況: 復旧作業を進めています。\n- 次回報告: 時刻は改めてお知らせします"
                else:
                    body = (
                        f"関係者各位\n\n{context.application_name}で障害を確認しています。影響を受けているサービス: {services_text}。\n\n- 影響: {script['ja_impact']}\n"
                        f"- 現状: 調査中。{CAUSE_NOT_CONFIRMED_JA if unconfirmed else f"暫定の原因分析では、{script['ja_cause']}（確度 約{confidence_percent}%）"}\n- 次回報告: 時刻は改めてお知らせします\n\n詳細が分かり次第、改めてご連絡します。"
                    )
            else:
                subject = f"[{context.priority}] {context.application_name}: {ENGLISH_TYPE_LABELS[communication_type]}"
                executive = synthesis.get("executive_summary") or _fill(script["executive"], context)
                if communication_type == "resolution_update":
                    body = f"The incident affecting {context.application_name} is resolved.\n\n- **Cause:** {synthesis.get('executive_summary') or executive}\n- **Duration:** {context.duration_minutes or 'n/a'} minutes\n- **Next:** a blameless postmortem will be shared with follow-up actions."
                elif communication_type == "executive_summary":
                    body = f"{executive}\n\n- **Status:** recovery in progress\n- **Next update:** the time of the next update will be confirmed"
                elif communication_type == "preliminary_report":
                    body = f"**Impact:** {services_text} are affected.\n\n{'**Cause:** ' + CAUSE_NOT_CONFIRMED_EN if unconfirmed else f"**Likely cause (confidence {confidence_percent}%):** {synthesis.get('why_it_happened_markdown') or executive}"}\n\n**Mitigation:** see the proposed fix in the investigation.\n\n**Next update:** the time of the next update will be confirmed"
                else:
                    body = f"We are aware of an issue affecting {context.application_name} ({services_text}). {executive}\n\n- **Status:** investigating\n- **Next update:** the time of the next update will be confirmed"
            drafts.append(CommunicationDraft(communication_type=communication_type, language_code=language_code, subject_line=subject, body_markdown=body))  # type: ignore[arg-type]
    return CommunicationDraftSet(drafts=drafts)


def build_postmortem(output_schema: type[BaseModel], prompt_sections: list[PromptSection]) -> BaseModel:
    context = mock_investigation_context.get()
    assert context is not None
    script = _script_for(context)
    synthesis = context.synthesis
    duration = f"{context.duration_minutes} minutes" if context.duration_minutes else "an extended period"
    first_prevent_position = next((position for position, action in enumerate(script["actions"]) if action[3] == "prevent"), 0)
    return PostmortemResult(
        report_title=f"Postmortem: {context.incident_title}", summary=synthesis.get("executive_summary") or _fill(script["executive"], context),
        impact=f"{context.application_name} was degraded for {duration}. {_fill(script['what_went_wrong'], context)}",
        timeline=[PostmortemTimelineEntry(time_text=time_text, description=description) for time_text, description in context.timeline_lines[:12]],
        root_cause=synthesis.get("why_it_happened_markdown") or _fill(script["why"], context),
        contributing_factors=["Existing alerts did not describe the failing component clearly enough to shorten diagnosis.", "The relevant limit or dependency was not covered by a capacity or readiness check."],
        detection="The incident was raised in ServiceNow and picked up by Keigan, which started the investigation immediately and collected evidence within minutes.",
        response=f"Responders followed the investigation's proposed fix. Total time to restore service: {duration}.",
        what_went_well=["Keigan assembled evidence and a ranked root cause hypothesis before responders joined.", "Stakeholders received bilingual updates early."],
        what_could_be_improved=["Detection depended on a user-visible symptom; an earlier signal would shorten time to detect.", "The fix steps were manual and should be rehearsed."],
        # The first prevent item of every scenario is top priority, so the demo has one that the error budget policy (spec 30) accepts.
        action_items=[PostmortemActionItem(description=description, owner_role=owner, due_in_days=days, action_type=kind, priority="top" if position == first_prevent_position else "normal") for position, (description, owner, days, kind) in enumerate(script["actions"])],  # type: ignore[arg-type]
        lessons_learned=script["lessons"],
    )


register_mock_response("incident_triage", build_triage)
register_mock_response("evidence_query_planner", build_query_plan)
for _hypothesis_feature in ("hypothesis_application", "hypothesis_dependencies", "hypothesis_infrastructure"):
    register_mock_response(_hypothesis_feature, build_hypothesis)
register_mock_response("rca_synthesis", build_synthesis)
register_mock_response("blast_radius_narrative", build_blast_radius_narrative)
register_mock_response("incident_communications", build_communications)
register_mock_response("postmortem_report", build_postmortem)

OfflineFactory = Callable[[type[BaseModel], list[PromptSection]], BaseModel]
OFFLINE_FACTORIES: dict[str, OfflineFactory] = {
    "incident_triage": build_triage, "evidence_query_planner": build_query_plan, "hypothesis_application": build_hypothesis, "hypothesis_dependencies": build_hypothesis,
    "hypothesis_infrastructure": build_hypothesis, "rca_synthesis": build_synthesis, "blast_radius_narrative": build_blast_radius_narrative,
    "incident_communications": build_communications, "postmortem_report": build_postmortem,
}
