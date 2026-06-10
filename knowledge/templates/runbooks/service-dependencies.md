---
template: service-dependencies
version: "1"
description: Upstream and downstream dependency map for a microservice
---

# <SERVICE_NAME> — Dependency Map

## Primary Data Store

| Property | Value |
|----------|-------|
| Type | `<Azure Cosmos DB / PostgreSQL / MySQL / Redis / Azure Table Storage>` |
| Account/Host | `<resource name or hostname>` |
| Database/Container | `<database or container name>` |
| Access pattern | `<read-write / read-only / write-heavy>` |
| Failure mode | `<What happens when this store is unavailable or throttled?>` |
| Throttling indicator | `<Log pattern or metric that indicates throttling, e.g. "429 TooManyRequests">` |

*Repeat this block for each data store if the service uses multiple.*

---

## Credential / Secret Store

| Property | Value |
|----------|-------|
| Type | `<Azure Key Vault / AWS Secrets Manager / HashiCorp Vault>` |
| Resource name | `<vault-name>` |
| Secrets managed | `<List: DB connection string, API keys, etc.>` |
| Failure mode | `<What happens when vault is unreachable? Does the service crash on startup? Does it use cached creds?>` |

---

## External Service Dependencies

| Service | Endpoint / Host | Protocol | Auth | Timeout | Failure mode |
|---------|----------------|----------|------|---------|-------------|
| `<Service Name>` | `<endpoint>` | `<HTTP / gRPC / AMQP>` | `<Bearer / mTLS / API Key>` | `<Ns>` | `<What fails when this is down?>` |

---

## Inter-Service Dependencies

| Calling Pattern | Called Service | Purpose | Failure Impact |
|----------------|---------------|---------|---------------|
| `<Synchronous HTTP>` | `<service-name>` | `<why>` | `<caller fails immediately / cached / degraded>` |

---

## Observability / Telemetry Sink

| Signal | Destination | Protocol |
|--------|------------|---------|
| Traces | `<OTLP endpoint / Azure Monitor>` | `<OTLP / HTTP>` |
| Metrics | `<Prometheus endpoint / OTLP>` | `<scrape / push>` |
| Logs | `<Elastic / Azure Monitor / stdout>` | `<Filebeat / agent / direct>` |

---

## Architecture Notes

- **Message queues:** `<None — synchronous HTTP only / Kafka topic X / Azure Service Bus queue Y>`
- **Caching:** `<None / Redis TTL Xs / In-memory with TTL Xs>`
- **Retry policy:** `<No retries / Exponential backoff up to N retries / Circuit breaker after N failures>`
- **Critical path:** `<Is this service on the critical path? Can users proceed if this service is slow?>`

---

## SRE Decision Guide

Use this to quickly identify the failing dependency during an incident:

| Symptom | Most Likely Cause | First Action |
|---------|------------------|-------------|
| `<HTTP 429 errors in logs>` | `<Data store throttling>` | `<Check RU/s consumption on Cosmos>` |
| `<"connection refused" errors>` | `<Downstream service not running>` | `<kubectl get pods -n <namespace>>` |
| `<Service startup fails with credential error>` | `<Key Vault unreachable or permission denied>` | `<Check managed identity assignment and Key Vault firewall>` |
| `<Add your known failure patterns here>` | | |
