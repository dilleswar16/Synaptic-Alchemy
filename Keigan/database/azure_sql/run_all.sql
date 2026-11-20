-- Runs every step in order. Run from this folder (sqlcmd resolves :r paths from the current directory):
--   sqlcmd -S <server>.database.windows.net -d <database> --authentication-method ActiveDirectoryDefault -b -i run_all.sql -v KeiganIdentityName=id-keigan-prod
-- -b stops at the first error. Every step is idempotent, so a fixed re-run is safe.
:on error exit
:r 01_create_schema.sql
:r 02_create_tables.sql
:r 03_create_foreign_keys.sql
:r 04_create_indexes.sql
:r 05_reference_data.sql
:r 06_grant_keigan_identity.sql
