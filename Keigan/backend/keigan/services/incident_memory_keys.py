"""The facts of an investigation, as the keys that make two incidents comparable (spec 34, 4.3). Pure: no database, no network.

One function builds the keys, for a past entry and for the current investigation alike, so the two always agree. A key is a kind and a hash of a normalised value, with a short readable form
for "matched on ...". Kinds this build does not produce yet (alert rule, change operation, dependency target) have weights in the catalogue and are added by their own facts later.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from keigan.entities.status_values import IncidentMemoryKeyKind
from keigan.services.incident_memory_scoring import KeyRef
from keigan.utils.error_signature import hash_key_value, normalize_error_template

MAXIMUM_DISPLAY_CHARACTERS = 200
# The resource itself, without the children under it: an agent pool or a database of a server is the same cluster or server for the purpose of "the same shared resource".
_RESOURCE_ROOT = re.compile(r"^(/subscriptions/[^/]+/resourcegroups/[^/]+/providers/[^/]+/[^/]+/[^/]+)", re.IGNORECASE)


@dataclass(frozen=True)
class MemoryFacts:
    services: Mapping[str, str]  # service id -> service name, for the services investigated or affected
    resource_identifiers: Sequence[str]  # Azure resource ids of those services and their components
    error_templates: Sequence[str]  # condensed error templates of evidence with a medium or high signal
    incident_category: str | None


def shared_resource_value(resource_identifier: str | None) -> str | None:
    """The lower-case Azure resource id with any child segments removed, or None when it is blank."""
    text = (resource_identifier or "").strip().lower()
    if not text:
        return None
    root = _RESOURCE_ROOT.match(text)
    return root.group(1) if root else text


def _key(kind: IncidentMemoryKeyKind, value: str, display_text: str) -> KeyRef:
    return KeyRef(kind.value, hash_key_value(value), display_text[:MAXIMUM_DISPLAY_CHARACTERS])


def build_match_keys(facts: MemoryFacts) -> list[KeyRef]:
    keys: dict[tuple[str, str], KeyRef] = {}

    def add(key: KeyRef) -> None:
        keys.setdefault((key.kind, key.value_hash), key)

    for service_id, service_name in sorted(facts.services.items()):
        add(_key(IncidentMemoryKeyKind.SERVICE, service_id, service_name))
    for resource_identifier in facts.resource_identifiers:
        value = shared_resource_value(resource_identifier)
        if value:
            add(_key(IncidentMemoryKeyKind.SHARED_RESOURCE, value, value.rsplit("/", 1)[-1]))
    for template in facts.error_templates:
        signature = normalize_error_template(template)
        if signature:
            add(_key(IncidentMemoryKeyKind.ERROR_SIGNATURE, signature, signature))
    category = (facts.incident_category or "").strip().lower()
    if category:
        add(_key(IncidentMemoryKeyKind.INCIDENT_CATEGORY, category, category))
    order = {kind.value: position for position, kind in enumerate(IncidentMemoryKeyKind)}
    return sorted(keys.values(), key=lambda key: (order[key.kind], key.display_text))
