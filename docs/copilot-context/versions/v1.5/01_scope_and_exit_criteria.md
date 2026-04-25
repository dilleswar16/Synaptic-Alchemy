# Corvin V1.5 — Real Cloud Integration

## What Is V1.5?

V1 built the entire engine with mocked adapters and an in-memory SQLite database.
All 155 tests pass, but no real cloud service has been contacted yet.

V1.5 is the **integration validation phase**. Its sole purpose is to wire every
adapter to its real Azure cloud counterpart and prove that the end-to-end
pipeline produces a genuine RCA from real logs — no mocks, no stubs, no fakes.

V1.5 does NOT add any new features. It only validates that V1 features
work against real infrastructure.

---

## V1.5 Scope (What Changes)

| Area | What changes |
|---|---|
| Postgres | Switch from local Docker to Azure Database for PostgreSQL Flexible Server |
| Azure OpenAI | Replace LiteLLM stub with real Azure AI Foundry endpoint (gpt-4.1) |
| Elasticsearch | Point ElasticAdapter at real Elastic Cloud cluster with real Java app logs |
| Azure Log Analytics | Point LogAnalyticsAdapter at real workspace with real APIM metrics |
| AKS | Point AKSAdapter at real AKS cluster via kubeconfig / Service Principal |
| Azure Activity Log | Point AzureActivityAdapter at real subscription activity |
| `.env` | Fully populated with real secrets (not placeholders) |

---

## V1.5 Build Sequence

1. Fill in `.env` using `setup/04_env_file.md` with all real Azure credentials.
2. Run `alembic upgrade head` against real Azure Postgres — confirm migration succeeds.
3. Start API with `uvicorn apps.api.main:app --reload` and hit `/health`.
4. Run the Elastic smoke test (see `02_integration_tests.md`).
5. Run the Log Analytics smoke test.
6. Run the AKS smoke test.
7. Run the Azure OpenAI smoke test.
8. Run a full end-to-end investigation via the CLI and confirm a real RCA is returned.
9. Confirm the RCA is persisted to Azure Postgres (check via `corvin› list`).
10. Run the full test suite (`pytest`) — all 155 tests must still pass.

---

## V1.5 Exit Criteria (All Must Pass)

### Infrastructure
- [ ] `alembic upgrade head` runs cleanly against Azure Postgres with no errors.
- [ ] `/health` returns `{"status": "ok"}` with real DB connection.
- [ ] No adapter falls back to mock mode in production config.

### Adapter Smoke Tests
- [ ] `ElasticAdapter` returns at least 1 log entry from a real index in the last 60 minutes.
- [ ] `LogAnalyticsAdapter` returns at least 1 APIM metric row from the real workspace.
- [ ] `AKSAdapter` returns at least 1 pod from the real cluster.
- [ ] `AzureActivityAdapter` returns at least 1 activity entry from the real subscription.
- [ ] `AzureOpenAI` via LiteLLM returns a valid JSON `RCAOutput` with `confidence` field.

### End-to-End
- [ ] Full CLI investigation (`corvin› investigate <service> <env>`) completes in under 60 seconds.
- [ ] RCA returned is non-empty and contains `root_cause`, `summary`, and at least 1 `fix_action`.
- [ ] Investigation record is visible in `corvin› list` after completion (Postgres write confirmed).

### Test Suite
- [ ] `pytest` returns 155/155 pass on the full suite (no regressions from env changes).

---

## V1.5 Failure Conditions

V1.5 is NOT complete if:
- Any adapter still returns mocked or stubbed data in the production `.env` configuration.
- The full end-to-end investigation fails or times out.
- Any of the 155 existing tests regress.
- The RCA output is empty, malformed, or missing key fields.

---

## V1.5 Does NOT Include

- New API endpoints
- New adapters or evidence sources
- Any approval or execution logic
- Any UI changes
- Any Teams integration changes

All of these belong to V2 and later.
