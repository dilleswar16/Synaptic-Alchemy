# Keigan demo data scripts (non-production only)

These scripts load the same demo world that `python -m keigan.seed_main` creates on SQLite: 5 applications (CLMJP, CHAD, PAYAU, PADMF, BENSA)
with services, knowledge, alerts, SLOs, incidents, investigations and reports. They exist so that **every row Keigan seeds for trying things
is also written as reviewed SQL**, and so the DBA can load or remove it on a non-production Azure SQL database.

**Production must never receive demo data.** Nothing here is part of `../run_all.sql` (a test fails if it ever is), every script refuses to run
unless you pass `-v ConfirmDemoData=yes`, and the data is only useful with `TELEMETRY_MODE=simulated` style settings (the sample hosts are
`*.example`). Production databases are created empty and filled through the Keigan UI.

## What is in this folder

| Order | File | What it holds |
|---|---|---|
| 1 | `01_applications_and_topology.sql` | Applications, components, services, dependencies, log sources, assignment groups, stakeholders |
| 2 | `02_knowledge.sql` | Knowledge documents and chunks, runbooks, topologies and review comments, record links, integrations |
| 3 | `03_alerts_and_slos.sql` | Alert sources, noise policies, maintenance window, mute rule, historical alerts and decisions, SLIs and SLOs |
| 4 | `04_sli_measurements.sql` | 30 days of SLI measurements (about 82,000 rows, 10 MB). **Not committed**; see "Step 4" below |
| 5 | `05_incidents_and_investigations.sql` | Incidents, communications, investigations, hypotheses, evidence, timelines, postmortems, alert groups (they point at incidents and investigations, so they load here) |
| 6 | `06_intelligence_and_collaboration.sql` | Predictive signals, intelligence reports, incident chat, notification history, simulation settings |
| runner | `run_all_demo_data.sql` | Runs the committed steps (1, 2, 3, 5, 6) in order with `:r`. Never include it from `run_all.sql` |
| removal | `99_remove_demo_data.sql` | Deletes the demo rows again (see "Remove demo data") |
| record | `MANIFEST.json` | Per file: row count per table and SHA-256. Also lists excluded tables |

Table order inside a file comes from the foreign keys of the entities, so a parent row is always inserted before its children.
The files are generated; never edit them by hand.

## Run them

Prerequisite: the database was created with steps 1 to 6 of `../README.md` (or has all migrations applied).

```bash
cd database/azure_sql/demo_data
az login   # as a user who may write to schema keigan
sqlcmd -S <server>.database.windows.net -d <database> \
       --authentication-method ActiveDirectoryDefault -b -f 65001 \
       -v ConfirmDemoData=yes -i run_all_demo_data.sql
```

- `-b` stops at the first error; `:on error exit` in every file does the same. Every statement is idempotent, so after a fix just run it again.
- `-f 65001` makes sqlcmd read the files as UTF-8, which the Japanese text needs. The files are UTF-8 without a byte order mark.
- Run from this folder (sqlcmd resolves `:r` paths from the current directory).
- Idempotent means: each row is checked individually against its key and inserted only if missing, so a run that stopped half way is completed
  and a second run changes nothing. It never updates or deletes a row that exists.

### Step 4: SLI measurements (optional, generated on demand)

`04_sli_measurements.sql` is too big to commit. Two choices:

1. **Skip it** (default). Without history the SLO pages start nearly empty. Keigan's collector (`collect_sli_measurements`) then records new
   5-minute measurements itself, but it only goes back at most 24 hours per run, and the 30-day catch-up (`backfill_sli`) is only queued
   when an SLI is created or accepted in the UI or API, not for SLIs loaded by SQL.
2. **Generate and run it.** From `backend/`: `.\.venv\Scripts\python.exe scripts\generate_demo_data_sql.py` (about a minute; it rewrites this folder
   and leaves `04_sli_measurements.sql` ignored by git), then run it after step 3:
   `sqlcmd ... -b -f 65001 -v ConfirmDemoData=yes -i 04_sli_measurements.sql`.
   Order against steps 5 and 6 does not matter. It does not insert the generated ids; SQL Server assigns them, and a row is matched by SLI and window start.
   The history is thinned for size: the newest two days keep every 5-minute window (what the 1-hour and 6-hour burn rates and the dashboard read),
   and each older hour is one row with the good and total counts summed, so error budgets and burn rates match the full history. The measured value is
   left empty on those hourly rows. Without thinning the file would hold 424,512 rows (53 MB).

`MANIFEST.json` records the row count and SHA-256 of this file. After you generate it, compare: `(Get-FileHash 04_sli_measurements.sql).Hash`
must equal the `sha256` listed there (case does not matter).

## Remove demo data

```bash
sqlcmd -S <server>.database.windows.net -d <database> \
       --authentication-method ActiveDirectoryDefault -b -f 65001 \
       -v ConfirmDemoData=yes -i 99_remove_demo_data.sql
```

- Deletes only the demo rows, by primary key, children before parents, all in one transaction that rolls back on any error. A second run deletes nothing.
- It never touches other rows, `keigan.alembic_version` or the schema marker row in `platform_setting`. There is no `DELETE` without a `WHERE`.
- Measurements have no stable key, so they are removed by SLI id (the short list of demo SLI ids), not by row. Every measurement of a demo SLI goes, also ones
  the collector added later.
- It fails (and rolls back) if someone created real rows that point at demo rows. Remove or move those first.

## What is NOT demo data (excluded tables)

Runtime and secret state is never generated, even though the seed writes some of it. The list lives in one place,
`backend/scripts/demo_data_sql/demo_data_plan.py` (`EXCLUDED_TABLE_REASONS`), and `MANIFEST.json` shows how many rows the seed wrote into each.

| Table | Why it is excluded |
|---|---|
| `background_job` | Job queue rows are picked up and run by the workers (for example a queued simulate_alerts_for_scenario); seeded jobs would run in Azure. |
| `stored_secret` | Holds secret values; secrets are created through the Keigan UI or Key Vault, never from a script in the repository. |
| `platform_user` | Real people sign in and are created on first sign-in; a seeded identity row could grant or block access to a real person. |
| `llm_usage_record` | Records of real model calls and their cost; demo rows would distort usage reporting and budgets. |
| `audit_event` | The audit trail is append-only evidence of what really happened; seeded or deleted audit rows would make it untrustworthy. |

## Demo values are not secrets

The seed uses a fixed random sequence so that regenerating gives identical files. Consequently the SHA-256 hashes in `alert_source.webhook_secret_hash`
and every other generated token or identifier are **public and reproducible: demo values, not secrets**. Never reuse them for a real webhook or
credential. Delete the demo alert sources (run the removal script) before pointing a real alert tool at the database. No secret store entries and no
plaintext secrets are in these files (`stored_secret` is excluded).

## Timestamps are fixed

The demo world's "now" is **2026-11-20 12:00 UTC** (shown in every file header), so the generated files do not change from day to day.
Dashboards that look at "the last 30 days" will therefore look old when loaded much later. To refresh, change `REFERENCE_TIME` in
`backend/scripts/generate_demo_data_sql.py` and regenerate.

## Regenerate (developers)

From `backend/`:

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_data_sql.py              # writes ../database/azure_sql/demo_data
.\.venv\Scripts\python.exe scripts\generate_demo_data_sql.py <folder> <schema>
```

The generator runs the seed in a throw-away SQLite database under a fixed clock, fixed identifiers and a fixed random sequence
(`keigan/seed/deterministic_seed_environment.py`), reads every row back, and writes T-SQL. Columns, keys and order come from the entities, so a schema
change flows through; a new table that holds seeded rows must be assigned to a file (or excluded with a reason) in `demo_data_plan.py`, otherwise the
generator stops and names the table.

Tests (`backend/tests/integration/seed/test_generate_demo_data_sql.py`, `backend/tests/unit/scripts/`) fail when the seed changes and these files were not regenerated.

### What the tests do not prove

T-SQL cannot run on SQLite and there is no real Azure SQL in the test environment, so **no generated statement has been executed against SQL Server**.
The tests check the text (order, per-row guards, exclusions, hashes). The first run on a non-production database is the real check; report any error to the developers.
