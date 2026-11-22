"""keigan/services/chat_service.py has no Ask Keigan limit as a literal in code (AC-20, spec 23 section 11): the limits are settings (section 4.7)."""

from __future__ import annotations

import ast
from pathlib import Path

import keigan.services.chat_service as chat_service

LIMIT_WORDS = ("LIMIT", "MAXIMUM", "MINIMUM", "BUDGET")


def test_chat_service_defines_no_limit_constant_and_passes_no_limit_literal() -> None:
    tree = ast.parse(Path(chat_service.__file__).read_text(encoding="utf-8"))
    constants = [target.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets
                 if isinstance(target, ast.Name) and any(word in target.id.upper() for word in LIMIT_WORDS)]
    literal_arguments = [keyword.arg for node in ast.walk(tree) if isinstance(node, ast.Call) for keyword in node.keywords
                         if keyword.arg and any(word in keyword.arg.lower() for word in ("budget", "limit")) and isinstance(keyword.value, ast.Constant)]
    assert constants == [] and literal_arguments == []
