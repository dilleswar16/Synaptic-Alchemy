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

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.prompt_safety import strip_invisible_characters
from keigan.config.settings import RESOURCES_DIRECTORY
from keigan.exceptions.keigan_exceptions import NotFoundException

PROMPTS_DIRECTORY = RESOURCES_DIRECTORY / "prompts"
# Names that users choose are rendered into system prompts, so they are cleaned to one short line of plain words (S6).
_NAME_VARIABLES = ("application_name", "application_code")
_PROMPT_VALUE_UNSAFE_CHARACTERS = re.compile(r"[<>{}`\\]")
MODEL_TIERS_WITHOUT_A_MODEL = ("none",)


def sanitize_prompt_value(value: str, maximum_characters: int = 120) -> str:
    """One short line without markup, quotes or line breaks, so a user-chosen name cannot add instructions to a system prompt."""
    single_line = " ".join(strip_invisible_characters(str(value)).split())
    return _PROMPT_VALUE_UNSAFE_CHARACTERS.sub("", single_line).replace('"', "'")[:maximum_characters].strip()


@dataclass(frozen=True)
class PromptTemplate:
    prompt_key: str
    version: str
    model_tier: str
    body_template: str
    metadata: dict[str, Any]


class PromptLibrary:
    def __init__(self) -> None:
        # The loader lets a prompt ``{% include "_fragment.md" %}`` a shared fragment (files starting with an underscore).
        self._template_environment = Environment(
            loader=FileSystemLoader(PROMPTS_DIRECTORY), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True
        )

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
        for name_variable in _NAME_VARIABLES:
            if name_variable in trusted_variables:
                trusted_variables[name_variable] = sanitize_prompt_value(trusted_variables[name_variable])
        trusted_variables.setdefault("organization_name", sanitize_prompt_value(get_ai_safety_settings().organization_name))
        return self._template_environment.from_string(prompt_template.body_template).render(**trusted_variables).strip()

    def model_tier_for_call(self, prompt_key: str) -> str:
        """The model tier of a prompt that is sent to a model; prompts for humans (``model_tier: none``) are refused."""
        model_tier = self.load_template(prompt_key).model_tier
        if model_tier in MODEL_TIERS_WITHOUT_A_MODEL:
            raise ValueError(f"The prompt {prompt_key} is written for people to copy and must not be sent to a model.")
        return model_tier

    def version_of(self, prompt_key: str) -> str:
        return self.load_template(prompt_key).version
