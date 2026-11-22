# Common rules for every build agent

Project root: `c:\Users\nites\Documents\My Projects\Keigan`. Windows; PowerShell or Git Bash. Python venv: `backend\.venv\Scripts\python.exe`. Work fully autonomously — nobody can answer questions.

## Before you start
1. **Check what already exists on disk** for your files. A previous run of your slice may have stopped half-way (usage limit). Continue from the current state; never redo finished work, never delete other agents' work.
2. Read `My Plans/00_INDEX.md`, `My Plans/11_BACKEND_FOUNDATION_GUIDE.md` (backend agents), `My Plans/07_BUILD_PHASES_AND_AGENTS.md` (ownership + clarifications), then only the sections your brief lists. Read large files in parts; don't re-read files you already read.

## Token discipline (usage limits are real)
- Read only what you need. Prefer Grep/Glob to locate code, then read the relevant range.
- Write each file in as few passes as possible; avoid rewriting whole files for small fixes (use Edit).
- Don't run `npm run build` or the full seed after every change — once mid-way and once at the end.
- Keep your progress notes and final report short.

## Ownership
Never edit files you don't own (see `07` §2 and your brief). Lead-owned shared files: `backend/keigan/main.py`, `config/*`, `entities/base_entity.py`, `ai/llm_gateway.py`, `ai/prompt_safety.py`, `ai/prompt_library.py`, `integrations/*` (unless your brief lists one), `workers/*`, `security/*`, `utils/*`, `seed/foundation_seed.py`, `seed_main.py`; frontend `components/ui/*`, `components/layout/*`, `components/charts/*`, `components/topology/*`, `api/httpClient.ts`, `auth/*`, `i18n/index.ts`, `styles/*`, `app/*` (F0 owns these until it finishes). Missing shared capability → implement locally in your files and add a line to `My Plans/09_LEARNINGS_LOG.md`.
You may add columns only to your own domain's entity file (record in `03_DATABASE_DESIGN.md` change log).

## Running and testing
- Own database and port (see your brief): from `backend/`: `$env:DATABASE_URL="sqlite+aiosqlite:///./data/keigan_<slice>.db"`, then `.\.venv\Scripts\python.exe -m keigan.seed_main`, then `.\.venv\Scripts\python.exe -m uvicorn keigan.main:app --port <port>` (run in background). Stop servers you start before you finish.
- Test HTTP with **curl in Git Bash** (PowerShell `Invoke-RestMethod` hangs on localhost here). Sign in: `curl -s -X POST http://127.0.0.1:<port>/api/auth/local-sign-in -H 'Content-Type: application/json' -d '{"userPrincipalName":"keigan.admin@keigan.local"}'`.
- Backend import check: `.\.venv\Scripts\python.exe -c "import keigan.main"`.
- Frontend: only start frontend work when `frontend/FOUNDATION_READY.md` exists. If it doesn't when your backend is done, polish backend/seed/mocks, then wait with `$i=0; while (-not (Test-Path "c:\Users\nites\Documents\My Projects\Keigan\frontend\FOUNDATION_READY.md") -and $i -lt 9) { Start-Sleep 60; $i++ }` (repeat up to ~60 min). Read `FOUNDATION_READY.md` and the guide at the end of `04_UI_UX_DESIGN_SYSTEM.md` before writing UI. Finish with `npm run build` (zero TypeScript errors).

## Quality bar
Descriptive names (no abbreviations), lean code (one service class per capability, private helpers), Java-like layering (controller → service → repository/entities; DTOs in `dtos`), RBAC on every endpoint, audit on writes, PII masked before AI, untrusted text only via `PromptSection(is_untrusted=True)`, secrets never returned, all UI strings via i18n, light + dark themes, loading/empty/error states. No unit-test suites now; smoke-test instead.
Mock mode (`LLM_PROVIDER=mock`) must produce realistic output for your AI features (`register_mock_response`) so the demo works without an API key.

## Finish
Append learnings to `My Plans/09_LEARNINGS_LOG.md`; update `05_API_CONTRACT.md` if your endpoints differ; final report (≤ 25 lines): what works end to end, endpoints, files, known gaps, guarded cross-slice calls.
