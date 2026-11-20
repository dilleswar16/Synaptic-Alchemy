---
prompt_key: knowledge_capture_prompt
version: 3
model_tier: none
---
You are GitHub Copilot working inside the repository for {{ scope_description }}.
Your job is to write ONE Markdown file named `keigan-knowledge-{{ file_slug }}.md` that teaches an on-call SRE how this system works.
An AI assistant called Keigan will read the file during live production incidents, so accuracy matters more than length.

## How to work
1. Read the whole repository before writing: source code, `pom.xml` / `build.gradle` / `package.json` / `*.csproj`, configuration files (`application*.yml`, `appsettings*.json`, `.env.example`),
   Helm charts and Kubernetes manifests, Dockerfiles, pipeline definitions (`azure-pipelines*.yml`, `.github/workflows`), Terraform / Bicep / ARM templates, and existing README files.
2. Write only what you can confirm from the repository. If something is not in the repository, write `Not identified in the repository`. Never guess.
3. Name real files, classes, methods, queues, tables and endpoints, with relative paths (for example `src/main/java/.../ClaimsController.java`).
4. Do not include secrets, passwords, connection strings, tokens, personal data or customer data. Write `<redacted>` where a value would appear.
5. Keep the file under 600 lines. Use the exact headings below, in this order, with the same wording.

## Required headings (use `##` for each)

## Purpose
What the system does for the business in three sentences, who calls it and who depends on it.

## Runtime and hosting
Language and framework with versions, how it is hosted (AKS namespace and deployment names, App Service, Function App, Logic App, VM, mainframe region), replica counts, resource requests and limits, health probes, scaling rules.

## Entry points and APIs
Table of HTTP endpoints, message consumers, scheduled jobs and batch entry points: method, path or topic, handler class, authentication, typical caller.

## Sequence diagrams
Two to four Mermaid `sequenceDiagram` blocks for the most important flows, including the main success path and the main failure or retry path.

## Class / module overview
The main packages or modules and what each is responsible for. Call out the classes that an engineer would open first during an incident.

## Data stores
Every database, cache, blob container, queue and topic: technology, name, what is stored, connection pool settings (pool size, timeout), transaction handling, migrations.

## Outbound dependencies
Every system this code calls: name, protocol, base URL setting name, timeouts, retry policy, circuit breaker, fallback behaviour. Present as a table.

## Configuration and feature flags
Important settings and feature flags, where they are defined (file, key vault name, config map), default values and what changes when they are altered. Never print secret values.

## Deployment route
Pipeline to environments to clusters or namespaces: pipeline file, stages, approvals, Helm release names, image registry, how to roll back.

## Logging and telemetry
Log format and the fields that exist (for example `traceId`, `correlationId`, `customerId`), logger names, Application Insights role name, custom metrics and events, tables or indexes to query, and example queries that find errors for this system.

## Known failure modes
For each failure mode seen in code comments, TODOs, retry logic, issues or incident notes: symptom, likely cause, how to confirm it in logs or metrics, and the mitigation.

## Operational commands
Safe, read-only diagnostic commands first (kubectl, az, SQL, curl), then recovery commands (restart, scale, rollback, replay) with their risks. This section is written for people. Keigan shows it to responders and never copies a command from it into an automated action, so state for each recovery command when it must not be used.

## Owners
Team, repository owners (from CODEOWNERS or the README), support channel, escalation contact, ServiceNow assignment group when known.

## Style rules
- Write in plain English, short sentences, present tense.
- Prefer tables and bullet lists over paragraphs. One fact per bullet.
- Put units on every number (milliseconds, seconds, MB, replicas).
- Quote exact names: queue names, table names, log message fragments, exception classes and metric names, so they can be searched.
- For every claim about behaviour under failure (timeouts, retries, pool exhaustion, back-pressure), cite the file and the setting that causes it.
- Mention anything that changes behaviour per environment (dev, test, uat, prod).
- If the repository contains several deployable services, describe each in its own `###` sub-section under the relevant heading.
- If you find contradictions between code and documentation, trust the code and note the contradiction under `Known failure modes`.
- Mark anything that looks outdated with `(possibly outdated)`.
- Do not summarise the headings back to me; produce the Markdown file content only.

## Quality check before you finish
- Every required heading is present, spelled exactly as above, and in the same order.
- Every Mermaid block renders (balanced participants and arrows).
- No secret values, tokens, e-mail addresses of customers, or personal data appear anywhere.
- All paths are relative to the repository root.

## Finish
After the file is written, list at the end of your reply the three things you could not determine from the repository. Do not commit the file; the team will upload it to Keigan.
