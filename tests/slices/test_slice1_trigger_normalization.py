"""
Slice 1 tests: Azure alert trigger normalization.

Validates that normalize_azure_alert produces a correct InvestigationRequest
from a realistic Azure Monitor Common Alert Schema payload.

These tests use no external dependencies and should run immediately.
This is the first testable slice in the V1 build sequence.
"""

from __future__ import annotations

import pytest

from corvin.core.contracts import TriggerSource
from corvin.triggers.azure_alert import normalize_azure_alert

# ── Fixtures ──────────────────────────────────────────────────────────────────

FULL_ALERT_PAYLOAD = {
    "schemaId": "azureMonitorCommonAlertSchema",
    "data": {
        "essentials": {
            "alertId": "/subscriptions/sub-abc/providers/Microsoft.AlertsManagement/alerts/alert-123",
            "alertRule": "HighCPUAlert",
            "description": "CPU above 90% for 5 minutes",
            "severity": "Sev2",
            "monitoringService": "Platform",
            "alertTargetIDs": [
                "/subscriptions/sub-abc/resourceGroups/rg-prod/providers/"
                "Microsoft.Compute/virtualMachineScaleSets/order-service-vmss"
            ],
        }
    },
}

MINIMAL_ALERT_PAYLOAD: dict = {
    "schemaId": "azureMonitorCommonAlertSchema",
    "data": {"essentials": {"alertRule": "MyRule"}},
}

EMPTY_PAYLOAD: dict = {}


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_trigger_source_is_azure_alert():
    req = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert req.trigger_source == TriggerSource.AZURE_ALERT


def test_service_name_extracted_from_target_id():
    req = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert req.service_name == "order-service-vmss"


def test_description_from_essentials():
    req = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert req.description == "CPU above 90% for 5 minutes"


def test_environment_from_monitoring_service():
    req = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert req.environment == "Platform"


def test_raw_payload_preserved():
    req = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert req.raw_payload == FULL_ALERT_PAYLOAD


def test_id_is_generated():
    req = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert req.id
    assert len(req.id) == 36


def test_two_alerts_get_different_ids():
    r1 = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    r2 = normalize_azure_alert(FULL_ALERT_PAYLOAD)
    assert r1.id != r2.id


def test_minimal_payload_falls_back_to_alert_rule():
    req = normalize_azure_alert(MINIMAL_ALERT_PAYLOAD)
    assert req.service_name == "MyRule"


def test_empty_payload_produces_sensible_defaults():
    req = normalize_azure_alert(EMPTY_PAYLOAD)
    assert req.trigger_source == TriggerSource.AZURE_ALERT
    assert req.service_name == "unknown-service"
    assert req.description == "Azure alert"
