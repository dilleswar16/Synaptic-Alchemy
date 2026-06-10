# Corvin — Knowledge Template Library

This directory contains reusable templates for documenting applications in Corvin.

When you onboard a new application, create runbooks for each service using these templates. Well-populated runbooks dramatically improve RCA quality — Corvin's LLM uses them to understand your specific architecture, known failure patterns, and service dependencies.

---

## Template Index

### Runbook Templates

| Template | Purpose | When to use |
|----------|---------|-------------|
| [service-topology.md](runbooks/service-topology.md) | Document AKS deployment topology | All AKS-deployed services |
| [service-inventory.md](runbooks/service-inventory.md) | Document service technical profile | All microservices |
| [service-dependencies.md](runbooks/service-dependencies.md) | Document upstream/downstream dependencies | All services with external dependencies |
| [service-api-spec.md](runbooks/service-api-spec.md) | Document API surface and APIM config | All API-exposed services |
| [service-known-errors.md](runbooks/service-known-errors.md) | Document known exception types and error codes | Java/Spring Boot services and APIM-fronted services |
| [service-security-context.md](runbooks/service-security-context.md) | Document auth patterns and identity configuration | All Azure-authenticated services |

### APIM Templates

| Template | Purpose |
|----------|---------|
| [apim-policy-summary.md](apim/apim-policy-summary.md) | Document your APIM policy configuration |
| [apim-error-reference.md](apim/apim-error-reference.md) | Generic Azure APIM error code reference (no customization needed) |

---

## How to Use These Templates

1. Copy the template to `knowledge/runbooks/your-service-name.md`
2. Replace every `<PLACEHOLDER>` and `<...>` value with your actual values
3. Remove sections that don't apply to your service (e.g. if not using APIM, remove the APIM section)
4. Register the runbook in `knowledge/runbooks/catalog.json`
5. Or — upload it through the Corvin UI under **Runbook Management**

## Worked Example

The `knowledge/examples/chad/` directory contains a complete, filled-in example of all these templates for the MetLife CHAD platform (a Java Spring Boot / Azure APIM / AKS application). Use it as a reference when you are unsure what level of detail to provide.

---

## Tips for High-Quality Runbooks

- **Be specific about failure modes.** Don't write "service may fail" — write "when Cosmos DB throttles, you will see `429 TooManyRequests` in logs with `x-ms-request-charge` exceeding provisioned RU/s."
- **Include the SRE decision guide.** The most valuable section is "how do I know which component is at fault?" HTTP 401 from APIM means token issue; HTTP 403 with `IP_NOT_ALLOWED` means APIM allowlist, not service code.
- **Document dependencies explicitly.** List every upstream service, database, cache, and message queue. State the failure mode for each ("if Cosmos DB is unavailable, all write operations fail; reads from cache still work for up to 60s").
- **List known exceptions by class.** For Java services, list the exception classes and their HTTP status codes. Corvin uses this to differentiate infrastructure failures from application bugs.
