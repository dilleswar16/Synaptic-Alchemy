"""
F10 — Chaos Experiment Generator.

AI-driven chaos engineering recommendations based on investigation findings.
Analyzes the root cause and blast radius from a completed investigation,
then generates targeted chaos experiments to validate resilience against
similar failures.

Experiment types:
  • pod-kill — Kill specific pods to test restart behavior
  • network-delay — Inject latency between services
  • resource-exhaust — CPU/memory pressure on target service
  • dependency-failure — Simulate downstream dependency unavailability
  • dns-failure — DNS resolution failures for service discovery

Integrates with Azure Chaos Studio and Chaos Mesh for AKS execution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult, RCAOutput
from corvin.core.prompt_registry import get_prompt_registry

_log = logging.getLogger(__name__)


@dataclass
class ChaosExperiment:
    """A single chaos experiment recommendation."""
    id: str
    name: str
    experiment_type: str  # pod-kill | network-delay | resource-exhaust | dependency-failure | dns-failure
    target_service: str
    target_namespace: str
    description: str
    hypothesis: str  # "We expect the system to..."
    steady_state: str  # How to verify normal behavior
    blast_radius: str  # limited | moderate | wide
    duration_seconds: int
    parameters: dict[str, Any] = field(default_factory=dict)
    rollback_steps: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "experiment_type": self.experiment_type,
            "target_service": self.target_service,
            "target_namespace": self.target_namespace,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "steady_state": self.steady_state,
            "blast_radius": self.blast_radius,
            "duration_seconds": self.duration_seconds,
            "parameters": self.parameters,
            "rollback_steps": self.rollback_steps,
            "prerequisites": self.prerequisites,
            "generated_at": self.generated_at,
        }


@dataclass
class ChaosExperimentPlan:
    """Complete chaos experiment plan for an investigation."""
    request_id: str
    service_name: str
    experiments: list[ChaosExperiment] = field(default_factory=list)
    rationale: str = ""
    risk_assessment: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "service_name": self.service_name,
            "experiments": [e.to_dict() for e in self.experiments],
            "rationale": self.rationale,
            "risk_assessment": self.risk_assessment,
            "generated_at": self.generated_at,
            "experiment_count": len(self.experiments),
        }


class ChaosExperimentGenerator:
    """Generates chaos experiment plans from investigation results."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())

    def _get_model(self) -> str:
        model = self._config.get("fallback_model") or self._config.get("model")
        if not model:
            raise ValueError("models/llm.yaml must define 'model' or 'fallback_model'")
        return model

    def generate(self, result: InvestigationResult) -> ChaosExperimentPlan:
        """
        Generate chaos experiments based on a completed investigation.

        Uses the RCA root cause + contributing factors to recommend
        experiments that would validate the system's resilience to
        similar failure modes.
        """
        prompt = self._build_prompt(result)

        try:
            resp = litellm.completion(
                model=self._get_model(),
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
            parsed = json.loads(raw)
            return self._parse_response(parsed, result)
        except Exception as exc:
            _log.warning("Chaos experiment generation failed, using deterministic fallback: %s", exc)
            return self._deterministic_fallback(result)

    def _system_prompt(self) -> str:
        return get_prompt_registry().get("chaos_generation")

    def _build_prompt(self, result: InvestigationResult) -> str:
        rca = result.rca
        return f"""Investigation details:
- Service: {result.request.service_name}
- Environment: {result.request.environment}
- Alert: {result.request.alert_summary}
- Root Cause: {rca.root_cause}
- Confidence: {rca.confidence.value}
- Contributing Factors: {json.dumps(rca.contributing_factors, default=str)}
- Fix Actions: {json.dumps([a if isinstance(a, str) else str(a) for a in (result.fix_strategy.actions or [])[:3]], default=str)}

Generate chaos experiments that would validate resilience against this failure mode."""

    def _parse_response(self, parsed: dict[str, Any], result: InvestigationResult) -> ChaosExperimentPlan:
        experiments = []
        for i, exp_data in enumerate(parsed.get("experiments", [])[:5]):
            experiments.append(ChaosExperiment(
                id=f"chaos-{result.request_id[:8]}-{i+1}",
                name=exp_data.get("name", f"Experiment {i+1}"),
                experiment_type=exp_data.get("experiment_type", "pod-kill"),
                target_service=result.request.service_name,
                target_namespace=result.request.environment or "default",
                description=exp_data.get("description", ""),
                hypothesis=exp_data.get("hypothesis", ""),
                steady_state=exp_data.get("steady_state", ""),
                blast_radius=exp_data.get("blast_radius", "limited"),
                duration_seconds=exp_data.get("duration_seconds", 60),
                parameters=exp_data.get("parameters", {}),
                rollback_steps=exp_data.get("rollback_steps", []),
                prerequisites=exp_data.get("prerequisites", []),
            ))

        return ChaosExperimentPlan(
            request_id=result.request_id,
            service_name=result.request.service_name,
            experiments=experiments,
            rationale=parsed.get("rationale", ""),
            risk_assessment=parsed.get("risk_assessment", ""),
        )

    def _deterministic_fallback(self, result: InvestigationResult) -> ChaosExperimentPlan:
        """Fallback: generate standard chaos experiments based on failure type heuristics."""
        service = result.request.service_name
        namespace = result.request.environment or "default"
        root_cause = (result.rca.root_cause or "").lower()

        experiments = []

        # Always recommend pod-kill for any service
        experiments.append(ChaosExperiment(
            id=f"chaos-{result.request_id[:8]}-1",
            name=f"Pod termination resilience — {service}",
            experiment_type="pod-kill",
            target_service=service,
            target_namespace=namespace,
            description=f"Terminate random pod of {service} to validate restart and request draining",
            hypothesis=f"We expect {service} to recover within 30s with zero dropped requests due to readiness probes",
            steady_state=f"Health endpoint returns 200, p99 latency < 500ms",
            blast_radius="limited",
            duration_seconds=60,
            parameters={"kill_count": 1, "interval_seconds": 30},
            rollback_steps=["kubectl rollout restart", "Verify pod count matches desired replicas"],
            prerequisites=["Minimum 2 replicas running", "PodDisruptionBudget configured"],
        ))

        # Network delay if root cause mentions latency/timeout
        if any(kw in root_cause for kw in ("timeout", "latency", "slow", "connection", "network")):
            experiments.append(ChaosExperiment(
                id=f"chaos-{result.request_id[:8]}-2",
                name=f"Network latency injection — {service}",
                experiment_type="network-delay",
                target_service=service,
                target_namespace=namespace,
                description=f"Inject 500ms network delay to {service} to test timeout handling",
                hypothesis=f"We expect circuit breakers to activate and fallback responses within 2s",
                steady_state="Response times < 200ms, error rate < 0.1%",
                blast_radius="moderate",
                duration_seconds=120,
                parameters={"delay_ms": 500, "jitter_ms": 100, "direction": "ingress"},
                rollback_steps=["Remove network policy", "Verify latency returns to baseline"],
                prerequisites=["Circuit breaker configured", "Monitoring alerts active"],
            ))

        # Resource exhaustion if root cause mentions OOM/CPU/memory
        if any(kw in root_cause for kw in ("oom", "memory", "cpu", "resource", "throttl")):
            experiments.append(ChaosExperiment(
                id=f"chaos-{result.request_id[:8]}-3",
                name=f"Resource pressure test — {service}",
                experiment_type="resource-exhaust",
                target_service=service,
                target_namespace=namespace,
                description=f"Apply CPU/memory stress to {service} pods to validate autoscaling and limits",
                hypothesis=f"We expect HPA to scale pods when resource usage exceeds 80% threshold",
                steady_state="CPU utilization < 50%, memory < 70%",
                blast_radius="moderate",
                duration_seconds=180,
                parameters={"cpu_load_pct": 85, "memory_mib": 512},
                rollback_steps=["Remove stress container", "Verify HPA scales down"],
                prerequisites=["HPA configured", "Resource limits set on pods"],
            ))

        # Dependency failure if root cause mentions downstream/dependency
        if any(kw in root_cause for kw in ("dependency", "downstream", "database", "redis", "queue")):
            experiments.append(ChaosExperiment(
                id=f"chaos-{result.request_id[:8]}-4",
                name=f"Dependency failure simulation — {service}",
                experiment_type="dependency-failure",
                target_service=service,
                target_namespace=namespace,
                description=f"Block traffic to downstream dependency to test graceful degradation",
                hypothesis=f"We expect {service} to return degraded responses rather than 500 errors",
                steady_state="All health checks passing, dependency reachable",
                blast_radius="wide",
                duration_seconds=120,
                parameters={"target_port": 5432, "block_type": "drop"},
                rollback_steps=["Remove network policy", "Verify connectivity restored"],
                prerequisites=["Fallback/circuit-breaker logic implemented", "Canary traffic only"],
            ))

        return ChaosExperimentPlan(
            request_id=result.request_id,
            service_name=service,
            experiments=experiments,
            rationale=f"Experiments target the root cause: {result.rca.root_cause[:100]}",
            risk_assessment="Limited blast radius — run in non-prod first, then canary in prod with approval gates.",
        )
