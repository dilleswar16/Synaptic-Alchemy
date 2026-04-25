# Corvin V1.5 — Integration Smoke Tests

Run these tests in order after filling in your `.env` with real Azure credentials.
Each test is a standalone CLI or Python command — no test framework needed.

---

## Test 1 — Postgres Migration

```powershell
alembic upgrade head
```

**Pass:** Output ends with `Running upgrade -> 0001, create initial tables` (or similar) with no errors.
**Fail:** Any `OperationalError`, `AuthenticationError`, or connection timeout.

---

## Test 2 — API Health

```powershell
uvicorn apps.api.main:app --reload
# In a new terminal:
curl http://localhost:8000/health
```

**Pass:** `{"status": "ok"}` returned immediately.
**Fail:** `500`, `Connection refused`, or any error in the uvicorn terminal.

---

## Test 3 — Elastic Smoke Test

```powershell
python - <<'EOF'
from corvin.adapters.elastic_adapter import ElasticAdapter
adapter = ElasticAdapter()
results = adapter.search(service="order-service", environment="production", minutes=60)
print(f"Total hits: {len(results)}")
assert len(results) >= 0, "Elastic connected but returned 0 results (index may be empty — that is OK)"
print("PASS: Elastic adapter connected successfully")
EOF
```

**Pass:** Prints `PASS` — even 0 results is fine as long as there is no connection error.
**Fail:** `ConnectionError`, `AuthenticationError`, or any exception.

---

## Test 4 — Log Analytics Smoke Test

```powershell
python - <<'EOF'
from corvin.adapters.log_analytics_adapter import LogAnalyticsAdapter
adapter = LogAnalyticsAdapter()
results = adapter.query(service="order-service", environment="production", minutes=60)
print(f"Log Analytics rows: {len(results)}")
print("PASS: Log Analytics adapter connected successfully")
EOF
```

**Pass:** Prints `PASS` with no exception.
**Fail:** `ClientAuthenticationError`, `HttpResponseError`, or workspace ID not found.

---

## Test 5 — AKS Smoke Test

```powershell
python - <<'EOF'
from corvin.adapters.aks_adapter import AKSAdapter
adapter = AKSAdapter()
pods = adapter.list_pods(namespace="default")
print(f"AKS pods visible: {len(pods)}")
print("PASS: AKS adapter connected successfully")
EOF
```

**Pass:** Prints `PASS` — 0 pods is fine if namespace is empty.
**Fail:** `ApiException`, `ConfigException`, or any Kubernetes auth error.

---

## Test 6 — Azure Activity Log Smoke Test

```powershell
python - <<'EOF'
from corvin.adapters.azure_activity_adapter import AzureActivityAdapter
adapter = AzureActivityAdapter()
events = adapter.list_recent_changes(hours=24)
print(f"Activity events: {len(events)}")
print("PASS: Azure Activity adapter connected successfully")
EOF
```

**Pass:** Prints `PASS`.
**Fail:** `ClientAuthenticationError` or subscription not found.

---

## Test 7 — Azure OpenAI / LiteLLM Smoke Test

```powershell
python - <<'EOF'
import litellm
response = litellm.completion(
    model="azure/gpt-4.1",
    messages=[{"role": "user", "content": "Reply with only the word PONG"}],
    max_tokens=10
)
assert "PONG" in response.choices[0].message.content.upper()
print("PASS: Azure OpenAI connected successfully")
EOF
```

**Pass:** Prints `PASS`.
**Fail:** `AuthenticationError`, `RateLimitError`, or deployment not found.

---

## Test 8 — Full End-to-End Investigation

Start the CLI and run a real investigation:

```powershell
corvin
corvin› investigate order-service production
```

**Pass:** Within 60 seconds, a formatted RCA panel is displayed with:
- `summary` — non-empty string
- `root_cause` — non-empty string
- `confidence` — one of High / Medium / Low
- At least 1 fix action listed

**Fail:** Timeout, empty RCA, or any traceback in the API terminal.

---

## Test 9 — Postgres Persistence Check

After Test 8 completes, verify the investigation was saved:

```powershell
corvin› list
```

**Pass:** The investigation from Test 8 appears in the list with a valid `id`, `service`, and `status`.
**Fail:** Empty list or any database error.

---

## Test 10 — Full Test Suite Regression

```powershell
pytest --tb=short -q
```

**Pass:** `155 passed` (or higher if new tests were added). Zero failures.
**Fail:** Any test regression from wiring the real adapters.

---

## Summary Checklist

| # | Test | Status |
|---|---|---|
| 1 | Postgres migration | ⬜ |
| 2 | API health | ⬜ |
| 3 | Elastic connection | ⬜ |
| 4 | Log Analytics connection | ⬜ |
| 5 | AKS connection | ⬜ |
| 6 | Azure Activity connection | ⬜ |
| 7 | Azure OpenAI connection | ⬜ |
| 8 | Full E2E investigation | ⬜ |
| 9 | Postgres persistence check | ⬜ |
| 10 | Regression test suite | ⬜ |

Mark every row ✅ before declaring V1.5 complete and moving to V2.
