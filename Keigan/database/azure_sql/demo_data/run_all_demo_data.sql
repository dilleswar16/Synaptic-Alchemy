-- Runs the committed demo data steps in order. DEMO DATA ONLY: never run this on a production database.
--   sqlcmd -S <server>.database.windows.net -d <database> --authentication-method ActiveDirectoryDefault -b -f 65001 -v ConfirmDemoData=yes -i run_all_demo_data.sql
-- Run it from this folder (sqlcmd resolves :r paths from the current directory). Never include it from ../run_all.sql.
:on error exit
:r 01_applications_and_topology.sql
:r 02_knowledge.sql
:r 03_alerts_and_slos.sql
-- 04_sli_measurements.sql is generated on demand and optional: see README.md
:r 05_incidents_and_investigations.sql
:r 06_intelligence_and_collaboration.sql
