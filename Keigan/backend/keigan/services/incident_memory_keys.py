"""The facts of an investigation, as the keys that make two incidents comparable (spec 34, 4.3). Pure: no database, no network.

One function builds the keys, for a past entry and for the current investigation alike, so the two always agree. A key is a kind and a hash of a normalised value, with a short readable form
for "matched on ...". The three helpers under the dataclass read a fact out of what a row stores (an alert's rule, a change evidence pattern, a failed-dependency message).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from keigan.entities.status_values import IncidentMemoryKeyKind
from keigan.services.incident_memory_scoring import KeyRef
from keigan.utils.error_signature import hash_key_value, normalize_error_template

MAXIMUM_DISPLAY_CHARACTERS = 200
# "Call to dependency <target> (<type>) failed with <code>" is the message evidence collection writes for a failed dependency call.
_DEPENDENCY_MESSAGE = re.compile(r"call to dependency\s+(\S+)\s+\(", re.IGNORECASE)
_PORT_SUFFIX = re.compile(r":\d+$")
_SAMPLE_OPERATION = re.compile(r"^(.+?)\s+by\s+", re.IGNORECASE)  # an older change pattern only has "<operation> by <caller>" as its sample line
# The resource itself, without the children under it: an agent pool or a database of a server is the same cluster or server for the purpose of "the same shared resource".
_RESOURCE_ROOT = re.compile(r"^(/subscriptions/[^/]+/resourcegroups/[^/]+/providers/[^/]+/[^/]+/[^/]+)", re.IGNORECASE)


@dataclass(frozen=True)
class MemoryFacts:
    services: Mapping[str, str]  # service id -> service name, for the services investigated or affected
    resource_identifiers: Sequence[str]  # Azure resource ids of those services and their components
    error_templates: Sequence[str]  # condensed error templates of evidence with a medium or high signal
    incident_category: str | None
    alert_rules: Sequence[tuple[str, str]] = ()  # (normalised value, readable name) of the rules of the alerts that raised this incident
    change_operations: Sequence[str] = ()  # Activity Log operation names of the changes found around it
    dependency_targets: Sequence[str] = ()  # hosts or names of the dependencies that failed


def shared_resource_value(resource_identifier: str | None) -> str | None:
    """The lower-case Azure resource id with any child segments removed, or None when it is blank."""
    text = (resource_identifier or "").strip().lower()
    if not text:
        return None
    root = _RESOURCE_ROOT.match(text)
    return root.group(1) if root else text


def alert_rule_fact(rule_identifier: str | None, rule_name: str | None) -> tuple[str, str] | None:
    """The rule's own identifier when it has one, else its name with the spacing and case folded: two alerts of one rule give one fact."""
    identifier = " ".join((rule_identifier or "").lower().split())
    name = " ".join((rule_name or "").split())
    value = identifier or name.lower()
    return (value, name or identifier) if value else None


def dependency_target_of(template: str | None) -> str | None:
    """The host (or name) of a failed dependency call, lower-case and without a port, from the message evidence collection wrote; None for any other text."""
    match = _DEPENDENCY_MESSAGE.search(template or "")
    target = _PORT_SUFFIX.sub("", match.group(1).strip().lower().strip("<>\"'")) if match else ""
    return target if target and target != "?" else None


def change_operation_of(pattern: Mapping[str, object]) -> str | None:
    """The Activity Log operation of one change pattern (``operationName``, else the part of the sample line before " by "), lower-case."""
    operation = str(pattern.get("operationName") or "").strip().lower()
    if not operation:
        samples = pattern.get("sampleLinesMasked") or []
        match = _SAMPLE_OPERATION.match(str(samples[0])) if isinstance(samples, list) and samples else None
        operation = match.group(1).strip().lower() if match else ""
    return operation or None


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
    for rule_value, rule_name in facts.alert_rules:
        add(_key(IncidentMemoryKeyKind.ALERT_RULE, rule_value, rule_name))
    for operation in facts.change_operations:
        if operation.strip():
            add(_key(IncidentMemoryKeyKind.CHANGE_OPERATION, operation.strip().lower(), operation.strip().lower()))
    for target in facts.dependency_targets:
        if target.strip():
            add(_key(IncidentMemoryKeyKind.DEPENDENCY_TARGET, target.strip().lower(), target.strip().lower()))
    category = (facts.incident_category or "").strip().lower()
    if category:
        add(_key(IncidentMemoryKeyKind.INCIDENT_CATEGORY, category, category))
    order = {kind.value: position for position, kind in enumerate(IncidentMemoryKeyKind)}
    return sorted(keys.values(), key=lambda key: (order[key.kind], key.display_text))
