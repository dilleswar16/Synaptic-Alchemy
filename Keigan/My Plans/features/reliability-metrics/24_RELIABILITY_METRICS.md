# 24 — Reliability metrics

Written 2026-11-21. Roadmap item A4 in `product/21_PRODUCT_RESEARCH.md` (section 3.5): show whether Keigan helps, with numbers a team can check. Status: built, verified by tests and screenshots, not yet committed.

## What it does

A page at `/metrics` (sidebar, Reliability section, next to SLO monitoring and Intelligence) shows, for the applications the signed-in person can read:

- incidents opened and resolved, by priority;
- four durations: time to detect, time to first update, time to resolve (MTTR) and time to conclusion;
- investigations by status, and how many were rated correct, partially correct or incorrect;
- AI usage: tokens per investigation, latency per model call, failed calls and, when prices are configured, an estimated cost;
- a weekly trend and one row per application;
- a "Definitions" section that states each rule below in the page's own words.

The person picks one application or all, and a period of 7, 30 or 90 days (the API accepts any period up to the maximum below).

## Rules (the definitions the page shows)

| Figure | Start | End | Which items count |
|---|---|---|---|
| Time to detect | earliest alert `first_seen_at` in an alert group linked to the incident | incident `opened_at` | incidents opened in the period. An incident with no linked alert, or whose first alert came after it opened, is left out and counted as "left out: no alert" |
| Time to first update | `detected_by_keigan_at` | `first_update_sent_at` | incidents whose first update was sent in the period |
| Time to resolve (MTTR) | `opened_at` | `resolved_at` | incidents resolved in the period; unresolved ones are not included |
| Time to conclusion | investigation `started_at` | `completed_at` | completed investigations (`completed` or `completed_evidence_only`) that finished in the period |
| Share correct | | | correct divided by rated investigations (created in the period). Withheld below the minimum sample: the page says "not enough ratings yet" |

- A duration counts in the period in which it ended; opened incidents are counted by `opened_at`, resolved ones by `resolved_at`.
- Median and p90 use linear interpolation between ranks, rounded to one decimal. The API also returns the mean. Every figure carries its sample size `n`. A figure that cannot be computed is `null`, never zero.
- A pair that cannot give a duration (no start, no end, or an end before the start) is not a sample; it is counted in `excludedCount`.
- AI usage covers model calls made for investigations created in the period. Calls with no investigation (for example the global chat) are not part of this page. Tokens are summed per investigation, latency is per call, a failed call is one whose `outcome_status` is `failed` (`LlmCallOutcome` in `entities/status_values.py`).
- Cost needs an exact model-name match in `LLM_MODEL_PRICES_JSON`. An investigation that used any model without a price is left out of the per-investigation cost, and the page names those models and how many investigations were left out, so the figure never quietly understates. With no prices configured the page shows tokens only and says so.
- The weekly trend starts each week on Monday 00:00 UTC. The first and last week of a period may be only partly inside it.
- **Time to acknowledge (MTTA) is not available.** No acknowledgement timestamp exists in the data, so the page shows "Not available" with the reason and does not estimate. No column was added for it.

## Where the code is

| Part | Path |
|---|---|
| Maths (pure functions: percentiles, durations, ratings, cost, weeks, period) | `backend/keigan/services/reliability_metrics.py` |
| Reads the rows and builds the answer | `backend/keigan/services/reliability_metrics_service.py` |
| Response shapes | `backend/keigan/dtos/metrics_dtos.py` |
| Endpoint | `backend/keigan/controllers/metrics_controller.py`: `GET /api/metrics/overview` |
| Enum for call outcomes | `LlmCallOutcome` in `backend/keigan/entities/status_values.py` |
| Settings | `backend/keigan/config/settings.py` (`ModelPrice`, `parse_model_prices`, `llm_model_prices`) |
| API client | `frontend/src/api/metricsApi.ts` |
| Page and parts | `frontend/src/features/metrics/pages/ReliabilityMetricsPage.tsx`, `components/MetricParts.tsx` |
| Route and sidebar | `frontend/src/app/routes.tsx` (`/metrics`), `frontend/src/components/layout/navigationItems.ts` |
| Text | i18n namespace `metrics` in `frontend/src/i18n/locales/<locale>/metrics.json` |
| Tests | `backend/tests/unit/services/test_reliability_metrics.py`, `tests/unit/config/test_metrics_settings.py`, `tests/integration/controllers/test_metrics_controller.py` |

Endpoint parameters: `applicationId` (optional; the caller must be able to read it), `days`, or `from` and `to`. `days` cannot be combined with `from`/`to`, `to` needs `from`, and a period longer than the maximum is a 422. With nothing given the period is the last 30 days. Without `applicationId` the answer covers every application the caller can read; the response also has one block per application (`applications`).

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `METRICS_MINIMUM_RATING_SAMPLE` | 5 | Fewest rated investigations before a "share correct" percentage is shown |
| `METRICS_MAXIMUM_WINDOW_DAYS` | 365 | Longest period one request may ask for |
| `LLM_MODEL_PRICES_JSON` | empty | Per-model prices: `{"model-name": {"input_per_million": 1.25, "output_per_million": 10}}`. Invalid JSON stops Keigan at startup. Currency is whatever the operator chose; Keigan only multiplies |

This is separate from `LLM_PRICE_PER_MILLION_INPUT_TOKENS` and `LLM_PRICE_PER_MILLION_OUTPUT_TOKENS`, which the administration usage page uses for one flat price.

## Demo data

The demo seed is unchanged. `backend/scripts/demo_data_sql/demo_data_plan.py` excludes `llm_usage_record` on purpose (demo rows would distort usage reporting and budgets), so on a fresh seed the AI section shows "no data". The seeded incidents have no linked alerts, so time to detect shows "left out: no alert". Both are the honest answer for that data, not a defect.

## What is not verified

- The numbers against a real installation: the tests use seeded and constructed rows, not production history.
- The translations (en, es, fr, ja, nl, zh-CN) were not read by native speakers. `es-MX` has an empty `metrics.json` by design and falls back to `es`.
- Cost with a real provider's model names: the exact-match rule depends on the name the provider returns in the usage record.

## Deliberately left out

- MTTA (see above).
- A weekly digest or export of these figures, which the roadmap mentioned for A4.
- Any outcome other than `failed` in the failure count (for example `blocked_by_budget` is not counted as a failed call), and calls that belong to no investigation.
- Any comparison against a target or another team: the page reports figures and sample sizes, it does not score them.
