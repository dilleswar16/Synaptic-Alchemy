"""
Blast Radius Estimator — V3.5

Translates raw evidence into a human-readable impact estimate:
  - How many users are likely affected
  - Which downstream services depend on the failing service
  - Estimated revenue risk per minute

No LLM call — pure calculation from EvidenceBundle + config.
Fast enough to run synchronously after every investigation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Output contract ────────────────────────────────────────────────────────────

class BlastRadiusEstimate(BaseModel):
    """Estimated impact for a single investigation."""

    service_name: str
    environment: str
    # Services directly or indirectly affected (from APIM + AKS evidence)
    affected_services: list[str]
    # Number of downstream APIM API IDs observed routing through this backend
    downstream_api_count: int
    # Estimated live users affected (replica_count × users_per_replica)
    estimated_users: int
    # Revenue risk per minute in configured currency
    revenue_risk_per_min: float
    currency: str
    # Current replica count from AKS evidence (0 = unknown)
    replica_count: int
    # Brief explanation of how the estimate was made
    rationale: str


# ── Estimator ─────────────────────────────────────────────────────────────────

_KNOWN_APIM_IDS: list[str] = ["fundapis", "partnerapis", "system"]


def estimate_blast_radius(
    service_name: str,
    environment: str,
    evidence: Any,          # EvidenceBundle — avoid circular import via Any
    policy: dict[str, Any], # config/policies/investigation.yaml parsed dict
) -> BlastRadiusEstimate:
    """
    Compute a BlastRadiusEstimate from collected evidence.

    Parameters
    ----------
    service_name:  the service under investigation
    environment:   deployment environment (dev/qa/prod)
    evidence:      EvidenceBundle (elastic, apim, aks fields)
    policy:        parsed investigation.yaml config dict
    """
    # ── 1. Replica count from AKS context ─────────────────────────────────────
    aks = evidence.aks_context or {}
    pods: list[dict] = aks.get("pods", [])
    replica_count = len([p for p in pods if isinstance(p, dict)])

    # ── 2. Downstream services from APIM logs ─────────────────────────────────
    apim_logs: list[dict] = evidence.log_analytics_apim or []
    seen_api_ids: set[str] = set()
    for row in apim_logs:
        api_id = row.get("ApiId") or row.get("apiId") or row.get("api_id", "")
        if api_id and api_id != service_name:
            seen_api_ids.add(str(api_id))

    downstream_apis = sorted(seen_api_ids)
    downstream_api_count = len(downstream_apis)

    # Affected services = primary service + any distinct APIM consumers
    affected_services = [service_name] + [s for s in downstream_apis if s not in (service_name,)]

    # ── 3. User estimate ────────────────────────────────────────────────────────
    users_per_replica: int = int(policy.get("blast_radius_users_per_replica", 400))
    if replica_count > 0:
        estimated_users = replica_count * users_per_replica
    else:
        # No AKS data — use downstream API count as a proxy
        estimated_users = max(downstream_api_count, 1) * users_per_replica

    # ── 4. Revenue risk ─────────────────────────────────────────────────────────
    revenue_per_user_per_min: float = float(
        policy.get("blast_radius_revenue_per_user_per_min", 0.003)
    )
    currency: str = str(policy.get("blast_radius_currency", "GBP"))
    revenue_risk_per_min = round(estimated_users * revenue_per_user_per_min, 2)

    # ── 5. Rationale ────────────────────────────────────────────────────────────
    if replica_count > 0:
        rationale = (
            f"{replica_count} pod{'s' if replica_count != 1 else ''} observed in AKS × "
            f"{users_per_replica} users/pod"
        )
    else:
        rationale = (
            f"No AKS pod data — estimated from {max(downstream_api_count, 1)} "
            f"APIM consumer{'s' if downstream_api_count != 1 else ''} × {users_per_replica}"
        )

    return BlastRadiusEstimate(
        service_name=service_name,
        environment=environment,
        affected_services=affected_services,
        downstream_api_count=downstream_api_count,
        estimated_users=estimated_users,
        revenue_risk_per_min=revenue_risk_per_min,
        currency=currency,
        replica_count=replica_count,
        rationale=rationale,
    )
