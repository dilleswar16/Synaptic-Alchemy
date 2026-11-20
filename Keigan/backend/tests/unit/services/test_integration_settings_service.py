"""keigan/services/integration_settings_service.py: the integration field catalog the onboarding form is built from (W2-3)."""

from __future__ import annotations

from keigan.services.integration_settings_service import KNOWN_INTEGRATION_FIELD_TYPES, load_integration_field_schemas


def test_known_field_types_are_the_ones_the_form_can_render() -> None:
    assert KNOWN_INTEGRATION_FIELD_TYPES == frozenset({"text", "url", "select", "secret", "key_value_list", "textarea"})


def test_every_field_in_the_catalog_has_a_known_type() -> None:
    unknown_types = {
        (integration_kind, field["key"], field["fieldType"])
        for integration_kind, schema in load_integration_field_schemas().items()
        for field in schema["fields"]
        if field["fieldType"] not in KNOWN_INTEGRATION_FIELD_TYPES
    }
    assert unknown_types == set()


def test_no_field_asks_for_a_secret_name_any_more() -> None:
    field_keys = {field["key"] for schema in load_integration_field_schemas().values() for field in schema["fields"]}
    assert "credential_secret_name" not in field_keys


def test_cmdb_ei_portal_and_knowledge_api_each_have_one_write_only_credential_field() -> None:
    secret_field_keys = {
        integration_kind: [field["key"] for field in schema["fields"] if field["fieldType"] == "secret"]
        for integration_kind, schema in load_integration_field_schemas().items()
    }
    assert secret_field_keys == {"cmdb": ["credential_value"], "ei_portal": ["credential_value"], "knowledge_api": ["credential_value"]}
