"""What a configured AI model can do (tool calling, streaming, context size, ...), decided by configuration and never by the vendor's name in code.

The catalog ``resources/catalogs/llm_model_capabilities.yaml`` lists per provider the model-name patterns Keigan knows about. The setting
``LLM_MODEL_CAPABILITIES_JSON`` has the same shape and is merged over the catalog, so an admin can describe a new model or a corporate
wrapper without a release. For one provider the first matching entry wins, and flags it does not state come from the defaults.
"""

from __future__ import annotations

import json
from enum import StrEnum
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from keigan.config.settings import RESOURCES_DIRECTORY, LlmProviderName

CAPABILITY_CATALOG_PATH = RESOURCES_DIRECTORY / "catalogs" / "llm_model_capabilities.yaml"
CAPABILITY_OVERRIDES_SETTING = "LLM_MODEL_CAPABILITIES_JSON"


class ToolCallingSupport(StrEnum):
    """How a model is offered tools: its own tool-calling interface, a JSON protocol in the prompt, or not at all."""

    NATIVE = "native"
    PROMPTED_JSON = "prompted_json"
    NONE = "none"


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_calling: ToolCallingSupport
    parallel_tool_calls: bool
    streams_text: bool
    streams_tool_requests: bool
    supports_tool_choice_none: bool
    supports_temperature: bool
    max_context_tokens: int = Field(gt=0)
    reports_stream_usage: bool
    structured_output_method: str | None = None


class _PartialCapabilities(BaseModel):
    """The flags an entry or a defaults block states; the rest stay unset and fall back."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_calling: ToolCallingSupport | None = None
    parallel_tool_calls: bool | None = None
    streams_text: bool | None = None
    streams_tool_requests: bool | None = None
    supports_tool_choice_none: bool | None = None
    supports_temperature: bool | None = None
    max_context_tokens: int | None = Field(default=None, gt=0)
    reports_stream_usage: bool | None = None
    structured_output_method: str | None = None

    def stated_flags(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class _ModelEntry(_PartialCapabilities):
    model: str = Field(min_length=1)


class CapabilityDocument(BaseModel):
    """The shape of the catalog file and of ``LLM_MODEL_CAPABILITIES_JSON``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    defaults: _PartialCapabilities = _PartialCapabilities()
    providers: dict[LlmProviderName, list[_ModelEntry]] = {}


def parse_capability_overrides(overrides_json: str) -> CapabilityDocument:
    """The ``LLM_MODEL_CAPABILITIES_JSON`` document; blank text means no overrides. Names the offending key when it is not valid."""
    if not overrides_json.strip():
        return CapabilityDocument()
    try:
        return CapabilityDocument.model_validate(json.loads(overrides_json))
    except (json.JSONDecodeError, ValidationError) as problem:
        raise ValueError(f"{CAPABILITY_OVERRIDES_SETTING} is not valid: {problem}") from problem


@lru_cache
def _load_catalog() -> tuple[ModelCapabilities, CapabilityDocument]:
    catalog_document = yaml.safe_load(CAPABILITY_CATALOG_PATH.read_text(encoding="utf-8"))
    return ModelCapabilities.model_validate(catalog_document["defaults"]), CapabilityDocument.model_validate({"providers": catalog_document["providers"]})


def resolve_model_capabilities(provider: LlmProviderName, model_name: str, overrides_json: str = "") -> ModelCapabilities:
    """Capabilities of ``model_name`` on ``provider``: override entries first, then the catalog's, then the defaults."""
    catalog_defaults, catalog = _load_catalog()
    overrides = parse_capability_overrides(overrides_json)
    resolved_flags = {**catalog_defaults.model_dump(), **overrides.defaults.stated_flags()}
    for entry in (*overrides.providers.get(provider, []), *catalog.providers.get(provider, [])):
        if fnmatchcase(model_name, entry.model):
            resolved_flags.update(entry.model_dump(exclude={"model"}, exclude_none=True))
            break
    return ModelCapabilities.model_validate(resolved_flags)
