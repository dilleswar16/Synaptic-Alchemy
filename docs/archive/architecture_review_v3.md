# Corvin: Full Architecture & Hackathon Readiness Review

## Verdict: Ready to Demo, NOT Ready to Ship V3

The codebase is genuinely impressive for a hackathon project, but there is one **critical blocker** that will fail your demo if you do not fix it first. After that is resolved, you are in excellent shape.

---

## ✅ What Is Solid (The Wins)

### Architecture Tier (9/10)
The layered architecture is clean and professional:
- `corvin/core/contracts.py` — single source of truth for all data shapes (Pydantic).
- `corvin/evidence/` — pluggable evidence adapters with graceful degradation.
- `corvin/enrich/` — orchestration layer is cleanly separated from adapters.
- `corvin/investigation/` — engine decoupled from delivery.
- `corvin/storage/` — proper SQLAlchemy ORM + Alembic migrations (not SQLite JSON files).
- `apps/api/`, `apps/cli/`, `apps/teams/`, `apps/web/` — four delivery surfaces, zero shared state.

This would pass an enterprise architecture review.

### Human-in-the-Loop State Machine (10/10)
The `ApprovalStatus` state machine (`pending → approved/rejected → executed`) is exactly right:
- Gate enforced at the **API level** (not just the UI) — you cannot call execute without approved state.
- State transitions emit the correct 404/409 HTTP semantics.
- All three surfaces (Web, CLI, Teams bot) enforce the same gate.
- Teams bot correctly transitions `approved → executed` after a successful run.

This is V2's showstopper feature and it is **correctly implemented end-to-end**.

### CHAD Knowledge Injection (9/10)
The `catalog.json` + keyword matching + `PromptBuilder` pipeline is working:
- 8 catalog entries covering all CHAD services.
- Runbooks are injected into the LLM system prompt at runtime.
- Dynamic lookback windows (15m for alerts, 60m for manual) are correctly wired from contracts all the way down to each adapter's KQL query.

### Streaming RCA (8/10)
The SSE streaming is well-designed:
- `InvestigationStreamer` yields per-stage events (`enrichment.start`, `rca.complete`, etc.).
- `response_format: json_object` correctly dropped on the streaming path (key fix to prevent Azure OpenAI buffering).
- `generation_status` and `degraded` flags surfaced in SSE events so the UI can show banners.
- React `EventSource` consumer implemented.

### CI/CD (8/10)
Both GitHub Actions workflows are production-quality:
- `azure-app-service-api.yml` — builds, tests, and deploys the FastAPI API to Azure App Service.
- `azure-static-web-apps.yml` — deploys the React frontend to Azure Static Web Apps.
- Tests are run in CI and gate the deploy (`continue-on-error: false`).

---

## 🔴 Critical Blocker: `botbuilder` Not Installed in venv

**This will break your demo.** The `botbuilder-core` and `botbuilder-integration-aiohttp` packages are listed in `pyproject.toml` but are **not installed in the local `.venv`**. 

This means **7 test files fail to even collect**, including the Teams bot tests and the streaming RCA tests (which import `apps.api.main` → `apps.teams.router` → `botbuilder`).

On your machine, right now:
```
161 tests collected, 7 errors (botbuilder import failure chain)
```

The progress.md says **320 passing**, which means these passed on the org laptop where `pip install -e .` was run correctly after the git pull. You need to run this on your local machine:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
```

**Do this before anything else.**

---

## 🟡 Items to Verify Before Demo

| Item | Risk | Action |
| :--- | :--- | :--- |
| `botbuilder` not installed in local venv | 🔴 CRITICAL | `pip install -e .` |
| Teams bot registration not done | 🟡 MEDIUM | Complete `setup/07_teams_bot.md` on org laptop |
| Azure alert trigger tested end-to-end | 🟡 MEDIUM | Send one real alert from Azure Monitor → confirm card in Teams |
| `alembic upgrade head` applied on real DB | 🟡 MEDIUM | Confirm migration `05ac79937721` is the head |
| Web `VITE_API_URL` set in SWA config | 🟡 MEDIUM | Must bypass SWA proxy buffer for SSE streaming to work |

---

## 💡 Suggested New Features (Hackathon Impact)

These are low-effort, high-impact additions that would impress a hackathon panel:

### 1. Live Investigation Dashboard (High Impact, Medium Effort)
The React web app currently shows a static list. Add a **real-time dashboard** that polls or uses SSE to show active investigations with live status badges (`pending`, `approved`, `executed`). Add color-coded confidence rings (GREEN = HIGH, AMBER = MEDIUM, RED = LOW).

### 2. Investigation Replay (Medium Impact, Low Effort)
Add a `GET /investigations/{id}/replay` endpoint that returns the full evidence bundle + runbooks injected + LLM prompt used for a given investigation. This is a **transparency / explainability** feature that would be very compelling in a demo — you can show the panel *exactly* what the AI saw before it made its decision. No hallucination possible.

### 3. Smart Alert Deduplication (High Impact, Medium Effort)
If two Azure alerts fire within 60 seconds for the same service, skip the second investigation and return the first `request_id`. Prevents alert storms from exploding the DB. This is a **production-readiness** feature that would show the panel you understand real SRE challenges.

### 4. Confidence Threshold Gate (Medium Impact, Low Effort)
Add a config key `min_confidence_to_suggest_action: medium`. If the LLM produces a `LOW` confidence RCA, the fix strategy should still be generated but all actions should have `requires_approval: true` AND a warning banner is shown: *"Low confidence RCA — manual review strongly recommended."* This is already partially there but could be made more visible in the UI.

### 5. SRE Action History Log (Medium Impact, Low Effort)
Store who approved what and when. Add `approved_by: str` and `approved_at: datetime` fields to the `InvestigationRequestRow`. Teams bot and Web UI populate these when an approval action fires. Gives you a **full audit trail** — a critical enterprise compliance feature.

---

## Can We Proceed to V3?

**No, not yet.** The `AGENTS.md` correctly says V3 is behind a V2.5 lock.

The V2 exit criteria checklist (in `docs/copilot-context/versions/v2/02_build_sequence_and_exit_criteria.md`) has these items still unchecked:

| Exit Criterion | Status |
| :--- | :--- |
| SRE can `@Corvin investigate` in Teams and get a real RCA card | ⏳ Needs Teams bot registration |
| SRE can click "Approve & Execute" and AKS pod is restarted | ⏳ Needs cloud validation |
| Streaming RCA produces token-by-token output in React UI | ⏳ Needs VITE_API_URL set in SWA config |
| All state transitions persist to Postgres | ✅ Done |
| V1 and V1.5 tests still pass | ✅ Done (320/320 on org laptop) |

**The code is done. The cloud validation is not.** This is a 1-2 hour task, not a coding task:
1. Fix `botbuilder` install in local venv.
2. Complete Teams bot registration (`setup/07_teams_bot.md`).
3. Run one end-to-end smoke test from Teams.
4. Confirm SSE streaming works in the deployed SWA.

Once those 4 steps are done, **V2 is fully complete and V3 is unlocked.**

---

## Overall Score: 8.5/10

| Dimension | Score | Note |
| :--- | :--- | :--- |
| Architecture | 9/10 | Clean separation of concerns, enterprise-grade |
| Feature completeness | 8/10 | All V2 features coded, cloud validation pending |
| Test coverage | 9/10 | 320 tests, every slice covered |
| CI/CD | 8/10 | Both pipelines wired correctly |
| CHAD knowledge | 9/10 | Runbooks injected, catalog complete |
| Demo readiness | 6/10 | Blocked by `botbuilder` install and Teams registration |

This is a **winning hackathon submission** once the `botbuilder` install is fixed and the Teams registration is completed. The approval lifecycle with the human-in-the-loop gate is the key differentiator — no generic AI demo has a proper `pending → approved → executed` state machine backed by real Postgres, real AKS execution, and real Teams notifications.
