# Backend tests

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"   # once
.\.venv\Scripts\python.exe -m pytest                     # whole suite
.\.venv\Scripts\python.exe -m pytest tests/unit          # fast, no database
```

## Layout

The folders mirror `keigan/`, so the tests for `keigan/services/alert_pipeline_service.py` live in
`tests/integration/services/test_alert_pipeline_service.py`.

| Folder | What goes there |
|---|---|
| `unit/<package>/` | Pure functions and classes: no database, no HTTP, no network. |
| `integration/<package>/` | Real FastAPI app (in-process HTTP), real SQLAlchemy on a temporary SQLite database, real job worker code. Integrations run in simulated mode and the LLM is the mock provider. |
| `support/` | Test-only helpers: demo users by role, `drain_jobs()` to run queued jobs. |
| `conftest.py` | Isolated environment (temporary DB and data folder) and the shared `seed_context`, `client`, `auth_headers` fixtures. |

## Conventions

- One test file per production module; name it `test_<module>.py`.
- A test name states the behaviour (`test_reader_cannot_create_an_alert_source`), not the method under test.
- Expected values are literals checked by hand, never computed with the code under test.
- **Known bugs** are written as `@pytest.mark.xfail(strict=True, reason="H<n>: ...")` with the ID from
  `My Plans/quality-and-security/16_HARDENING_PLAN.md`. When the fix lands the test passes, `strict` turns that into a failure, and the fix
  removes the marker. A suite with no `XPASS` means every listed bug is still there or fixed and unmarked.
- The session database is shared. Tests that change data create their own records (unique names or ids) rather than
  editing seeded ones.
