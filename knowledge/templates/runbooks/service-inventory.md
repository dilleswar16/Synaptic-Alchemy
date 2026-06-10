---
template: service-inventory
version: "1"
description: Technical service inventory for a Java Spring Boot microservices application
---

# <APPLICATION_NAME> — Service Inventory

## Services

| Service | artifactId | Main Class | Port | AKS Deployment | Purpose |
|---------|-----------|-----------|------|----------------|---------|
| `<service-1>` | `<maven-artifact-id>` | `<com.company.service.ServiceApplication>` | `<port>` | `<k8s-deployment-name>` | `<one-line purpose>` |
| `<service-2>` | `<maven-artifact-id>` | `<com.company.service.ServiceApplication>` | `<port>` | `<k8s-deployment-name>` | `<one-line purpose>` |

*For non-Java services, replace `artifactId` and `Main Class` with equivalent build identifiers.*

---

## Inter-Service Dependencies

| Caller | Called Service | Protocol | Purpose |
|--------|---------------|----------|---------|
| `<service-A>` | `<service-B>` | `HTTP/REST` | `<why A calls B>` |
| `<service-A>` | `<external-api>` | `HTTP/REST` | `<why A calls external>` |

---

## Architecture Constraints

These facts help Corvin reason about blast radius and cascading failures:

| Constraint | Value | Implication for Incidents |
|------------|-------|--------------------------|
| Shared database between services | `<Yes / No>` | `<If yes: data mutations in service A affect service B>` |
| Message bus / event queue | `<Yes: Kafka/Service Bus / No: synchronous only>` | `<If no: failures propagate synchronously, full blast radius immediately>` |
| Circuit breaker | `<Yes: Resilience4j / Hystrix / No>` | `<If no: downstream failure causes upstream timeout cascade>` |
| Caching layer | `<Yes: Redis / In-memory / No>` | `<Cache size and TTL — affects staleness during incident>` |

---

## Build & Deployment

| Property | Value |
|----------|-------|
| Build tool | `<Maven 3.x / Gradle>` |
| Java version | `<17 / 21>` |
| Spring Boot version | `<3.x>` |
| Container registry | `<registry-url>` |
| Image tag strategy | `<git SHA / semver / date-build>` |
| Deployment strategy | `<RollingUpdate / Blue-Green / Canary>` |

---

## Service Ownership

| Service | Team | On-Call Rotation | Escalation Contact |
|---------|------|-----------------|-------------------|
| `<service-1>` | `<team-name>` | `<PagerDuty / rotation name>` | `<escalation contact>` |
| `<service-2>` | `<team-name>` | `<PagerDuty / rotation name>` | `<escalation contact>` |

---

## SRE Notes

- `<Note about service startup time — relevant for readiness probe failures>`
- `<Note about known slow dependencies during cold start>`
- `<Note about any manual pre/post deployment steps>`
