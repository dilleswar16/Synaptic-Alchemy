# Next Features Build Plan — V5 Roadmap

**Status:** Ready to implement (post enterprise-grade sweep complete).  
**Order:** Feature 8 → 9 → 10 → 7 (pgvector last, needs DB migration).  
**Principle:** Zero hardcodes. No customer-specific strings anywhere in source. Every configurable value comes from DB or `config/` YAML. Every new endpoint is generic and multi-tenant safe.

---

## Feature 8 — Root Cause Debate Mode (Competing Hypotheses)

**Goal:** Instead of a single RCA answer, present 3 competing hypotheses ranked by evidence strength. SRE selects the winner. Winner hypothesis becomes the canonical root cause for fix strategy generation.

### Backend

**New Pydantic model** (`corvin/core/contracts.py`):
```python
class RCAHypothesis(BaseModel):
    id: str                         # "h1" | "h2" | "h3"
    title: str                      # Short label e.g. "Memory Leak in Worker Pool"
    root_cause: str                 # Full explanation
    evidence_ids: list[str]         # Evidence keys that support this hypothesis
    confidence_score: float         # 0.0–1.0 (LLM-assigned)
    evidence_strength_pct: int      # 0–100 (rendered as progress bar)
    supporting_signals: list[str]   # Bullet list of key signals
    refuting_signals: list[str]     # Signals that argue against this hypothesis
```

**Modified `InvestigationResult`** (`corvin/core/contracts.py`):
```python
class InvestigationResult(BaseModel):
    ...
    rca: RCAResult                          # Existing — selected/confirmed hypothesis
    hypotheses: list[RCAHypothesis] | None  # New — all 3 candidates
    selected_hypothesis_id: str | None      # New — set when SRE selects
```

**Modified DB** (`corvin/storage/models.py`):
```python
# On InvestigationRow:
hypotheses_json: Mapped[dict | None]        # stores list[RCAHypothesis] as JSON
selected_hypothesis_id: Mapped[str | None]  # "h1" | "h2" | "h3" | None
```

**Modified system prompt** (`corvin/strategy/agent_service.py` or `config/prompts/agent_service.yaml` once prompt centralisation is done):
- Add a phase after evidence collection: **HYPOTHESES GENERATION**
- Instruct LLM to generate exactly 3 distinct hypotheses in JSON matching `RCAHypothesis` schema
- Instruction: "Do NOT converge on one root cause during hypothesis generation. Maintain genuine diversity between hypotheses. One should focus on infrastructure (OOM/CPU), one on code/config change, one on upstream dependency."

**New API endpoint** (`apps/api/routes/investigations.py`):
```
POST /investigations/{id}/select-hypothesis
Body: { "hypothesis_id": "h1" }
Effect: sets selected_hypothesis_id, re-runs fix strategy generation based on selected hypothesis
Returns: updated InvestigationResult
```

**Config** (`config/policies/investigation.yaml`):
```yaml
debate_mode:
  enabled: true           # feature flag — can be disabled per tenant
  hypothesis_count: 3     # number of competing hypotheses (default 3)
  min_evidence_signals: 2 # minimum signals required before hypothesis is valid
```

### Frontend

**New component** `apps/web/src/components/investigation/HypothesisDebatePanel.tsx`:
- 3-column layout, one card per hypothesis
- Each card: title, confidence bar (0–100%), supporting signals list, refuting signals list
- "Select as Root Cause" button on each card
- Selected card highlighted with `--c-signal` border
- Loading skeleton while hypotheses stream in
- Empty state: "Hypotheses not available for this investigation (generated before Feature 8 was enabled)"

**Modified** `apps/web/src/pages/InvestigationsPage.tsx` or the investigation detail view:
- Render `HypothesisDebatePanel` below the RCA section when `hypotheses` are present
- Show "✓ Root Cause Selected" badge after SRE picks one

### No Hardcodes
- Hypothesis count is configurable via `investigation.yaml`
- `debate_mode.enabled` flag allows disabling per deployment
- JSON schema for hypotheses is Pydantic-validated — no string parsing
- Old investigations without `hypotheses_json` show graceful empty state

---

## Feature 9 — Incident Heatmap Calendar

**Goal:** GitHub-contribution-style 90-day calendar showing investigation density by day, on the dashboard. Dark cells = many incidents. Click a cell → filter investigations list to that day.

### Backend

**New endpoint** (`apps/api/routes/investigations.py`):
```
GET /investigations/heatmap?days=90&service_name=&environment=
Returns:
{
  "days": [
    { "date": "2026-03-01", "count": 0, "severity": "none" },
    { "date": "2026-03-02", "count": 3, "severity": "high" },
    ...
  ],
  "max_count": 7,
  "total_incidents": 142,
  "date_range": { "start": "...", "end": "..." }
}
```

**SQL query** (pure DB — no ML):
```sql
SELECT DATE(created_at) as day, COUNT(*) as count
FROM investigation_requests
WHERE created_at >= NOW() - INTERVAL '<days> days'
  AND (:service_name IS NULL OR service_name = :service_name)
  AND (:environment IS NULL OR environment = :environment)
GROUP BY DATE(created_at)
ORDER BY day ASC
```

**Severity thresholds** (`config/policies/investigation.yaml`):
```yaml
heatmap:
  severity_thresholds:
    low:    1    # 1 incident
    medium: 3    # 3+ incidents
    high:   5    # 5+ incidents
    critical: 10 # 10+ incidents
  default_days: 90
  max_days: 365
```

### Frontend

**New component** `apps/web/src/components/IncidentHeatmap.tsx`:
- Pure CSS grid — 7 columns (days of week), rows = weeks
- 5 color shades matching `--c-surface-2` through `--c-red`
- Responsive: compact on mobile (no labels), full on desktop
- Hover tooltip: "3 incidents on June 4" with list of service names
- Click cell: emits `onDayClick(date: string)` callback — parent filters investigations list
- Week labels on left, month labels on top (same pattern as GitHub)
- Color scale legend at bottom right

**Props interface** (no hardcodes, fully data-driven):
```typescript
interface IncidentHeatmapProps {
  days?: number          // default from config, passed as prop
  serviceFilter?: string
  environmentFilter?: string
  onDayClick?: (date: string) => void
  compact?: boolean      // for dashboard widget vs full page
}
```

**Placement**: Dashboard page, below the SLO overview cards.

### No Hardcodes
- Day count comes from `investigation.yaml` `heatmap.default_days`, passed to component as prop
- Severity thresholds come from `investigation.yaml`, returned in the API response
- Color scheme uses CSS variables only — customers can theme it

---

## Feature 10 — Compliance Evidence Pack

**Goal:** One-click download of a tamper-evident audit bundle for a specific investigation. For SOX / SOC2 compliance auditors. Includes: investigation timeline, evidence collected, RCA, fix actions taken, approval records, SHA-256 integrity hash.

### Backend

**New endpoint** (`apps/api/routes/investigations.py`):
```
GET /investigations/{id}/compliance-pack?format=pdf|zip
```

**ZIP bundle contents** (when `format=zip`):
```
corvin-evidence-pack-<id>/
  manifest.json          # metadata + SHA-256 of all files
  investigation.json     # full InvestigationResult as JSON
  evidence/
    aks_pods.json        # raw AKS evidence
    container_logs.json  # raw container log evidence
    apim_logs.json       # raw APIM evidence
  rca.md                 # human-readable RCA
  fix_strategy.md        # human-readable fix strategy
  approval_audit.json    # approval_status, approver, timestamp
  postmortem.md          # if generated
  integrity.sha256       # SHA-256 hash of manifest.json
```

**PDF bundle** (when `format=pdf`): Single document with all sections, header/footer with investigation ID + generated timestamp, watermark "CONFIDENTIAL — FOR AUDIT USE".

**Integrity hash**:
```python
import hashlib, json
manifest = { "investigation_id": id, "generated_at": now.isoformat(), "files": [...] }
manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
sha256 = hashlib.sha256(manifest_bytes).hexdigest()
# Written to integrity.sha256 in the bundle
```

**Config** (`config/policies/investigation.yaml`):
```yaml
compliance_pack:
  enabled: true
  watermark_text: "CONFIDENTIAL — FOR AUDIT USE"
  include_raw_evidence: true
  supported_frameworks:       # shown in the report header
    - SOX
    - SOC2
    - ISO27001
```

### Frontend

**New button** in the investigation detail view:
- "📦 Download Evidence Pack" with dropdown: PDF | ZIP
- Shows spinner during generation (large investigations may take 5–10s)
- On success: browser download triggered via `Content-Disposition: attachment`

**New API client function** (`apps/web/src/api/client.ts`):
```typescript
export async function downloadCompliancePack(
  investigationId: string,
  format: 'pdf' | 'zip'
): Promise<Blob>
```

### No Hardcodes
- Watermark text configurable in `investigation.yaml`
- Compliance frameworks list configurable (shown in header only, no logic tied to them)
- ZIP vs PDF format is a runtime choice — no format hardcoded anywhere
- SHA-256 algorithm is non-negotiable (cryptographic standard)

---

## Feature 7 — pgvector Semantic RAG (Last)

**Goal:** Semantic similarity search over past investigations. "Has this happened before?" becomes a vector search over RCA embeddings, returning top-K similar incidents with similarity scores.

**Build this last** because it requires:
1. PostgreSQL with `pgvector` extension (not SQLite-compatible)
2. An embedding API call per investigation (adds latency + cost)
3. A DB migration to add `embedding` column

### Backend

**DB migration** (new Alembic migration):
```sql
-- Requires: CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE investigation_requests
  ADD COLUMN embedding vector(1536);  -- dimension matches text-embedding-3-small

CREATE INDEX ON investigation_requests
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**New service** `corvin/strategy/similarity_service.py`:
```python
class SimilarityService:
    def embed(self, text: str) -> list[float]: ...
    def index_investigation(self, result: InvestigationResult) -> None: ...
    def find_similar(self, query: str, k: int = 5) -> list[SimilarIncident]: ...
```

**Embedding model** — read from `config/models/llm.yaml`:
```yaml
embedding_model: "text-embedding-3-small"  # no hardcoded model names in source
```

**New endpoint**:
```
GET /investigations/similar?q=<text>&k=5&service_name=&environment=
Returns: list[SimilarIncident] with similarity_score, investigation_id, summary
```

**Fallback**: When `pgvector` is not available (SQLite or Postgres without extension), falls back to the existing `get_similar_incidents()` keyword search. Code detects this at startup — no crash, just logs a warning and disables the semantic path.

**Config** (`config/policies/investigation.yaml`):
```yaml
similarity:
  backend: pgvector          # pgvector | keyword (auto-detected if pgvector unavailable)
  embedding_model_config: "models/llm.yaml#embedding_model"
  top_k_default: 5
  min_similarity_threshold: 0.72
  index_on_completion: true  # embed + index each investigation when it completes
```

### Frontend

- Search bar on Investigations page: "🔍 Find similar incidents…"
- Results panel: similarity score badge (0–100%), service name, date, one-line RCA summary
- Clicking a result opens the full investigation detail

### No Hardcodes
- Embedding model name from `llm.yaml` — zero model strings in Python
- `top_k_default` and `min_similarity_threshold` from `investigation.yaml`
- pgvector vs keyword fallback is auto-detected, not configured by hand
- Vector dimension (1536) is derived from the model's output — validated at indexing time

---

## Cross-Cutting Rules for All Features

These apply to every feature above without exception:

| Rule | Enforcement |
|------|------------|
| No customer service names as examples | Use `payments-api`, `auth-service`, `order-service` in all docstrings |
| No `environment = "prod"` defaults | All API models require environment explicitly |
| No model names hardcoded | All model identifiers from `config/models/llm.yaml` |
| Feature flags in `investigation.yaml` | `debate_mode.enabled`, `heatmap.*`, `compliance_pack.enabled`, `similarity.backend` |
| Every new DB column has nullable + default | No migrations that break existing rows |
| Backward compat | Old investigations without new fields render graceful empty states |
| TypeScript types | All new API response shapes have corresponding `interface` in `client.ts` |
| No `any` in new TypeScript | Strict types for all new component props |

---

## Implementation Order Within Each Feature

For each feature, follow this order:
1. **DB schema** — Alembic migration first, models.py second
2. **Pydantic models** — contracts.py updates
3. **Service layer** — new strategy/service file
4. **API endpoint** — route handler with no logic (delegates to service)
5. **API client** — TypeScript `client.ts` additions
6. **Frontend component** — data-driven, no hardcoded content
7. **Page integration** — wire component into existing pages

---

*Created: 2026-06-04. Implement in order: 8 → 9 → 10 → 7.*
