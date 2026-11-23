"""keigan/services/incident_memory_scoring.py: which past incidents are suggested, in what order, and why (spec 34, 4.4; AC-6, AC-7, AC-9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.services.incident_memory_scoring import (
    STALE_OLDER_THAN_THRESHOLD, STALE_SERVICE_REMOVED, CurrentIncident, KeyRef, MemoryCandidate, catalogue, score_matches, similarity_config,
)

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CONFIG = similarity_config(minimum_score=0.35, stale_after_days=180, maximum_shown=5)
ERROR = KeyRef("error_signature", "e" * 64, "connection pool exhausted")
CLUSTER = KeyRef("shared_resource", "c" * 64, "aks-prod-1")
SERVICE = KeyRef("service", "s" * 64, "claims-api")
CATEGORY = KeyRef("incident_category", "k" * 64, "database")


def current(*keys: KeyRef, terms: tuple[str, ...] = (), application: str = "app-a") -> CurrentIncident:
    return CurrentIncident(application, keys, terms)


def past(entry_id: str, *keys: KeyRef, application: str = "app-a", verdict: str | None = "correct", days_ago: int = 30, terms: frozenset[str] = frozenset(), service_exists: bool = True) -> MemoryCandidate:
    return MemoryCandidate(entry_id, application, verdict, NOW - timedelta(days=days_ago), keys, terms, service_exists)


def test_the_catalogue_names_a_weight_for_every_kind_of_key_and_every_verdict() -> None:
    from keigan.entities.status_values import IncidentMemoryKeyKind

    document = catalogue()
    assert set(document["key_weights"]) == {kind.value for kind in IncidentMemoryKeyKind}
    assert set(document["verdict_multipliers"]) == {"correct", "partially_correct", "none"} and document["rejected_verdict"] == "incorrect"
    assert set(document["cross_application_required_key_kinds"]) <= set(document["key_weights"])


def test_sharing_a_hard_fact_scores_its_weight_and_the_match_says_which() -> None:
    [match] = score_matches(current(ERROR), [past("m1", ERROR)], CONFIG, NOW)
    assert match.score == pytest.approx(0.35) and [key.kind for key in match.reasons] == ["error_signature"] and match.reasons[0].display_text == "connection pool exhausted"


def test_each_kind_counts_once_however_many_keys_of_it_are_shared() -> None:
    second_error = KeyRef("error_signature", "f" * 64, "another signature")
    [match] = score_matches(current(ERROR, second_error), [past("m1", ERROR, second_error)], CONFIG, NOW)
    assert match.score == pytest.approx(0.35) and len(match.reasons) == 2


def test_weights_add_up_and_are_capped_at_one() -> None:
    [match] = score_matches(current(ERROR, CLUSTER, SERVICE, CATEGORY), [past("m1", ERROR, CLUSTER, SERVICE, CATEGORY)], CONFIG, NOW)
    assert match.score == pytest.approx(0.35 + 0.15 + 0.15 + 0.05) and [key.kind for key in match.reasons] == ["error_signature", "shared_resource", "service", "incident_category"]


def test_wording_adds_to_the_score_in_proportion_to_the_words_found() -> None:
    terms = ("timeout", "claims", "batch")
    [all_words] = score_matches(current(ERROR, terms=terms), [past("m1", ERROR, terms=frozenset(terms))], CONFIG, NOW)
    [no_words] = score_matches(current(ERROR, terms=terms), [past("m1", ERROR)], CONFIG, NOW)
    assert all_words.score == pytest.approx(0.35 + 0.30) and no_words.score == pytest.approx(0.35)


def test_a_rare_word_counts_for_more_than_one_every_past_incident_has() -> None:
    terms = ("rare", "common")
    candidates = [past("m1", ERROR, terms=frozenset({"common"})), past("m2", ERROR, terms=frozenset({"rare"})), past("m3", ERROR, terms=frozenset({"common"}))]
    scores = {match.entry_id: match.score for match in score_matches(current(ERROR, terms=terms), candidates, CONFIG, NOW)}
    assert scores["m2"] > scores["m1"] == scores["m3"]


def test_a_past_incident_of_another_application_needs_a_hard_fact_not_just_words() -> None:
    words_only = past("other-words", application="app-b", terms=frozenset({"timeout", "claims"}), days_ago=5)
    weak_key = past("other-service", SERVICE, application="app-b")
    hard = past("other-cluster", CLUSTER, application="app-b")
    matches = score_matches(current(CLUSTER, SERVICE, terms=("timeout", "claims")), [words_only, weak_key, hard], similarity_config(minimum_score=0.1, stale_after_days=180, maximum_shown=5), NOW)
    assert [match.entry_id for match in matches] == ["other-cluster"]


def test_wording_alone_is_enough_inside_one_application_when_it_is_alike_enough() -> None:
    terms = ("timeout", "claims", "batch")
    matches = score_matches(current(terms=terms), [past("same-app", terms=frozenset(terms))], similarity_config(minimum_score=0.2, stale_after_days=180, maximum_shown=5), NOW)
    assert [match.entry_id for match in matches] == ["same-app"]


def test_an_admin_confirmed_past_incident_ranks_above_a_partly_right_one_and_an_unreviewed_one() -> None:
    candidates = [past("none", ERROR, CLUSTER, verdict=None), past("right", ERROR, CLUSTER, verdict="correct"), past("partly", ERROR, CLUSTER, verdict="partially_correct")]
    config = similarity_config(minimum_score=0.1, stale_after_days=180, maximum_shown=5)
    assert [match.entry_id for match in score_matches(current(ERROR, CLUSTER), candidates, config, NOW)] == ["right", "partly", "none"]


def test_a_past_incident_marked_incorrect_is_listed_apart_after_the_others_and_judged_on_its_raw_score() -> None:
    """Not mixed in and not multiplied down: it is shown, labelled, when it matches as well as anything else would have to."""
    candidates = [past("wrong", ERROR, CLUSTER, SERVICE, verdict="incorrect"), past("none", ERROR, CLUSTER, SERVICE, verdict=None)]
    matches = score_matches(current(ERROR, CLUSTER, SERVICE), candidates, CONFIG, NOW)
    assert [(match.entry_id, match.is_rejected) for match in matches] == [("none", False), ("wrong", True)]
    assert matches[1].score == pytest.approx(0.35 + 0.15 + 0.15)  # no verdict multiplier


def test_a_marked_incorrect_incident_still_needs_the_minimum_score_and_the_cap_and_zero_hides_them() -> None:
    weak = past("weak", CATEGORY, verdict="incorrect")
    strong = [past(f"wrong{number}", ERROR, verdict="incorrect", days_ago=number) for number in range(1, 5)]
    assert score_matches(current(CATEGORY), [weak], CONFIG, NOW) == []
    capped = score_matches(current(ERROR), strong, similarity_config(minimum_score=0.35, stale_after_days=180, maximum_shown=5, maximum_rejected_shown=2), NOW)
    assert [match.entry_id for match in capped] == ["wrong1", "wrong2"]
    assert score_matches(current(ERROR), strong, similarity_config(minimum_score=0.35, stale_after_days=180, maximum_shown=5, maximum_rejected_shown=0), NOW) == []


def test_an_incident_with_no_facts_is_compared_on_its_words_alone_and_they_carry_the_whole_score() -> None:
    terms = ("timeout", "claims", "batch")
    [match] = score_matches(current(terms=terms), [past("m1", terms=frozenset(terms), verdict="correct")], CONFIG, NOW)
    assert match.score == pytest.approx(1.0)  # not the 0.30 they are worth next to shared facts
    half = score_matches(current(terms=terms), [past("m2", terms=frozenset(terms[:1]), verdict="correct")], CONFIG, NOW)
    assert half == []  # a third of the words is below the minimum score


def test_nothing_below_the_minimum_score_is_shown() -> None:
    assert score_matches(current(CATEGORY), [past("m1", CATEGORY)], CONFIG, NOW) == []


def test_only_the_best_few_are_shown_newest_first_on_a_tie() -> None:
    candidates = [past(f"m{number}", ERROR, days_ago=number) for number in range(1, 8)]
    matches = score_matches(current(ERROR), candidates, similarity_config(minimum_score=0.1, stale_after_days=180, maximum_shown=3), NOW)
    assert [match.entry_id for match in matches] == ["m1", "m2", "m3"]


def test_an_old_past_incident_is_marked_out_of_date_and_so_is_one_whose_services_are_gone() -> None:
    old = past("old", ERROR, days_ago=181)
    recent = past("recent", ERROR, days_ago=180)
    gone = past("gone", ERROR, days_ago=10, service_exists=False)
    by_id = {match.entry_id: match for match in score_matches(current(ERROR), [old, recent, gone], similarity_config(minimum_score=0.1, stale_after_days=180, maximum_shown=5), NOW)}
    assert by_id["old"].is_stale and list(by_id["old"].stale_reasons) == [STALE_OLDER_THAN_THRESHOLD] and by_id["old"].age_days == 181
    assert not by_id["recent"].is_stale and by_id["recent"].stale_reasons == []
    assert list(by_id["gone"].stale_reasons) == [STALE_SERVICE_REMOVED]


def test_no_candidates_no_matches() -> None:
    assert score_matches(current(ERROR), [], CONFIG, NOW) == []
