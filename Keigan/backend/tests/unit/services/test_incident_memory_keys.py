"""keigan/services/incident_memory_keys.py: the facts of an investigation as comparable keys (spec 34, 4.3)."""

from __future__ import annotations

from keigan.services.incident_memory_keys import MAXIMUM_DISPLAY_CHARACTERS, MemoryFacts, build_match_keys, shared_resource_value
from keigan.utils.error_signature import hash_key_value

CLUSTER = "/subscriptions/0000/resourceGroups/rg-prod/providers/Microsoft.ContainerService/managedClusters/aks-prod-1"


def facts(**overrides) -> MemoryFacts:
    values = {"services": {"svc-1": "claims-api"}, "resource_identifiers": [CLUSTER], "error_templates": ["Timeout expired after 30000 ms"], "incident_category": "Database"}
    return MemoryFacts(**{**values, **overrides})


def by_kind(keys) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for key in keys:
        grouped.setdefault(key.kind, []).append(key)
    return grouped


def test_a_service_a_cluster_an_error_and_a_category_each_become_a_key() -> None:
    grouped = by_kind(build_match_keys(facts()))
    assert set(grouped) == {"service", "shared_resource", "error_signature", "incident_category"}
    assert grouped["service"][0].display_text == "claims-api" and grouped["service"][0].value_hash == hash_key_value("svc-1")
    assert grouped["shared_resource"][0].display_text == "aks-prod-1"
    assert grouped["error_signature"][0].display_text == "timeout expired after # ms"
    assert grouped["incident_category"][0].display_text == "database"


def test_the_same_facts_give_the_same_keys_so_a_past_entry_and_the_current_investigation_agree() -> None:
    assert build_match_keys(facts()) == build_match_keys(facts())


def test_two_occurrences_of_one_error_with_different_numbers_share_a_key() -> None:
    first = by_kind(build_match_keys(facts(error_templates=["Timeout expired after 30000 ms"])))["error_signature"]
    second = by_kind(build_match_keys(facts(error_templates=["timeout EXPIRED after 15 ms"])))["error_signature"]
    assert first == second


def test_a_child_resource_is_the_same_shared_resource_as_its_parent() -> None:
    assert shared_resource_value(CLUSTER + "/agentPools/pool1") == shared_resource_value(CLUSTER) == CLUSTER.lower()
    assert shared_resource_value("  ") is None and shared_resource_value(None) is None
    assert shared_resource_value("https://api.partner.example") == "https://api.partner.example"


def test_two_services_on_one_cluster_give_one_shared_resource_key() -> None:
    keys = by_kind(build_match_keys(facts(resource_identifiers=[CLUSTER, CLUSTER + "/agentPools/x", CLUSTER.upper()])))
    assert len(keys["shared_resource"]) == 1


def test_blank_facts_give_no_keys() -> None:
    assert build_match_keys(MemoryFacts({}, ["", "  "], ["", "   "], None)) == []
    assert build_match_keys(MemoryFacts({}, [], [], "  ")) == []


def test_a_readable_form_is_cut_to_the_maximum() -> None:
    [key] = [key for key in build_match_keys(facts(services={}, resource_identifiers=[], incident_category=None, error_templates=["word " * 200]))]
    assert len(key.display_text) <= MAXIMUM_DISPLAY_CHARACTERS


def test_keys_come_in_a_stable_order_by_kind() -> None:
    assert [key.kind for key in build_match_keys(facts())] == ["service", "shared_resource", "error_signature", "incident_category"]
