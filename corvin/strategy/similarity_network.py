"""
Similarity Network Engine — Feature 11.

Builds a lightweight investigation similarity graph without requiring pgvector.
Uses three signals to compute pairwise similarity:

  1. Service / environment match  (weight: 0.40)
  2. RCA text Jaccard similarity   (weight: 0.40)
  3. Time proximity                (weight: 0.20)

The graph is returned as {nodes, edges} suitable for @xyflow/react in the
frontend. Only edges above ``min_similarity`` are included so the graph
stays readable.

pgvector-backed semantic similarity (Feature 7) will supersede the Jaccard
component when that feature is enabled; until then this engine works entirely
from data already in the SQLite/Postgres investigation store.

No customer-specific strings appear in this module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from corvin.core.config_loader import get_env, load_config

_log = logging.getLogger(__name__)

# ── Similarity weights ────────────────────────────────────────────────────────

_W_SERVICE = 0.40
_W_TEXT = 0.40
_W_TIME = 0.20

# Time window in days beyond which time proximity contributes 0.
_TIME_DECAY_DAYS = 30


# ── Data shapes ───────────────────────────────────────────────────────────────


@dataclass
class NetworkNode:
    id: str
    service_name: str
    environment: str
    priority: str
    rca_summary: str
    created_at: str   # ISO string
    node_size: int    # 1–5 derived from priority (P1=5, P2=4, P3=3, else=2)
    label: str        # short display label

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service_name": self.service_name,
            "environment": self.environment,
            "priority": self.priority,
            "rca_summary": self.rca_summary,
            "created_at": self.created_at,
            "node_size": self.node_size,
            "label": self.label,
        }


@dataclass
class NetworkEdge:
    source_id: str
    target_id: str
    similarity_score: float  # 0.0–1.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "similarity_score": round(self.similarity_score, 3),
            "reasons": self.reasons,
        }


# ── Engine ────────────────────────────────────────────────────────────────────


class SimilarityNetworkEngine:
    """Builds an investigation similarity graph from the stored investigation set.

    Usage::

        engine = SimilarityNetworkEngine()
        graph = engine.build(focus_id="abc-123", limit=50, min_similarity=0.25)
        # graph = {"nodes": [...], "edges": [...], "focus_id": "abc-123", ...}
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config if config is not None else load_config("policies/investigation", get_env())
        sim_cfg = cfg.get("similarity_network", {})
        self._default_limit: int = int(sim_cfg.get("default_limit", 50))
        self._max_limit: int = int(sim_cfg.get("max_limit", 200))
        self._min_similarity: float = float(sim_cfg.get("min_similarity", 0.20))

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        investigations: list[dict[str, Any]],
        focus_id: str | None = None,
        min_similarity: float | None = None,
    ) -> dict[str, Any]:
        """Build the similarity graph from a pre-loaded investigation list.

        Args:
            investigations: list of dicts with keys
                {id, service_name, environment, priority, rca_summary, created_at}
            focus_id: when set, only edges touching this node are returned
            min_similarity: override the config default

        Returns a dict with keys: nodes, edges, focus_id, stats.
        """
        threshold = min_similarity if min_similarity is not None else self._min_similarity

        if not investigations:
            return {
                "nodes": [],
                "edges": [],
                "focus_id": focus_id,
                "stats": {"node_count": 0, "edge_count": 0},
            }

        nodes = [self._make_node(inv) for inv in investigations]
        edges = self._compute_edges(investigations, focus_id, threshold)

        return {
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
            "focus_id": focus_id,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "threshold": threshold,
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _make_node(self, inv: dict[str, Any]) -> NetworkNode:
        priority = str(inv.get("priority", "P3")).upper()
        node_size = {"P1": 5, "P2": 4, "P3": 3}.get(priority, 2)
        service = str(inv.get("service_name", "unknown"))
        created_at = inv.get("created_at", "")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        short_id = str(inv.get("id", ""))[:8]
        return NetworkNode(
            id=str(inv.get("id", "")),
            service_name=service,
            environment=str(inv.get("environment", "")),
            priority=priority,
            rca_summary=str(inv.get("rca_summary", ""))[:200],
            created_at=created_at,
            node_size=node_size,
            label=f"{service[:20]} ({short_id})",
        )

    def _compute_edges(
        self,
        investigations: list[dict[str, Any]],
        focus_id: str | None,
        threshold: float,
    ) -> list[NetworkEdge]:
        edges: list[NetworkEdge] = []
        n = len(investigations)
        for i in range(n):
            for j in range(i + 1, n):
                a = investigations[i]
                b = investigations[j]
                edge = self._score_pair(a, b)
                if edge.similarity_score < threshold:
                    continue
                if focus_id and focus_id not in (edge.source_id, edge.target_id):
                    continue
                edges.append(edge)
        # Sort descending by score so the frontend can trim if needed.
        edges.sort(key=lambda e: e.similarity_score, reverse=True)
        return edges

    def _score_pair(self, a: dict[str, Any], b: dict[str, Any]) -> NetworkEdge:
        reasons: list[str] = []

        # ── Signal 1: service + environment overlap ──────────────────────────
        svc_score = 0.0
        a_svc = str(a.get("service_name", "")).lower().strip()
        b_svc = str(b.get("service_name", "")).lower().strip()
        a_env = str(a.get("environment", "")).lower().strip()
        b_env = str(b.get("environment", "")).lower().strip()

        if a_svc and a_svc == b_svc:
            svc_score += 0.7
            reasons.append(f"Same service: {a_svc}")
        elif a_svc and b_svc and (a_svc in b_svc or b_svc in a_svc):
            svc_score += 0.4
            reasons.append("Related services")
        if a_env and a_env == b_env:
            svc_score += 0.3
            reasons.append(f"Same environment: {a_env}")
        svc_score = min(1.0, svc_score)

        # ── Signal 2: RCA text Jaccard similarity ────────────────────────────
        text_score = self._jaccard(
            str(a.get("rca_summary", "")),
            str(b.get("rca_summary", "")),
        )
        if text_score >= 0.15:
            reasons.append(f"Similar RCA ({int(text_score * 100)}% overlap)")

        # ── Signal 3: time proximity ──────────────────────────────────────────
        time_score = self._time_proximity(
            a.get("created_at"),
            b.get("created_at"),
        )
        if time_score >= 0.5:
            reasons.append("Close in time")

        score = (_W_SERVICE * svc_score) + (_W_TEXT * text_score) + (_W_TIME * time_score)
        return NetworkEdge(
            source_id=str(a.get("id", "")),
            target_id=str(b.get("id", "")),
            similarity_score=round(min(1.0, score), 4),
            reasons=reasons,
        )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Normalise and tokenize text into a word-token set."""
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        tokens = {t for t in text.split() if len(t) > 2}
        # Remove generic stop-words that add noise without semantic value.
        _STOP = {"the", "and", "for", "this", "that", "was", "has", "with",
                 "are", "due", "from", "not", "have", "been", "its"}
        return tokens - _STOP

    def _jaccard(self, a: str, b: str) -> float:
        if not a.strip() or not b.strip():
            return 0.0
        ta = self._tokenize(a)
        tb = self._tokenize(b)
        if not ta or not tb:
            return 0.0
        intersection = len(ta & tb)
        union = len(ta | tb)
        return intersection / union if union else 0.0

    @staticmethod
    def _time_proximity(dt_a: Any, dt_b: Any) -> float:
        """Return 1.0 for same day, 0.0 for >= _TIME_DECAY_DAYS apart."""
        def _parse(v: Any) -> datetime | None:
            if isinstance(v, datetime):
                return v
            if isinstance(v, str):
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        a = _parse(dt_a)
        b = _parse(dt_b)
        if a is None or b is None:
            return 0.0
        diff_days = abs((a - b).total_seconds()) / 86400
        if diff_days >= _TIME_DECAY_DAYS:
            return 0.0
        return 1.0 - (diff_days / _TIME_DECAY_DAYS)
