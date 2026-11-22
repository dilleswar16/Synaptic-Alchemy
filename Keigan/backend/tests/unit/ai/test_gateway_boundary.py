"""AC-32: every model call of Ask Keigan goes through ``LlmGateway``, and the tool registry is declarations only (spec 23, 4.5 and 4.6)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KEIGAN_PACKAGE = Path(__file__).resolve().parents[3] / "keigan"
AI_PACKAGE = KEIGAN_PACKAGE / "ai"
MODEL_LIBRARY_PREFIXES = ("langchain", "langgraph")
# The legacy global and Teams investigation chat still drives a LangGraph agent itself; it is removed in phase 4 of the plan (spec 23, section 11, step 4.3), and this entry with it.
LEGACY_MODEL_LIBRARY_USERS = {Path("services") / "investigation_chat_service.py"}
LAYERS_ABOVE_THE_REGISTRY = ("keigan.services", "keigan.controllers", "keigan.repositories", "keigan.workers")
NEW_ASK_KEIGAN_AI_MODULES = ("tool_registry.py", "ask_keigan_errors.py", "ask_keigan_tool_models.py", "ask_keigan_answer_format.py", "ask_keigan_answer_stream.py", "ask_keigan_follow_ups.py", "agent_tool_protocol.py", "agent_turn_types.py")


def imported_modules(path: Path) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


def test_no_module_outside_the_ai_package_imports_a_model_library_except_the_legacy_chat() -> None:
    offenders = {
        path.relative_to(KEIGAN_PACKAGE) for path in KEIGAN_PACKAGE.rglob("*.py")
        if AI_PACKAGE not in path.parents and any(module.startswith(MODEL_LIBRARY_PREFIXES) for module in imported_modules(path))
    }
    assert offenders == LEGACY_MODEL_LIBRARY_USERS


@pytest.mark.parametrize("module_name", NEW_ASK_KEIGAN_AI_MODULES)
def test_the_ask_keigan_modules_of_the_ai_package_import_no_service_controller_or_repository(module_name: str) -> None:
    offending = [module for module in imported_modules(AI_PACKAGE / module_name) if module.startswith(LAYERS_ABOVE_THE_REGISTRY)]
    assert offending == []


def test_the_ask_keigan_engine_modules_reach_the_model_only_through_the_gateway() -> None:
    for path in KEIGAN_PACKAGE.glob("services/ask_keigan_*.py"):
        assert not any(module.startswith(MODEL_LIBRARY_PREFIXES) for module in imported_modules(path)), path.name
