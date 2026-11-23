"""How alike two incidents are, and which past incidents are worth showing (spec 34, 4.4). Pure: no database, no network.

A past incident scores by the facts it shares with the current one (the same error signature, the same shared cluster, the same service ...) plus the share of the current incident's words found in
it, times how far an admin trusted that past analysis. Every match carries its reasons, so a person can see why it was suggested and judge it. A past incident of another application is shown only
when it shares a hard fact; matching words alone are never enough across applications.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

import yaml

from keigan.config.settings import RESOURCES_DIRECTORY

NO_VERDICT = "none"
STALE_OLDER_THAN_THRESHOLD = "older_than_threshold"
STALE_SERVICE_REMOVED = "service_removed"


@dataclass(frozen=True)
class KeyRef:
    kind: str
    value_hash: str
    display_text: str


@dataclass(frozen=True)
class CurrentIncident:
    application_id: str
    keys: Sequence[KeyRef]
    terms: Sequence[str]


@dataclass(frozen=True)
class MemoryCandidate:
    entry_id: str
    application_id: str
    verdict: str | None
    occurred_at: datetime
    keys: Sequence[KeyRef]
    terms: frozenset[str]
    has_existing_service: bool  # false when every service the entry was about has been deleted


@dataclass(frozen=True)
class SimilarityConfig:
    key_weights: Mapping[str, float]
    keyword_weight: float
    verdict_multipliers: Mapping[str, float]
    cross_application_required_key_kinds: frozenset[str]
    minimum_score: float
    stale_after_days: int
    maximum_shown: int
    rejected_verdict: str  # a past investigation with this verdict is listed apart and labelled, not mixed in
    maximum_rejected_shown: int


@dataclass(frozen=True)
class ScoredMatch:
    entry_id: str
    application_id: str
    score: float
    reasons: Sequence[KeyRef]  # the keys both incidents have, strongest kind first
    age_days: int
    is_stale: bool
    stale_reasons: Sequence[str]
    is_rejected: bool = False  # an admin marked that past analysis incorrect: shown last and labelled


@lru_cache
def catalogue() -> dict[str, Any]:
    return yaml.safe_load((RESOURCES_DIRECTORY / "catalogs" / "incident_similarity.yaml").read_text(encoding="utf-8"))


def similarity_config(*, minimum_score: float, stale_after_days: int, maximum_shown: int, maximum_rejected_shown: int = 2) -> SimilarityConfig:
    document = catalogue()
    return SimilarityConfig(
        key_weights=dict(document["key_weights"]), keyword_weight=float(document["keyword_weight"]), verdict_multipliers=dict(document["verdict_multipliers"]),
        cross_application_required_key_kinds=frozenset(document["cross_application_required_key_kinds"]), minimum_score=minimum_score, stale_after_days=stale_after_days, maximum_shown=maximum_shown,
        rejected_verdict=document["rejected_verdict"], maximum_rejected_shown=maximum_rejected_shown,
    )


def _shared_keys(current: CurrentIncident, candidate: MemoryCandidate) -> list[KeyRef]:
    candidate_hashes = {(key.kind, key.value_hash) for key in candidate.keys}
    seen: set[tuple[str, str]] = set()
    shared: list[KeyRef] = []
    for key in current.keys:
        identity = (key.kind, key.value_hash)
        if identity in candidate_hashes and identity not in seen:
            seen.add(identity)
            shared.append(key)
    return shared


def _keyword_share(query_terms: Sequence[str], candidate: MemoryCandidate, document_frequency: Mapping[str, int], candidate_count: int) -> float:
    """Σ idf over the query's terms the entry has ÷ Σ idf over the query's terms. Between 0 and 1, and not inflated when there is only one candidate (unlike a raw BM25 score)."""
    unique_terms = set(query_terms)
    if not unique_terms:
        return 0.0
    def idf(term: str) -> float:
        return math.log((candidate_count + 1) / (document_frequency.get(term, 0) + 1)) + 1.0
    total = sum(idf(term) for term in unique_terms)
    return sum(idf(term) for term in unique_terms if term in candidate.terms) / total


def score_matches(current: CurrentIncident, candidates: Sequence[MemoryCandidate], config: SimilarityConfig, today: datetime) -> list[ScoredMatch]:
    document_frequency: dict[str, int] = {}
    for candidate in candidates:
        for term in set(current.terms) & candidate.terms:
            document_frequency[term] = document_frequency.get(term, 0) + 1
    matches: list[ScoredMatch] = []
    for candidate in candidates:
        shared = _shared_keys(current, candidate)
        shared_kinds = {key.kind for key in shared}
        is_same_application = candidate.application_id == current.application_id
        if not is_same_application and not shared_kinds & config.cross_application_required_key_kinds:
            continue  # wording or a weak key is not enough to compare two applications
        structured = min(1.0, sum(config.key_weights.get(kind, 0.0) for kind in shared_kinds))
        keyword = _keyword_share(current.terms, candidate, document_frequency, len(candidates))
        raw = min(1.0, structured + config.keyword_weight * keyword)
        is_rejected = candidate.verdict == config.rejected_verdict
        score = raw if is_rejected else raw * config.verdict_multipliers.get(candidate.verdict or NO_VERDICT, config.verdict_multipliers[NO_VERDICT])
        if score < config.minimum_score:
            continue
        age_days = max(0, (today - candidate.occurred_at).days)
        stale_reasons = [reason for reason, applies in ((STALE_OLDER_THAN_THRESHOLD, age_days > config.stale_after_days), (STALE_SERVICE_REMOVED, not candidate.has_existing_service)) if applies]
        reasons = sorted(shared, key=lambda key: -config.key_weights.get(key.kind, 0.0))
        matches.append(ScoredMatch(candidate.entry_id, candidate.application_id, round(score, 6), reasons, age_days, bool(stale_reasons), stale_reasons, is_rejected))
    by_entry = {candidate.entry_id: candidate for candidate in candidates}
    matches.sort(key=lambda match: (-match.score, -by_entry[match.entry_id].occurred_at.timestamp()))
    kept = [match for match in matches if not match.is_rejected][:config.maximum_shown]
    return kept + [match for match in matches if match.is_rejected][:config.maximum_rejected_shown]  # the ones an admin marked incorrect come last, labelled
