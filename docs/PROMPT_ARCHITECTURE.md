# Corvin — Prompt Architecture Strategy

**Date:** 2026-06-10  
**Phase:** Phase 1 — Productization & Genericization  
**Status:** Design — implementation tracked in PB-021

---

## Problem Statement

All LLM prompts in Corvin are embedded directly in Python source files. This creates four problems:

1. **No auditability:** Prompts cannot be reviewed by non-engineers without reading source code.
2. **No versioning:** Changing a prompt is indistinguishable in git history from changing logic.
3. **No override mechanism:** A customer cannot customize a prompt without forking the codebase.
4. **No evaluation target:** The evaluation framework (when built) has no stable target to test against — any code change might change the prompt without intent.

The goal of the Prompt Architecture is to make prompts first-class configuration artifacts, not embedded strings.

---

## Current State Inventory

All prompts in the codebase are generic — no customer-specific language. The problem is structural, not content-based.

| File | Prompt | Approximate Lines | Status |
|------|--------|-------------------|--------|
| `corvin/investigation/prompt_builder.py` | RCA System Prompt (assembled from parts) | ~150 assembled | Generic content, embedded logic |
| `corvin/strategy/rca_generator.py` | RCA generation instructions | ~40 | Generic, embedded |
| `corvin/strategy/fix_strategy_generator.py` | Fix strategy system prompt | ~30 | Generic, embedded |
| `corvin/strategy/autonomous_agent.py` | Autonomous agent system prompt | ~60 | Generic, embedded |
| `corvin/command_center/agent.py` | Command Center system prompt | ~80 | Generic, embedded |
| `corvin/strategy/debate_engine.py` | Debate / perspective prompts | ~50 | Generic, embedded |
| `corvin/strategy/comms_draft_generator.py` | Audience-specific comms prompts | ~60 | Generic, embedded |
| `corvin/strategy/chaos_generator.py` | Chaos experiment generation prompt | ~40 | Generic, embedded |
| `corvin/strategy/nl_to_kql.py` | NL → KQL translation prompt | ~30 | Generic, embedded |
| `corvin/strategy/causal_chain_generator.py` | Causal chain / DAG prompt | ~30 | Generic, embedded |

---

## Proposed Architecture

### Layer 1 — Prompt Registry

A prompt registry is a directory of versioned YAML files. Each file defines one prompt with:
- A unique ID
- A version number
- A description for human reviewers
- Optional variables (Jinja2 template syntax)
- The actual prompt text as a multi-line YAML string

```
config/
  prompts/
    rca_system.v1.yaml
    rca_system.v2.yaml       ← newer version
    fix_strategy_system.v1.yaml
    autonomous_agent_system.v1.yaml
    command_center_system.v1.yaml
    debate_perspectives.v1.yaml
    comms_draft.v1.yaml
    chaos_generation.v1.yaml
    nl_to_kql.v1.yaml
    causal_chain.v1.yaml
    overrides/               ← customer-specific overrides
      rca_system.yaml        ← overrides the configured version for this deployment
```

### Layer 2 — Prompt Loader

A `PromptRegistry` class loads prompts from the filesystem at startup. It respects:

1. **Configured version** — `config/models/llm.yaml` specifies which version of each prompt to use
2. **Override files** — `config/prompts/overrides/` takes precedence over versioned prompts

```python
# corvin/core/prompt_registry.py (new file)

from pathlib import Path
import yaml
from jinja2 import Template
from functools import lru_cache

class PromptRegistry:
    def __init__(self, prompts_dir: Path, overrides_dir: Path | None = None):
        self._prompts: dict[str, dict] = {}
        self._load(prompts_dir, overrides_dir)

    def _load(self, prompts_dir: Path, overrides_dir: Path | None) -> None:
        # Load versioned prompts
        for path in sorted(prompts_dir.glob("*.v*.yaml")):
            data = yaml.safe_load(path.read_text())
            key = f"{data['id']}.v{data['version']}"
            self._prompts[key] = data

        # Load overrides (override files have no version suffix)
        if overrides_dir and overrides_dir.exists():
            for path in overrides_dir.glob("*.yaml"):
                data = yaml.safe_load(path.read_text())
                prompt_id = data['id']
                # Override wins for all version requests for this prompt ID
                self._prompts[f"{prompt_id}.__override__"] = data

    def get(self, prompt_id: str, version: str | None = None, **kwargs) -> str:
        # Check override first
        override_key = f"{prompt_id}.__override__"
        if override_key in self._prompts:
            return self._render(self._prompts[override_key]['content'], kwargs)

        # Use specified version or configured default
        resolved_version = version or self._get_configured_version(prompt_id)
        key = f"{prompt_id}.v{resolved_version}"
        if key not in self._prompts:
            raise KeyError(f"Prompt '{prompt_id}' version '{resolved_version}' not found")

        return self._render(self._prompts[key]['content'], kwargs)

    def _render(self, template_str: str, variables: dict) -> str:
        return Template(template_str).render(**variables)

    def _get_configured_version(self, prompt_id: str) -> str:
        # Read from llm.yaml prompt_versions section
        # Default: "1"
        ...

# Singleton — instantiated at startup, injected as FastAPI dependency
_registry: PromptRegistry | None = None

def get_prompt_registry() -> PromptRegistry:
    global _registry
    if _registry is None:
        _registry = PromptRegistry(
            prompts_dir=Path("config/prompts"),
            overrides_dir=Path("config/prompts/overrides"),
        )
    return _registry
```

### Layer 3 — Version Configuration

`config/models/llm.yaml` gains a `prompt_versions` section:

```yaml
# config/models/llm.yaml

provider: azure_openai
model: gpt-4.1
# ... existing fields ...

prompt_versions:
  rca_system: "2"              # Use rca_system.v2.yaml
  fix_strategy_system: "1"
  autonomous_agent_system: "1"
  command_center_system: "1"
  debate_perspectives: "1"
  comms_draft: "1"
  chaos_generation: "1"
  nl_to_kql: "1"
  causal_chain: "1"
```

When a generator requests `registry.get("rca_system")`, it gets version 2 unless an override file exists.

---

## YAML Prompt File Format

```yaml
# config/prompts/rca_system.v2.yaml

id: rca_system
version: "2"
description: >
  Main system prompt for the RCA generation pipeline. Instructs the LLM to
  perform structured root cause analysis from an evidence bundle. Version 2
  adds explicit instruction to cite specific evidence items.
author: corvin-team
created: 2026-06-10

# Jinja2 template variables available:
# {{ service_name }}  — the service being investigated
# {{ environment }}   — prod / staging / dev
# {{ runbooks }}      — matched runbook content (may be empty)
# {{ learnings }}     — past incident learnings (may be empty)

content: |
  You are Corvin, an expert SRE AI assistant performing root cause analysis.
  
  Your task is to analyze the evidence bundle for service **{{ service_name }}**
  in **{{ environment }}** and identify the most likely root cause.
  
  ## Instructions
  
  1. Review all evidence sources provided.
  2. Identify patterns and anomalies across sources.
  3. Propose 1-3 root cause hypotheses, ordered by confidence.
  4. For each hypothesis, cite the specific evidence items that support it.
  5. Assign a confidence level: high / medium / low.
  6. Identify any evidence gaps that would increase confidence.
  
  {% if runbooks %}
  ## Relevant Runbooks
  
  {{ runbooks }}
  
  Reference these runbooks when your findings align with known failure patterns.
  {% endif %}
  
  {% if learnings %}
  ## Past Incident Learnings
  
  {{ learnings }}
  
  These are learnings from previous incidents on this service. Treat them as
  strong signals — if a hypothesis matches a past pattern, increase confidence.
  {% endif %}
  
  ## Output Format
  
  Return a JSON object matching the RCAOutput schema. Use json_object mode.
  Do not fabricate evidence. Do not suggest fixes — that is a separate step.
```

---

## Override Strategy

A customer deploying Corvin can provide a custom override for any prompt by:

1. Creating `config/prompts/overrides/<prompt_id>.yaml`
2. Matching the same YAML format (id, content fields required; version field ignored)
3. Restarting the API (or triggering a hot-reload if implemented)

This allows customers to:
- Adjust tone or formality of RCA output
- Add company-specific policies to the fix strategy prompt
- Restrict the chaos generator to specific experiment types
- Add domain context to the NL→KQL prompt (e.g., "Our services always use the field `app_name`")

**What overrides cannot change:**
- The schema of the response object (controlled by Pydantic contracts)
- The tool availability for the autonomous agent (controlled by `toolsets.yaml`)
- The evidence adapters invoked (controlled by application connector config)

---

## Prompt Versioning Strategy

### When to increment the version

Create a new version file (`rca_system.v2.yaml`) when:
- The output structure expected by the calling code changes
- The prompt's fundamental approach changes (e.g., adding chain-of-thought reasoning)
- A regression is detected and the old prompt needs to be preserved for investigation

Do **not** create a new version for:
- Wording improvements that don't change behavior
- Adding/removing whitespace or punctuation
- Clarifying instructions that don't change output structure

For minor wording improvements, edit the existing version file in place. Git history preserves the before/after.

### Version retention policy

- Keep all versions in the filesystem (they are small YAML files)
- Mark deprecated versions with `deprecated: true` in the YAML header
- The `prompt_versions` config in `llm.yaml` can never reference a deprecated version — CI validates this
- After 6 months, deprecated versions may be archived to `config/prompts/archive/`

---

## Evaluation Integration

When the evaluation framework is built (see `docs/AI_GOVERNANCE.md`), the prompt registry is the evaluation target:

```python
# tests/evals/test_rca_prompt.py

def test_rca_system_v2_on_canonical_incidents(prompt_registry, llm_client):
    """Regression test: v2 RCA prompt against canonical incident dataset."""
    for incident in load_canonical_incidents():
        result = rca_generator.generate(
            evidence=incident.evidence,
            prompt_registry=prompt_registry,  # uses v2
        )
        assert cosine_similarity(result.root_cause, incident.expected_root_cause) > 0.8
```

When a new prompt version is proposed, the eval suite must pass before `llm.yaml` is updated to reference the new version.

---

## Migration Plan

### Step 1 — Extract and create YAML files (Week 6 of Phase 1)

For each prompt file listed in the inventory:
1. Extract the prompt string(s) from Python
2. Create corresponding YAML file(s) in `config/prompts/`
3. Update the generator to inject `PromptRegistry` and call `registry.get()`
4. Delete the embedded string from the Python file

### Step 2 — Add version configuration to llm.yaml

Add the `prompt_versions` section to `config/models/llm.yaml`. All versions set to `"1"`.

### Step 3 — Add CI validation

CI gate: `python -m corvin.core.prompt_registry --validate` checks:
- All prompt IDs referenced in `llm.yaml` have corresponding files
- No deprecated versions are referenced
- All YAML files parse without error
- All Jinja2 templates render without error using sample variable values

### Step 4 — Document override mechanism

Add "Customizing Prompts" section to `docs/ONBOARDING_GUIDE.md`.

---

## API Endpoint (Future — Phase 2 or 3)

Once the prompt registry is in place, an admin endpoint can expose it:

```
GET /admin/prompts                    — list all prompt IDs and versions
GET /admin/prompts/{id}               — get a specific prompt with metadata
GET /admin/prompts/{id}/versions      — list all versions
POST /admin/prompts/{id}/override     — create/update a deployment override
DELETE /admin/prompts/{id}/override   — remove override, revert to configured version
```

This makes prompt management accessible from the Corvin admin panel without filesystem access.

---

## See Also

- [docs/PRODUCTIZATION_ASSESSMENT.md](PRODUCTIZATION_ASSESSMENT.md) — Section 6 covers prompt assessment context
- [docs/PRODUCTIZATION_BACKLOG.md](PRODUCTIZATION_BACKLOG.md) — PB-021 tracks implementation
- [docs/AI_GOVERNANCE.md](AI_GOVERNANCE.md) — evaluation framework that uses the prompt registry as its test target
