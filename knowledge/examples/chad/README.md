# Worked Example: MetLife CHAD Platform

This directory contains a complete, real-world example of Corvin configured for a **Java Spring Boot microservices platform running on Azure AKS** behind Azure API Management.

## What CHAD Is

CHAD ("Channels And Data") was the original development application used to build and validate Corvin. It is a MetLife Australia financial services platform with three microservices:

- **fundapis** — Fund API service. Handles fund data, member profiles, and scheme operations via a REST API backed by Azure Cosmos DB.
- **fundsso** — Fund SSO service. Handles single sign-on for fund portals via PingFederate integration.
- **partnerapis** — Partner API service. Handles partner-facing APIs for third-party integrations.

The platform routes through Azure APIM, runs on AKS with Istio, uses Azure Workload Identity for secretless credential access, and emits telemetry via the OTEL Java Agent.

## Why This Is Here

CHAD represents the most complete example of Corvin in production use. The runbooks in this directory show exactly what a fully-populated Corvin knowledge base looks like for a Java/AKS/APIM deployment.

Use this directory as a reference when:
- Creating runbooks for a new Java Spring Boot application
- Understanding what level of detail makes runbooks useful for Corvin's LLM
- Evaluating how Corvin performs on a real architecture

## Contents

| File | Purpose |
|------|---------|
| `runbooks/chad-service-topology.md` | AKS namespace, deployments, HPAs, Istio, telemetry |
| `runbooks/chad-service-inventory.md` | Maven artifacts, Spring Boot classes, inter-service dependencies |
| `runbooks/chad-security-context.md` | Auth architecture, Workload Identity, Key Vault, SRE error guide |
| `runbooks/chad-api-spec.md` | APIM policies, endpoint specs, known failure modes |
| `runbooks/chad-known-errors.md` | Java exception taxonomy, APIM error codes |
| `runbooks/chad-dependencies.md` | Cosmos DB, Key Vault, PingFederate, OTLP telemetry |
| `catalog_chad.json` | Full catalog.json configuration for these runbooks |
| `seed_data_chad.yaml` | Original demo seed data with CHAD service topology |

## Using This as a Template

Each file in `runbooks/` has a corresponding **blank template** in `knowledge/templates/runbooks/` where customer-specific values have been replaced with `<PLACEHOLDER>` blocks.

Start from the template, not from this example. Use this example as a reference when you are unsure what value to put in a placeholder.

## Technical Stack (for context)

- **Language/Framework:** Java 17, Spring Boot 3.x
- **Container runtime:** Azure AKS, Kubernetes 1.28+
- **Service mesh:** Istio with AuthorizationPolicies
- **API gateway:** Azure API Management (B2B and internal routes)
- **Auth:** Azure AD JWT validated at APIM, Workload Identity for service-to-Azure-service
- **Data:** Azure Cosmos DB (NoSQL), Azure Key Vault (secrets)
- **External auth:** PingFederate (SSO integration)
- **Observability:** OTEL Java Agent 2.8.0, Micrometer OTLP, Elastic Agent

## Note on Customer Identifiers

The runbooks in this directory contain some MetLife-specific identifiers (ACR registry URLs, Azure tenant IDs, managed identity client IDs). These are preserved to maintain the integrity of the worked example. They are not active production credentials.

The templates in `knowledge/templates/` have all these identifiers removed and replaced with placeholders.
