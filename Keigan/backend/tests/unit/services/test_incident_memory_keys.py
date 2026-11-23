"""keigan/services/incident_memory_keys.py: the facts of an investigation as comparable keys (spec 34, 4.3)."""

from __future__ import annotations

from keigan.services.incident_memory_keys import (
    MAXIMUM_DISPLAY_CHARACTERS, MemoryFacts, alert_rule_fact, build_match_keys, change_operation_of, dependency_target_of, shared_resource_value,
)
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


# ── Alert rules, changes and failed dependencies ─────────────────────────────────────────────────


def test_two_alerts_of_one_rule_with_different_spacing_and_case_are_one_fact() -> None:
    assert alert_rule_fact(None, "High  CPU on  Claims") == ("high cpu on claims", "High CPU on Claims")
    assert alert_rule_fact(None, "high cpu on claims")[0] == alert_rule_fact(None, "High  CPU on  Claims")[0]  # the value is what is compared; the name is only for display
    assert alert_rule_fact(" /Subscriptions/X/Rules/R1 ", "Anything") == ("/subscriptions/x/rules/r1", "Anything")  # the rule's own identifier wins over its name
    assert alert_rule_fact(None, "  ") is None and alert_rule_fact(None, None) is None


def test_the_target_of_a_failed_dependency_call_is_read_from_the_evidence_message() -> None:
    assert dependency_target_of("Call to dependency Partner-API.Example.com:443 (HTTP) failed with 503") == "partner-api.example.com"
    assert dependency_target_of("Call to dependency sql-prod-1 (SQL) failed with timeout") == "sql-prod-1"
    assert dependency_target_of("Call to dependency ? (HTTP) failed with 500") is None
    assert dependency_target_of("Timeout expired after 30000 ms") is None and dependency_target_of(None) is None


def test_the_operation_of_a_change_is_its_name_or_the_start_of_its_sample_line() -> None:
    assert change_operation_of({"operationName": "Microsoft.Web/sites/config/write"}) == "microsoft.web/sites/config/write"
    assert change_operation_of({"sampleLinesMasked": ["Microsoft.Sql/servers/firewallRules/write by <EMAIL_1>"]}) == "microsoft.sql/servers/firewallrules/write"
    assert change_operation_of({}) is None and change_operation_of({"sampleLinesMasked": []}) is None


def test_alert_rules_changes_and_dependencies_each_become_a_key_in_the_listed_order() -> None:
    keys = build_match_keys(facts(alert_rules=[("high cpu", "High CPU")], change_operations=["Microsoft.Web/sites/config/write", " "], dependency_targets=["partner-api.example.com", ""]))
    assert [key.kind for key in keys] == ["service", "shared_resource", "alert_rule", "error_signature", "change_operation", "dependency_target", "incident_category"]
    by_kind = {key.kind: key for key in keys}
    assert by_kind["alert_rule"].display_text == "High CPU" and by_kind["alert_rule"].value_hash == hash_key_value("high cpu")
    assert by_kind["change_operation"].display_text == "microsoft.web/sites/config/write" and by_kind["dependency_target"].display_text == "partner-api.example.com"


def test_two_changes_of_one_operation_in_different_case_share_a_key() -> None:
    assert build_match_keys(facts(change_operations=["A/B/write"])) == build_match_keys(facts(change_operations=["a/b/WRITE"]))
