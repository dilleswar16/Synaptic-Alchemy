# Database Migrations (Alembic)

Corvin uses **SQLAlchemy** for its ORM models and **Alembic** to manage schema migrations for the Postgres database. 

Whenever you modify a file in `corvin/storage/models.py` (such as adding new columns or tables), you must run Alembic to synchronize the actual Postgres database schema with the Python code.

This guide provides the step-by-step process for generating and applying migrations.

---

## Prerequisites

Before running any Alembic commands, ensure that:
1. Your Python virtual environment is activated.
2. Your `.env` file is present in the root directory and contains valid `CORVIN_DB_*` credentials. Alembic must be able to connect to the live Postgres database to compare the schema.

```powershell
# Activate your virtual environment
.\.venv\Scripts\Activate.ps1
```

---

## Step 1: Generate the Migration Blueprint

When you have modified `corvin/storage/models.py`, run the `revision --autogenerate` command. 

```powershell
alembic revision --autogenerate -m "Enter a short description here"
```

**What this does:**
1. Alembic connects to Postgres and inspects the current tables.
2. It compares the tables against the Python classes in `models.py`.
3. It generates a new Python migration script inside the `alembic/versions/` folder containing the exact `CREATE` or `ALTER TABLE` statements required.

> [!WARNING]
> **Do not skip this step!** The database is not actually modified yet. Always open the newly generated file in `alembic/versions/` and manually review the `upgrade()` and `downgrade()` functions to ensure Alembic guessed your changes correctly.

---

## Step 2: Apply the Migration

Once you have verified the blueprint script, you apply it to the database using the `upgrade` command.

```powershell
alembic upgrade head
```

**What this does:**
1. Alembic executes the SQL commands in your new migration script against the Postgres database.
2. It records the migration ID in the `alembic_version` table so it won't run it again.

> [!TIP]
> **Rollbacks:** If you make a mistake and need to undo the last migration you applied, you can run `alembic downgrade -1`.

---

## Summary of Commands

| Action | Command |
| :--- | :--- |
| **Check current DB status** | `alembic current` |
| **Auto-generate a new migration** | `alembic revision --autogenerate -m "description"` |
| **Apply all pending migrations** | `alembic upgrade head` |
| **Undo the last migration** | `alembic downgrade -1` |
