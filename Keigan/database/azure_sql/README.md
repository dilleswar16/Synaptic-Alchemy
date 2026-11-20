# Keigan — Azure SQL database scripts

Run these once on an empty Azure SQL database **before** the first Helm install of Keigan.
They create the `keigan` schema, 47 tables, 32 foreign keys, 62 indexes, the migration baseline and a
database user for Keigan's managed identity. Keigan stores no demo data in Azure: applications, users' access
and everything else are created through the Keigan UI.

| Order | File | What it does |
|---|---|---|
| 1 | `01_create_schema.sql` | Creates schema `keigan` |
| 2 | `02_create_tables.sql` | Creates every table with its primary key and unique constraints |
| 3 | `03_create_foreign_keys.sql` | Adds foreign keys (after all tables exist, so order never matters) |
| 4 | `04_create_indexes.sql` | Adds indexes, including the filtered unique index on ServiceNow incident numbers |
| 5 | `05_reference_data.sql` | Creates `keigan.alembic_version` = `94692c828bd3` (so later releases apply only newer migrations) and a schema marker row |
| 6 | `06_grant_keigan_identity.sql` | Creates the database user for Keigan's managed identity and grants read/write on schema `keigan` |
| — | `run_all.sql` | Runs 1–6 in order with `sqlcmd` |

Every script is idempotent: it checks `sys.schemas`, `sys.tables`, `sys.foreign_keys`, `sys.indexes` and
`sys.database_principals` first, so running it twice changes nothing.

## Before you run them

1. The SQL server has a **Microsoft Entra admin** (a person or group). You run the scripts signed in as that admin,
   because only an Entra principal can run `CREATE USER … FROM EXTERNAL PROVIDER` in step 6.
2. Keigan's **user-assigned managed identity** exists (for example `id-keigan-prod`) — the same identity the AKS
   workload identity is federated with.
3. Install the current `sqlcmd` (Go version: `winget install sqlcmd`), or use SSMS / Azure Data Studio.

## Run everything with sqlcmd

From this folder (`sqlcmd` resolves the `:r` file paths from the current directory):

```bash
az login   # as the SQL server's Entra admin
sqlcmd -S <server>.database.windows.net -d <database> \
       --authentication-method ActiveDirectoryDefault -b \
       -i run_all.sql -v KeiganIdentityName=id-keigan-prod
```

`-b` stops at the first error. With SSMS or Azure Data Studio, open each file in order, turn on
**Query → SQLCMD Mode**, and in `06_grant_keigan_identity.sql` uncomment the `:setvar KeiganIdentityName …` line.

## Check the result

```sql
SELECT COUNT(*) AS table_count FROM sys.tables WHERE schema_id = SCHEMA_ID(N'keigan');   -- 48 (47 + alembic_version)
SELECT version_num FROM keigan.alembic_version;                                          -- 94692c828bd3
SELECT name, type_desc FROM sys.database_principals WHERE name = N'id-keigan-prod';     -- EXTERNAL_USER
```

## Backend settings that go with these scripts

Already in `deploy/helm/keigan/values.yaml`:

| Setting | Value | Why |
|---|---|---|
| `DATABASE_URL` (Key Vault secret `keigan-database-url`) | `mssql+aioodbc://@<server>.database.windows.net:1433/<database>?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no` | No password in it |
| `DATABASE_SCHEMA` | `keigan` | Tables live in schema `keigan`, not `dbo` |
| `DATABASE_AUTHENTICATION` | `managed_identity` | Keigan signs in to SQL with an Entra token of its managed identity |
| `AUTO_CREATE_SCHEMA` | `false` | These scripts own the tables; Keigan never creates them at start-up |

The backend image already contains Microsoft ODBC Driver 18 and `aioodbc` (`deploy/docker/backend.Dockerfile`).

## Future schema changes

Two options; pick one per environment:

- **Keigan applies them (default).** The Helm pre-upgrade job runs `alembic upgrade head`. Uncomment the three
  optional `GRANT` lines at the end of `06_grant_keigan_identity.sql` so the identity may alter tables.
- **DBAs apply them.** Set `databaseMigration.enabled: false` in the Helm values. For each release, review the SQL of
  the new migrations with `alembic upgrade <old>:<new> --sql` (from `backend/`) and run it.

## Regenerating these files

The scripts are generated from the backend entities, which are the single source of truth. After changing an entity
(and adding its Alembic migration), run from `backend/`:

```powershell
.\.venv\Scripts\python.exe scripts\generate_azure_sql_ddl.py            # writes ../database/azure_sql
.\.venv\Scripts\python.exe scripts\generate_azure_sql_ddl.py <folder> <schema>   # other folder or schema name
```

## SQL Server rules the entities follow

- Text is `NVARCHAR(n)` / `NVARCHAR(max)` (Japanese and Chinese text needs Unicode); times are `DATETIME2(6)` in UTC.
- SQL Server allows only one cascade path to a table. Where a second path would exist (for example
  `investigation → incident`), the foreign key is `NO ACTION` and Keigan deletes those rows itself before deleting
  the application.
- A unique constraint in SQL Server treats NULLs as equal, so "ServiceNow number unique per application" is a filtered
  unique index (`WHERE external_incident_number IS NOT NULL`).
- Constraint and index names follow one convention (`pk_`, `fk_`, `uq_`, `ix_` + table + columns), so migrations can
  find and change them by name.
