"""backend/requirements.lock: every third-party package the backend imports is pinned there (the Docker image installs only from it)."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = BACKEND_DIRECTORY / "keigan"
LOCK_FILE = BACKEND_DIRECTORY / "requirements.lock"
# Extras the lock is built with, and extras that are not runtime dependencies. Every other extra is optional and imported lazily.
EXTRAS_IN_LOCK_OR_NOT_RUNTIME = {"azuresql", "dev"}


def normalise_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_distribution_names(lock_text: str) -> set[str]:
    return {normalise_distribution_name(match) for match in re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", lock_text, flags=re.MULTILINE)}


def optional_distribution_names() -> set[str]:
    """Packages of optional extras that are deliberately not in the lock (for example the Anthropic provider, imported only when selected)."""
    extras = tomllib.loads((BACKEND_DIRECTORY / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    requirements = [requirement for extra_name, items in extras.items() if extra_name not in EXTRAS_IN_LOCK_OR_NOT_RUNTIME for requirement in items]
    return {normalise_distribution_name(re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement).group(0)) for requirement in requirements}  # type: ignore[union-attr]


def imported_top_level_modules() -> set[str]:
    modules: set[str] = set()
    for source_file in SOURCE_DIRECTORY.rglob("*.py"):
        for node in ast.walk(ast.parse(source_file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules - set(sys.stdlib_module_names) - {"keigan"}


def distributions_missing_from_lock(lock_text: str) -> set[str]:
    distributions_by_module = packages_distributions()
    locked = locked_distribution_names(lock_text) | optional_distribution_names()
    missing: set[str] = set()
    for module_name in imported_top_level_modules():
        for distribution_name in distributions_by_module.get(module_name, [module_name]):
            if normalise_distribution_name(distribution_name) not in locked:
                missing.add(f"{distribution_name} (imported as {module_name})")
    return missing


def test_every_package_the_backend_imports_is_pinned_in_the_lock_file() -> None:
    assert distributions_missing_from_lock(LOCK_FILE.read_text(encoding="utf-8")) == set()


def test_the_check_notices_a_package_that_is_missing_from_the_lock() -> None:
    lock_without_markdown_parser = "\n".join(
        line for line in LOCK_FILE.read_text(encoding="utf-8").splitlines() if not line.startswith("markdown-it-py==")
    )
    assert distributions_missing_from_lock(lock_without_markdown_parser) == {"markdown-it-py (imported as markdown_it)"}
