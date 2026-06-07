# Task: Prompt Centralization

**Status:** Planned — do after V4 pgvector RAG is complete.  
**Estimated effort:** 1 day (implement) + 1 day (test all strategy paths)  
**Priority:** Medium — all prompts work today; this is about maintainability and per-tenant customization.

---

## Why Do This

Today, LLM system prompts are hardcoded as Python string constants inside each strategy module. This means:
- Changing a prompt requires a code deploy.
- No customer can customize prompts without forking the code.
- There is no prompt versioning or diff history.
- Prompts referencing platform-specific language (e.g. "SRE Copilot") cannot be white-labeled.

---

## Industry Standard Approach

Tools like LangSmith, PromptLayer, and enterprise LLM platforms use **versioned prompt templates** stored outside code. The standard pattern:

```
config/prompts/
  agent_service.yaml        # Corvin SRE Copilot system prompt
  chat_service.yaml         # Copilot chat (investigation context)
  fix_strategy.yaml         # Fix strategy generation
  causal_chain.yaml         # Causal chain analysis
  comms_draft.yaml          # Communications drafting (3 audiences)
  nl_to_kql.yaml            # Natural language → KQL
  runbook_builder.yaml      # Conversational runbook creation
  postmortem.yaml           # Post-mortem prevention section
  voice_incident.yaml       # Voice transcription extraction
  chaos_engine.yaml         # Chaos experiment generation
  multi_agent.yaml          # Agent routing selection
```

Each YAML file:
```yaml
version: "1.0"
description: "System prompt for RCA + investigation chat."
variables:
  - name: service_name
    description: "The service being investigated."
  - name: site_knowledge
    description: "Injected from KnowledgeBaseRow or disk."
system: |
  You are Corvin, an elite SRE AI Copilot.
  ...
  ${site_knowledge}
  ...
```

---

## Implementation Plan

### Step 1: Create `corvin/core/prompt_loader.py`

```python
class PromptLoader:
    def load(self, name: str, variables: dict[str, str] = {}) -> str:
        """Load prompt from config/prompts/{name}.yaml, substitute ${var} placeholders."""
        ...

    def _resolve(self, name: str) -> Path:
        """config/prompts/{name}.yaml relative to project root."""
        ...
```

Resolution order:
1. `ApplicationRow.prompt_overrides_json[name]` in DB (per-tenant customization).
2. `config/prompts/{name}.yaml` (platform default).
3. Hardcoded Python constant (backward-compatible fallback during migration).

### Step 2: Migrate Each Strategy File

For each file below, extract the constant and write a YAML file:

| File | Constant | YAML File | Notes |
|------|----------|-----------|-------|
| `corvin/strategy/agent_service.py` | `SYSTEM_PROMPT` | `agent_service.yaml` | SRE Copilot identity |
| `corvin/strategy/chat_service.py` | inline in `_build_system_prompt` | `chat_service.yaml` | Incident context injection |
| `corvin/strategy/fix_strategy_generator.py` | inline user message | `fix_strategy.yaml` | User message template |
| `corvin/strategy/causal_chain.py` | `_SYSTEM_PROMPT` | `causal_chain.yaml` | |
| `corvin/strategy/comms_draft.py` | `_SYSTEM_PROMPTS` dict | `comms_draft.yaml` | 3 audience keys |
| `corvin/strategy/nl_to_kql.py` | `_SYSTEM_PROMPT` | `nl_to_kql.yaml` | |
| `corvin/strategy/runbook_builder.py` | `_SYSTEM_PROMPT` | `runbook_builder.yaml` | |
| `corvin/strategy/postmortem_service.py` | `_PREVENTION_PROMPT` | `postmortem.yaml` | |
| `corvin/strategy/voice_incident.py` | inline extraction prompt | `voice_incident.yaml` | |
| `corvin/strategy/multi_agent.py` | inline selection prompt | `multi_agent.yaml` | |
| `corvin/strategy/chaos_engine.py` | `_system_prompt()` method | `chaos_engine.yaml` | |

### Step 3: Add DB override column

```python
# On ApplicationRow:
prompt_overrides_json: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
# Schema: {"chat_service": "Custom prompt...", "fix_strategy": "..."}
```

Add a "Prompt Overrides" section to the Application Panel for advanced users.

### Step 4: Test each strategy path

Write a test fixture for each strategy that:
1. Verifies the YAML prompt loads correctly.
2. Verifies variable substitution works.
3. Verifies the DB override takes precedence over YAML.
4. Verifies the Python constant fallback works.

---

## Variables Each Prompt Needs

| Prompt | Key Variables |
|--------|---------------|
| `chat_service` | `service_name`, `environment`, `investigation_id`, `root_cause`, `evidence_summary`, `fix_summary`, `site_knowledge`, `runbook` |
| `fix_strategy` | `service_name`, `environment`, `rca_summary`, `evidence_summary` |
| `causal_chain` | `service_name`, `rca_summary`, `contributing_factors` |
| `comms_draft` | `service_name`, `environment`, `rca_summary`, `fix_summary`, `audience` |
| `nl_to_kql` | `workspace_id` (optional), `table_hints` |
| `runbook_builder` | `service_name` |
| `postmortem` | `service_name`, `environment`, `rca_summary`, `fix_summary`, `detection_timeline` |
| `voice_incident` | (none — template only) |
| `chaos_engine` | `service_name`, `environment`, `rca_summary` |
| `multi_agent` | `available_agents` (list) |

---

## What NOT to Centralize

The following should remain in code (they are algorithmic, not textual):
- `investigation/prompt_builder.py` — orchestrates prompt sections dynamically.
- Tool schemas in `agent_tools.py` — these are structured JSON, not free text.
- Evidence formatting in adapters — pure data transformation.

---

## Risk Mitigation

- Migrate one file at a time. Ship the YAML version alongside the Python constant.
- Use the Python constant as the fallback in `PromptLoader.load()`.
- Do NOT delete the Python constants until all tests pass with the YAML version.
- Run the full 433-test suite after each migration.

---

## Estimated Files Changed

| Component | Files |
|-----------|-------|
| New | `corvin/core/prompt_loader.py`, 11 YAML files in `config/prompts/` |
| Modified | 10 strategy files, `corvin/storage/models.py` (prompt_overrides_json column) |
| Frontend | Application Panel "Prompt Overrides" section (optional, for advanced users) |

---

*Created: 2026-06-04. Do after V4 pgvector RAG is shipped and stable.*
