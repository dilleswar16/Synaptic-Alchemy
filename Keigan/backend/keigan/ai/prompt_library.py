"""Versioned prompt templates loaded from ``keigan/resources/prompts/*.md``.

File format::

    ---
    prompt_key: incident_triage
    version: 1
    model_tier: fast
    ---
    You are Keigan's triage analyst ... {{ application_name }} ...

Only *trusted* values (names, ids, settings, catalogue text) may be rendered into a template. Untrusted content
(logs, incident text, chat) must be passed as ``PromptSection(is_untrusted=True)`` to the LLM gateway instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined

from keigan.config.settings import RESOURCES_DIRECTORY
from keigan.exceptions.keigan_exceptions import NotFoundException

PROMPTS_DIRECTORY = RESOURCES_DIRECTORY / "prompts"


@dataclass(frozen=True)
class PromptTemplate:
    prompt_key: str
    version: str
    model_tier: str
    body_template: str
    metadata: dict[str, Any]


class PromptLibrary:
    def __init__(self) -> None:
        self._template_environment = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)

    @staticmethod
    @lru_cache(maxsize=128)
    def load_template(prompt_key: str) -> PromptTemplate:
        prompt_file_path = PROMPTS_DIRECTORY / f"{prompt_key}.md"
        if not prompt_file_path.exists():
            raise NotFoundException(f"Prompt template {prompt_key} does not exist.")
        file_text = prompt_file_path.read_text(encoding="utf-8")
        front_matter: dict[str, Any] = {}
        body_text = file_text
        if file_text.startswith("---"):
            _, front_matter_text, body_text = file_text.split("---", 2)
            front_matter = yaml.safe_load(front_matter_text) or {}
        return PromptTemplate(
            prompt_key=str(front_matter.get("prompt_key", prompt_key)),
            version=str(front_matter.get("version", "1")),
            model_tier=str(front_matter.get("model_tier", "deep")),
            body_template=body_text.strip(),
            metadata=front_matter,
        )

    def render(self, prompt_key: str, **trusted_variables: Any) -> str:
        prompt_template = self.load_template(prompt_key)
        return self._template_environment.from_string(prompt_template.body_template).render(**trusted_variables)

    def version_of(self, prompt_key: str) -> str:
        return self.load_template(prompt_key).version
