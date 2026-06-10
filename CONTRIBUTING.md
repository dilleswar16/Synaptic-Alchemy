# Contributing to Corvin

This document is the single source of truth for contribution standards, code conventions, testing patterns, and development workflow. All contributors — human and AI — must follow these rules exactly.

**Read this before writing a single line of code.**

---

## Development Setup

```powershell
# Backend
pip install -e ".[dev]"
cp .env.example .env    # populate all values — see setup/04_env_file.md

# Run migrations
alembic upgrade head

# Start API server
uvicorn apps.api.main:app --reload --port 8000

# Frontend
cd apps/web && npm install && npm run dev

# Activate the shared venv if using it
C:\venv\corvin\Scripts\Activate.ps1
```

---

## Running Tests

```powershell
pytest tests/ -v --tb=short          # full suite
pytest tests/slices/ -v              # slice tests only
pytest -k "test_approval" -v         # single test by name
```

**All existing tests must stay green after every change.** If your change breaks a test, fix either the code or the test — never skip or delete a test.

---

## Code Conventions

### 1. Contracts are the source of truth

All domain types are defined in `corvin/core/contracts.py`. This is the only place where shared data shapes live.

- Any change to a persisted field in `contracts.py` requires a matching Alembic migration.
- Do not duplicate type definitions in route schemas when you can import from contracts.
- Never add business logic to contracts — they are data shapes only.

### 2. Adapters must be resilient

Every evidence adapter method must return an empty list or dict on failure — never raise. Use `logger.warning(...)` and `return []`. `EnrichmentService` handles partial evidence correctly.

```python
def get_apim_logs(self, service_name: str, ...) -> list[dict]:
    try:
        # ... real call ...
    except Exception as exc:
        logger.warning("Log Analytics call failed: %s", exc)
        return []
```

### 3. LLM output uses json_object mode

Never use `json_schema` strict mode with the Azure OpenAI / LiteLLM endpoint. Always instruct the model to return JSON matching the target Pydantic schema in the system prompt text — not via the `response_format` schema field.

### 4. All automated actions require human approval

No `ExecutionService` method may be called without `ApprovalStatus.APPROVED` in Postgres. The gate is enforced at the API route level (`POST /investigations/{id}/execute`). Do not bypass it.

### 5. Environment variables use the CORVIN_ prefix for DB settings

- `CORVIN_DB_HOST`, `CORVIN_DB_USER`, `CORVIN_DB_PASSWORD`, `CORVIN_DB_NAME`
- All other vars follow their service's naming convention (`AZURE_CLIENT_ID`, `ELASTIC_HOST`)
- Never invent a new environment variable name without adding it to `.env.example` and `setup/04_env_file.md`

### 6. Config files use `${VAR_NAME}` expansion

All `config/integrations/*.yaml` files use `${ENV_VAR}` placeholders. The `_expand()` helper in each adapter resolves them at runtime via `os.environ`. Do not hardcode values that belong in config.

### 7. No business logic in route handlers

Routes validate input, call service classes, and return responses. Business logic — calculations, LLM calls, data transformations — belongs in service classes under `corvin/strategy/` or `corvin/investigation/`.

---

## Testing Patterns

### Unit Tests — Use Fake Adapter Subclasses

Never use `unittest.mock.patch`. Subclass the real adapter and override only what you need. This keeps tests readable and avoids mock-reality divergence.

```python
class FakeLogAnalytics(LogAnalyticsAdapter):
    def get_apim_logs(self, service_name: str, ...) -> list[dict]:
        return [{"apim_event": "timeout", "service": service_name}]

def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="test investigation",
    )
```

The canonical example: `tests/slices/test_slice2_enrichment_service.py`

### Integration Tests

Integration tests may hit real Azure endpoints. They require a populated `.env`. Mark them clearly and ensure they are optional in CI (`pytest -m "not integration"`).

### Test File Naming

Slice tests: `tests/slices/test_slice_{version}_{feature}.py`  
Adapter tests: `tests/adapters/test_{adapter_name}.py`  
Contract tests: `tests/contracts/test_{contract_name}.py`

---

## Database Migrations

```powershell
# Apply pending migrations
alembic upgrade head

# Create a new migration after modifying SQLAlchemy models
alembic revision --autogenerate -m "describe_change_in_snake_case"

# Check current state
alembic current
```

**Rules:**
- Migration files must use sequential 4-digit prefixes: `0025_`, `0026_`, etc.
- Never create two migration files with the same prefix number.
- Run `alembic check` in CI to catch unapplied model changes.
- Do not modify the `_SQLITE_COLUMN_MIGRATIONS` list in `db.py` — SQLite is for testing only and does not need manual migration tracking.

---

## What NOT to Do

- Do not add Elasticsearch as a hard dependency — it is optional and may be blocked by org SSO.
- Do not call `ExecutionService` without checking `ApprovalStatus.approved`.
- Do not modify `corvin/core/contracts.py` without a matching Alembic migration.
- Do not use `json_schema` strict mode with LiteLLM + Azure OpenAI.
- Do not mock adapters with `unittest.mock.patch` — use Fake subclasses.
- Do not invent new environment variable names — always check `.env.example` first.
- Do not add new env var names without updating both `.env.example` and `setup/04_env_file.md`.
- Do not commit `.db` database files — they are in `.gitignore` for a reason.
- Do not hardcode customer-specific values (currency, locale, organization names, logos) in code or policy files.
- Do not put business logic inside route handlers — route handlers call services, nothing more.
- Do not set `litellm.drop_params = True` or similar global flags outside of the module where they are needed.

---

## Runbook Management

Runbooks are loaded in two tiers — DB first, disk fallback.

**Primary (DB):** Add runbooks via the Application Panel UI → Runbook Library tab. Takes effect immediately, no restart required.

**Fallback (disk):** When adding a runbook to `knowledge/runbooks/`, two steps are required:
1. Create the `.md` file with `keywords:` frontmatter.
2. Add an entry to `knowledge/runbooks/catalog.json` with the correct `match_patterns`.

Skipping step 2 means the disk runbook will never be injected into the LLM prompt.

---

## Pull Request Standards

- One PR per feature or fix — do not batch unrelated changes.
- PRs must have a description explaining *why*, not just *what*.
- All tests must pass in CI before merge.
- Alembic migrations must be included in the same PR as the model change.
- Never force-push to `main`.
- Never skip CI with `--no-verify`.

---

## AI Agent Rules

If you are an AI agent (Claude, Copilot, Cursor, Gemini) contributing to this repository, also read:

- `AGENTS.md` — mental model, version state, current focus
- `.github/instructions/` — scoped guidance for architecture, Azure evidence, and UI
- `.github/prompts/` — reusable prompts for implementation slices

The rules in this document apply to AI agents equally. An AI agent that breaks an existing test or commits a database file has made the same mistake as a human contributor.
