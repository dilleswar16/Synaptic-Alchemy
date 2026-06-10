# Corvin Command Center — Technical Documentation

**Version:** V3.95 "Awestruck"  
**Built:** 2026-05-16  
**Status:** Production-ready (requires org network for Azure tools)

---

## What Was Built

A standalone, full-page AI SRE Command Center at `/corvin`. Unlike the
investigation-scoped floating chat widget, this is a global agentic
copilot that can:

- Hold multiple independent conversations (ChatGPT-style sessions)
- Call **15 live tools** that query the real Corvin platform, AKS, Log Analytics, and Elasticsearch
- Render rich data cards in a right-side context panel as tools execute
- **Show live reasoning and tool call progress inline in each chat bubble** (Live Thought system)
- Persist full conversation history in the database
- Auto-title sessions from the first user message

---

## Live Thought Bubble System

Each assistant response bubble has **three stacked sections** that appear sequentially:

### Section 1 — Reasoning (collapsible)
- Appears as soon as the model starts thinking (`thinking` SSE event)
- Amber left-border block, monospace font, scrollable
- Header button: `💭 Reasoning ▼` — click to expand/collapse at any time
- **Auto-collapses** the moment the final text answer starts streaming
- Spinner animates while reasoning is in progress

### Section 2 — Tool Call Timeline (audit trail)
- Each tool call appears immediately as a row when `tool_call` SSE arrives:
  `⟳ Calling 📋 Recent Incidents`
- Transitions to done when `tool_result` SSE arrives:
  `✓ 📋 Recent Incidents · 10 incidents`
- Result preview is extracted per-tool (`extractPreview()` helper)
- Rows stay visible permanently — they are the audit trail of what Corvin did

### Section 3 — Final Answer
- Separated from tool rows by a thin divider
- Streams in token-by-token with blinking cursor
- Full ReactMarkdown + GFM rendering (tables, code blocks, etc.)

### Waiting State
- If no thinking/tools/content yet: shows `⟳ Corvin is thinking…`

### SSE → UiMessage mapping

| SSE event type | Effect on UiMessage |
|---|---|
| `thinking` | Appends to `thinking` field |
| `tool_call` | Appends `{status:'calling'}` ToolStep |
| `tool_result` | Updates matching ToolStep to `{status:'done', resultPreview}` |
| `text` | Appends to `content`; sets `thinkingCollapsed:true` |

---

## Database & Persistence (Postgres & SQLite)

The Corvin Command Center features a persistent chat history backend that supports both SQLite (for local dev) and Postgres (for production/cloud).

### Models
- **`CorvinSessionRow`**: Stores the conversation metadata (ID, Title, Timestamps).
- **`CorvinMessageRow`**: Stores each turn in the conversation.
    - `content`: The final markdown answer.
    - `thinking`: The internal reasoning/thought process (persisted).
    - `tool_calls`: JSONB column storing the list of tools called during that turn.

### Postgres Migrations
When switching to Postgres (`DB_BACKEND=postgres` in `.env`), you must apply the chat history migration:

```bash
# Apply migrations to Azure Postgres
alembic upgrade head
```

The migration `0009_v38_corvin_chat_history.py` creates the required tables with correct Postgres-specific types (`JSONB`).

### Automatic SQLite Setup
For local development using SQLite, the tables are created automatically on startup without needing Alembic.

---

## V3 Features Summary

| Feature | Status | Description |
|---|---|---|
| **Global Chat** | ✅ | Full-page ChatGPT-style interface at `/corvin`. |
| **Agentic Loops** | ✅ | Up to 6 rounds of automated tool execution. |
| **15 Live Tools** | ✅ | Access to AKS, Logs, ROI, Topology, etc. |
| **Live Thought Bubble** | ✅ | Inline reasoning (collapsible) and tool timeline. |
| **Rich Data Cards** | ✅ | Dedicated UI for Investigations, AKS health, etc. |
| **Persistence** | ✅ | Full session save/load with Reasoning history. |


### Frontend
- **Route:** `/corvin` → `CorvinCommandPage.tsx`
- **Layout:** Left sidebar (session list) + Split pane (chat left 58%, context panel right 42%)
- **Session sidebar:** Lists all conversations, newest first. Hover to delete. Click to switch.
- **Context panel:** Renders `ToolResultCard` for each tool call/result. Skeleton shown while tool executes.
- **Streaming:** Uses `streamChat()` from `corvinApi.ts` — async SSE iterator over 5 event types.

### Backend
- **Routes prefix:** `POST/GET/DELETE /corvin/sessions/...` → `apps/api/routes/corvin_agent.py`
- **Agent service:** `corvin/strategy/agent_service.py` — `CorvinAgentService.stream_chat_simple()`
- **Tool definitions:** `corvin/strategy/agent_tools.py` — `TOOL_SCHEMAS` (OpenAI function format) + `execute_tool()`
- **DB tables:** `corvin_sessions`, `corvin_messages` (in `corvin/storage/models.py`)

---

## Agentic Loop

```
User message
  → Build messages list (system prompt + full session history)
  → litellm.completion(tools=TOOL_SCHEMAS, tool_choice="auto", stream=False)
  → If finish_reason == "tool_calls":
      for each tool_call:
        emit SSE: {"type": "tool_call", "tool_name": ..., "arguments": ...}
        result = execute_tool(tool_name, arguments)   ← LIVE DATA, no mocks
        emit SSE: {"type": "tool_result", "tool_name": ..., "data": result}
        append result to messages
      → Re-call LLM (up to 6 rounds)
  → LLM returns final text answer
  → litellm.completion(stream=True) → emit SSE: {"type": "text", "text": chunk}
  → emit SSE: data: [DONE]
```

Max tool rounds: **6** (prevents infinite loops).

---

## SSE Event Types

| Type | Payload fields | Frontend action |
|------|---------------|-----------------|
| `thinking` | `text` | Reasoning block (if model supports it) |
| `tool_call` | `tool_name`, `arguments` | Show skeleton card in right panel |
| `tool_result` | `tool_name`, `data` | Replace skeleton with data card |
| `text` | `text` | Append to assistant bubble |
| `error` | `message` | Show error in bubble |

---

## Tool Inventory (15 live tools)

| Tool | Data source | Needs Azure? |
|------|-------------|-------------|
| `get_platform_stats` | `InvestigationRepository.get_investigation_stats()` | No |
| `list_recent_incidents` | `InvestigationRepository.list_investigations()` | No |
| `get_investigation_detail` | `InvestigationRepository.get_investigation_result()` | No |
| `get_predictive_alerts` | `PredictiveMonitor.refresh_alerts()` | No |
| `get_service_score` | `build_service_score()` | No |
| `get_roi` | `build_roi_stats()` | No |
| `get_service_topology` | `build_service_topology()` | No |
| `get_blast_radius` | `build_blast_radius()` | No |
| `get_postmortem` | `InvestigationRepository.get_post_mortem()` | No |
| `get_similar_incidents` | `InvestigationRepository.get_similar_incidents()` | No |
| `get_site_knowledge` | `KnowledgeLoader.load_site_knowledge()` (knowledge/site.md) | No |
| `get_runbook` | `KnowledgeLoader.load_matching_runbooks()` — DB-first (RunbookRow), disk catalog fallback | No |
| `run_kql` | `LogAnalyticsAdapter.get_apim_logs()` | **Yes** |
| `get_aks_health` | `AKSAdapter.get_pod_context()` | **Yes** |
| `run_elastic_query` | `ElasticAdapter.get_logs/get_metrics()` | **Yes** |

Tools marked **Yes** require network access to the org Azure subscription.
On a personal laptop without VPN, they will return an error which Corvin
will handle gracefully and explain to the user.

---

## Database Tables

### `corvin_sessions`
| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `title` | VARCHAR(255) | Auto-set from first 60 chars of first message |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | Updated on every new message |

### `corvin_messages`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INT PK autoincrement | |
| `session_id` | VARCHAR(36) FK | References `corvin_sessions.id` |
| `role` | VARCHAR(20) | `"user"` or `"assistant"` |
| `content` | TEXT | Full message text |
| `tool_calls` | JSON | List of tools called during this turn (null for user messages) |
| `created_at` | TIMESTAMPTZ | |

---

## API Endpoints

```
POST   /corvin/sessions                         Create new session → {id, title, ...}
GET    /corvin/sessions                         List all sessions [{id, title, message_count, ...}]
GET    /corvin/sessions/{session_id}            Get session + full message history
DELETE /corvin/sessions/{session_id}            Delete session and all messages
POST   /corvin/sessions/{session_id}/chat       Send message, stream SSE response
```

---

## Key Design Decisions

1. **Completely independent of ChatService** — `chat_service.py` and the floating widget
   at `POST /investigations/{id}/chat` are untouched. Two parallel systems.

2. **No mock data** — every tool executor calls the same code path used by the
   existing dashboard endpoints. If Azure is unreachable, the tool returns an error
   dict which the LLM handles gracefully.

3. **Session-scoped memory** — each conversation is a separate `CorvinSession`.
   The full history is sent to the LLM on every turn so the model has complete
   context. No summarization yet (V4 roadmap).

4. **Knowledge base always available** — `get_site_knowledge` and `get_runbook` tools
   query the DB-backed runbook library first (RunbookRow, managed via Applications UI),
   then fall back to the local `knowledge/` directory. No network required. The LLM is
   instructed in the system prompt to call these when asked about CHAD architecture,
   services, or incident playbooks.

5. **Auto-title** — the session title is set to the first 60 characters of the first
   user message, exactly like ChatGPT. Updated on first message, never after.

---

## Running & Testing

Both servers must be running:
```bash
# Backend (from Synaptic Alchemy/)
uvicorn apps.api.main:app --reload --port 8000

# Frontend (from Synaptic Alchemy/apps/web/)
npm run dev
```

Navigate to `http://localhost:5173/corvin`.

### Quick smoke test
1. Click `+ New Chat`
2. Type: `"What's the MTTR this week?"`
3. Expect: `tool_call → get_platform_stats` → skeleton appears in right panel → data card renders → LLM interprets the numbers
4. Type: `"Tell me about CHAD architecture"`
5. Expect: `tool_call → get_site_knowledge` → full architecture text loads → LLM summarizes it
6. Refresh the page → session still exists in sidebar, click it → history reloads

### Azure tools (org laptop only)
- `"Show me APIM logs for partnerapis"` → `run_kql` → real Log Analytics results
- `"Is fundsso healthy in AKS?"` → `get_aks_health` → live pod status
