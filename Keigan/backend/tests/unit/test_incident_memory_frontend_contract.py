"""The kinds and sources the "Seen before" screen knows are the ones the backend produces, and each has a label in every screen language (spec 34)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keigan.entities.status_values import IncidentMemoryCauseSource, IncidentMemoryFixSource, IncidentMemoryKeyKind
from keigan.services.incident_memory_scoring import STALE_OLDER_THAN_THRESHOLD, STALE_SERVICE_REMOVED

FRONTEND_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src"
API = (FRONTEND_SOURCE / "api" / "incidentMemoryApi.ts").read_text(encoding="utf-8")
LOCALES = sorted(path.name for path in (FRONTEND_SOURCE / "i18n" / "locales").iterdir() if path.is_dir() and path.name != "es-MX")
SCREEN_LISTS = {
    "memoryKeyKinds": ("keyKind", {kind.value for kind in IncidentMemoryKeyKind}),
    "memoryCauseSources": ("causeSource", {source.value for source in IncidentMemoryCauseSource}),
    "memoryFixSources": ("fixSource", {source.value for source in IncidentMemoryFixSource}),
    "memoryStaleReasons": ("stale", {STALE_OLDER_THAN_THRESHOLD, STALE_SERVICE_REMOVED}),
}


def screen_values(list_name: str) -> set[str]:
    match = re.search(rf"export const {list_name}:[^=]*=\s*\[(.*?)\];", API, re.DOTALL)
    assert match, f"{list_name} not found in frontend/src/api/incidentMemoryApi.ts"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


@pytest.mark.parametrize("list_name", SCREEN_LISTS)
def test_the_screen_lists_are_the_backend_values(list_name: str) -> None:
    assert screen_values(list_name) == SCREEN_LISTS[list_name][1]


@pytest.mark.parametrize("locale", LOCALES)
def test_every_value_has_a_label_in_every_screen_language(locale: str) -> None:
    labels = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / locale / "investigations.json").read_text(encoding="utf-8"))["similarIncidents"]
    for list_name, (label_group, values) in SCREEN_LISTS.items():
        assert set(labels[label_group]) >= values, f"{locale}: {label_group} lacks {values - set(labels[label_group])}"
    assert set(labels["trust"]) == {"correct", "partially_correct", "incorrect", "none"}
