"""Reading the TypeScript types of ``frontend/src/api/askKeiganApi.ts``, so the backend's contract tests can compare them with the API."""

from __future__ import annotations

import re
from pathlib import Path

ASK_KEIGAN_API = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "askKeiganApi.ts").read_text(encoding="utf-8")


def typescript_block(declaration: str) -> str:
    """The text between the braces of ``export interface <declaration> {`` (nested braces included)."""
    start = ASK_KEIGAN_API.index(declaration)
    opening = ASK_KEIGAN_API.index("{", start)
    depth = 0
    for position in range(opening, len(ASK_KEIGAN_API)):
        depth += {"{": 1, "}": -1}.get(ASK_KEIGAN_API[position], 0)
        if depth == 0:
            return ASK_KEIGAN_API[opening + 1:position]
    raise AssertionError(f"{declaration} is not closed")


def typescript_fields(block: str) -> set[str]:
    """The names declared at the top level of an interface body (fields of nested object types are not included)."""
    names: set[str] = set()
    depth = 0
    for line in block.splitlines():
        if depth == 0:
            declared = re.match(r"^(\w+)\??:", line.strip())
            if declared:
                names.add(declared.group(1))
        depth += line.count("{") - line.count("}")
    return names


def interface_fields(name: str) -> set[str]:
    """The fields of ``interface <name>`` (exported or not), without those of an interface it extends."""
    return typescript_fields(typescript_block(f"interface {name} "))


def typescript_union(name: str) -> set[str]:
    match = re.search(rf"export type {name} =\s*(.*?);", ASK_KEIGAN_API, re.DOTALL)
    assert match, f"{name} not found in askKeiganApi.ts"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def inline_object_fields(interface_name: str, field_name: str) -> set[str]:
    """The fields of an object type written inline: ``target: { applicationId: ...; records: ... }``."""
    block = typescript_block(f"interface {interface_name} ")
    match = re.search(rf"\b{field_name}\??:\s*\{{(.*?)\}};", block, re.DOTALL)
    assert match, f"{interface_name}.{field_name} is not an inline object type"
    return set(re.findall(r"(\w+)\??:", match.group(1)))


def event_type_names() -> set[str]:
    """The ``type: "..."`` of every event interface: the event names of the protocol as the screen knows them."""
    return set(re.findall(r'^\s+type: "([a-z.]+)";', ASK_KEIGAN_API, re.MULTILINE))
