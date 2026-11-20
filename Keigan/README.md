# 慧眼 Keigan — the discerning eye for our systems

AI SRE platform for MetLife: incident root cause analysis (three-perspective hypotheses, evidence, blast radius, fixes),
alert noise reduction, SLO monitoring, predictive intelligence, bilingual (EN/JA) communications, Microsoft Teams incident rooms
and blameless postmortems. Keigan **suggests**; people decide and act.

- Backend: Python 3.12 · FastAPI · SQLAlchemy (async) · LangChain / LangGraph — `backend/`
- Frontend: React 19 · TypeScript · Vite 6 · Tailwind v4 · TanStack Query · i18next · MSAL — `frontend/`
- Deployment: Docker + Helm for AKS (frontend and backend namespaces) — `deploy/`
- Plans, design and decisions: `My Plans/` (start with `00_INDEX.md`; progress in `12_FEATURE_TRACKER.md`)

## Run it locally (no cloud access needed)

Everything runs against a **simulated world**: five demo applications (Azure, hardware, mainframe, SaaS), realistic telemetry,
ServiceNow, Teams and email — and a mock AI, so no key is required.

```powershell
# 1. Backend (first time)
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
copy .env.example .env
.\.venv\Scripts\python.exe -m keigan.seed_main          # demo data, ~40 s, safe to re-run

# 2. Backend (every time) — http://localhost:8000, API docs at /api/docs
.\.venv\Scripts\python.exe -m uvicorn keigan.main:app --port 8000

# 3. Frontend (second terminal) — http://localhost:5173
cd frontend
npm install
npm run dev
```

Sign in with a demo user:

| User | Can do |
|---|---|
| Kai Admin — `keigan.admin@keigan.local` | Everything (Keigan admin) |
| Aiko AppAdmin — `aiko.appadmin@keigan.local` | Edits Claims Processing (JP); reads Channel APIs (AU) |
| Rui Reader — `rui.reader@keigan.local` | Reads Claims Processing (JP) and Payments (AU) |
| Noa NoAccess — `noa.noaccess@keigan.local` | Nothing — shows the "request access" page |

## Demo in five minutes

1. Sign in as **Kai Admin**. The seed already started a live incident: *Claims Processing (JP): claim submissions failing with timeouts*.
2. **Home** → open the live incident → read the RCA (what went wrong / why / how to fix), the three hypotheses and the evidence.
3. **Teams room** tab → type `Keigan, what changed in the last hour?` → then `Keigan, this is finished` → the **Postmortem** tab fills in.
4. **Alerts** (noise funnel), **SLO monitoring**, **Intelligence** (early warnings), **Keigan AI chat**:
   *"How many requests failed in the last 17 hours on claims-api?"*, then *"Show me the pattern"*.
5. **Platform settings → Simulation controls** to start another incident scenario on any application.

## Use real AI

In `backend/.env`:

```
LLM_PROVIDER=gemini                 # or azure_openai | openai_compatible (MetLife wrapper) | anthropic
LLM_API_KEY=<your key>
LLM_FAST_MODEL=gemini-2.5-flash
LLM_DEEP_MODEL=gemini-2.5-pro
```

For MetLife's internal gateway: `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=<gateway>/v1`, model names = deployment names,
extra headers in `LLM_EXTRA_HEADERS_JSON`. Nothing outside `backend/keigan/ai/llm_gateway.py` knows which provider is used.

## Go live

Switch each integration from `simulated` to `live` in `backend/.env` (`TELEMETRY_MODE`, `SERVICENOW_MODE`, `TEAMS_MODE`, `EMAIL_MODE`),
set `AUTH_MODE=entra` with the Entra IDs, and follow `My Plans/10_DEPLOYMENT_AKS.md` and `deploy/teams/README.md`.
`AUTH_MODE=local` and the default development secrets only start when `ENVIRONMENT` is `local` or `test`; every other
environment needs Entra and real secrets. The infra checklist (forwarded-header CIDR, egress ranges, Key Vault secrets) is in
`My Plans/16_HARDENING_PLAN.md` under "Go-live prerequisites".

The Docker image installs third-party packages only from `backend/requirements.lock` (pinned, hashed). After changing the
dependencies in `backend/pyproject.toml`, regenerate the lock with the command at the top of that file.

## Useful checks

```powershell
cd backend; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"; .\.venv\Scripts\python.exe -m pytest   # backend tests (see backend/tests/README.md)
cd frontend; npm run build                                   # type check + production build
node scripts/capture-screens.mjs --web http://localhost:5173 --api http://localhost:8000 --out screens   # opens every screen in Edge, reports errors
node scripts/check-locales.mjs                               # translation completeness
```
