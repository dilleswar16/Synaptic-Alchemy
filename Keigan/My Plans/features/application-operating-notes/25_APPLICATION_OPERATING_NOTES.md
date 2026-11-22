# 25 — Application operating notes

Written 2026-11-21. Roadmap item B2 in `product/21_PRODUCT_RESEARCH.md` (section 3.5): a short text per application that the team writes for the AI. Status: built, verified by tests and screenshots, not yet committed.

## What it does

An application's team can write a few paragraphs that Keigan's AI reads in every investigation and investigation chat for that application: which services carry revenue or regulated traffic, which alerts are usually noise, what a quiet night looks like. It tells the AI what telemetry cannot.

The notes are **guidance, not evidence.** The AI may use them to decide what matters and how to word an explanation. It may not cite them, and every claim still needs real evidence. If the evidence contradicts a note, the prompts tell the model to trust the evidence and say so. The notes change no alert rule, noise policy or incident priority.

## Rules

| Area | Rule |
|---|---|
| Storage | Three nullable columns on `application` (below). No backfill: existing applications have no notes |
| Who | Readers of the application can read; Keigan admins and the application's admin group can edit (`require_application_reader`, `require_application_admin`) |
| Text | Trimmed; `\r\n` and `\r` are stored as `\n`, so the length matches what a browser text box counts. Length is counted in characters (code points) after trimming |
| Limit | `APPLICATION_OPERATING_NOTES_MAXIMUM_CHARACTERS`, default 4000, allowed 100 to 20000. Over the limit: 422 with a field error on `text` that gives the maximum and the actual length |
| Clearing | An empty text clears the notes (the column is set to null) |
| Audit | Event `application.operating_notes_update` records who, plus the previous and new length. It keeps no text. A save that changes nothing writes nothing (no audit event, no new "last edited" stamp) |
| Prompts | See below |

## How the notes reach the AI

`build_operating_notes_section(notes_text, masker)` in `backend/keigan/ai/operating_notes_prompt.py` returns a `PromptSection`, or `None` when there are no notes:

- **Untrusted.** The section is marked `is_untrusted`, so it is spotlighted like uploaded knowledge and never treated as instructions.
- **Masked** with the same `PiiMasker` as the rest of the run (in chat, the same masker as the question and history, so a person keeps one placeholder).
- **Checked** with `assess_prompt_injection`. A flagged text carries `is_flagged` (a warning on its block). When the flagged-document policy (`ai_flagged_document_policy`) is `exclude`, a flagged text is left out of the prompt.
- **No citation code.** It never enters the set of valid citation codes, so no citation can validly point to it.
- Title: "Operating notes from the application team (guidance, not evidence)". The prompts name the section by this title.

Where it is used: the three hypothesis calls and `rca_synthesis` (the graph reads it once in the context step, `investigation_graph.py`), and the investigation chat (`investigation_chat_service.py`: a spotlighted block in the agent path, a section in the plain fallback path). Other flows (triage, communications, postmortem, the global chat) do not receive it.

Prompt files changed from version 2 to version 3: `hypothesis_application`, `hypothesis_dependencies`, `hypothesis_infrastructure` (all three through the shared `_hypothesis_body.md`), `rca_synthesis` and `investigation_chat`. Each now describes the section and says it is guidance, never evidence, and must never be cited.

## Schema

Alembic revision `f1b9d3a5c7e2` (down revision `e4c8a1d7b2f6`) adds to `application`:

| Column | Type |
|---|---|
| `operating_notes_text` | `Text` (NVARCHAR(max) on Azure SQL) |
| `operating_notes_updated_at` | UTC datetime, nullable |
| `operating_notes_updated_by_user_principal_name` | VARCHAR(320), nullable |

Azure SQL: `database/azure_sql/migrations/f1b9d3a5c7e2_application_operating_notes.sql`; scripts 01 to 06 were regenerated.

## Endpoints

`GET /api/applications/{id}/operating-notes` and `PUT /api/applications/{id}/operating-notes` (body `{ "text": "..." }`). Both return `{ text, maximumCharacters, updatedAt, updatedBy }`. Code: `controllers/operating_notes_controller.py`, `services/operating_notes_service.py`, `dtos/operating_notes_dtos.py`.

## Screen

The first section of the Knowledge step in application setup (`frontend/src/features/applications/components/OperatingNotesSection.tsx`, used by `steps/KnowledgeStep.tsx`): a text box with a live counter ("used of maximum characters"), helper text that says what to write and that it is guidance and not for passwords or personal data, last edited by and when, a message when over the limit with Save disabled, a read-only mode for people who cannot edit, and a guard that asks before leaving with unsaved text (tab close, reload and moving to another step). API client: `useOperatingNotes` and `useSaveOperatingNotes` in `frontend/src/api/applicationsApi.ts`. Text: `operatingNotes` in the `applications` namespace.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `APPLICATION_OPERATING_NOTES_MAXIMUM_CHARACTERS` | 4000 | Longest notes, counted after trimming; allowed 100 to 20000 (20000 is also the default length one prompt section keeps) |

## Tests

`backend/tests/unit/ai/test_operating_notes_prompt.py`, `tests/integration/ai/test_investigation_operating_notes.py`, `tests/integration/services/test_operating_notes_service.py`, `tests/integration/controllers/test_operating_notes_controller.py`, `tests/integration/migrations/test_operating_notes_migration.py`, `tests/unit/config/test_operating_notes_settings.py`, plus the demo seed test.

## Demo data

The demo seed (`keigan/seed/foundation_seed.py`, generated into `database/azure_sql/demo_data/`) gives Claims Processing (JP) and Channel APIs for Digital (AU) a note each.

## What is not verified

- Behaviour with a real model. The tests use a scripted model, so they prove what is sent and how citations are handled, not how a real model weighs the notes.
- The translations, which were not read by native speakers.

## Deliberately left out

- No version history of the text: the audit event keeps lengths only, so an earlier text cannot be recovered.
- No effect on alert rules, noise policy or priority. A note such as "this alert is usually noise" informs an explanation; it does not mute anything.
- No notes per service, and no approval step: the application admins own the text.
- Not sent to triage, communications, postmortem or the global chat.
