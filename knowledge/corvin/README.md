# Corvin — CHAD SRE Co-Pilot

## What is Corvin?

Corvin is an AI-powered SRE Co-Pilot grounding corpus for the **CHAD** platform (project code **14470**). It is a structured knowledge base of verified, code-derived facts that an LLM can retrieve at incident time to assist an SRE without inventing information.

Every fact in this corpus was extracted directly from source code, pipeline YAML, Kubernetes manifests, and APIM policy XML. No content is summarised, assumed, or invented. If a fact does not exist in the codebase, it is not present here.

---

## What is CHAD?

CHAD is a MetLife Australia channel integration platform. It connects partner superannuation fund systems to MetLife's insurance administration platform (AXE / MIP) via three Spring Boot microservices deployed on Azure AKS.

**The platform does three things:**

| # | Service | What it does |
| :--- | :--- | :--- |
| 1 | `fundapis` | Receives XML and JSON member/insurance data **inbound** from partner fund systems via APIM. Validates posted data against fund-specific XSD schemas. Persists to Cosmos DB (`FundRequest`, `MemberProfile` containers). Also serves internal read endpoints consumed by the other two services. |
| 2 | `partnerapis` | Exposes member detail and insurance data **outbound** to AXE (MetLife Insurance Platform). Reads member data from `fundapis` internal endpoints and directly from `MemberProfile` Cosmos container. Manages partner config (`PartnerConfigs` container). Accepts amended insurance postbacks from AXE. |
| 3 | `fundSSO` | **SSO broker** — receives a member ID and scheme reference from a fund system, fetches the member profile from `fundapis`, drops member attributes to PingFederate's Reference ID Adaptor (`RefIDChadAU`), and returns an HTTP `302` redirect with `?REF=<referenceValue>` to initiate the SAML SSO flow into MIP. |

**Partner funds known to integrate via CHAD:** REIS, CareSuper, APEX (from APIM IP allowlist entries).

---

## Runtime Environments

| Environment | Cosmos DB | Key Vault | Domain |
| :--- | :--- | :--- | :--- |
| **prod** | `cdb14470aepr0101.documents.azure.com` | `kyv14470aepr0101` | `www.channels.metlife.com.au` |
| **dev** | `cdb14470aedv0101.documents.azure.com` | `kyv14470aedv0101` | `dev.channels.metlife.com.au` |

- **AKS namespace:** `chad`
- **APIM gateway name:** `EAI14470`
- **Container registry (prod):** `acr14470aepr011.azurecr.io/14470-chad/`
- **Azure AD tenant:** `ca56a4a5-e300-406a-98ff-7e36a0baac5b`

---

## Knowledge Files in This Corpus

| File | What it answers |
| :--- | :--- |
| [chad-service-inventory.md](chad-service-inventory.md) | How many services are there? Which Maven artifact is which? Which service calls which? What happens if `fundapis` goes down? |
| [chad-service-topology.md](chad-service-topology.md) | Which AKS namespace? What are the HPA min/max values? What are the liveness/readiness probe paths? What image is running? |
| [chad-api-spec.md](chad-api-spec.md) | What HTTP endpoints exist? What headers are required? What does a 400/404/500 mean on a given endpoint? What is the SRE action for each failure mode? |
| [chad-known-errors.md](chad-known-errors.md) | I see a log string or exception in Elastic / Kibana. What service threw it? What does it mean? What do I do? |
| [chad-dependencies.md](chad-dependencies.md) | What external systems does CHAD talk to? Which Cosmos containers exist? Which Key Vault secrets are required? What happens if PingFederate is down? |
| [chad-security-context.md](chad-security-context.md) | How does auth work? Why is the pod getting 401/403? How does Workload Identity work? Where is OTEL data sent? |

The [catalog.json](catalog.json) file maps keywords and log strings to the above files for automated retrieval.

---

## What Corvin Can Help With

- Diagnosing a specific log string or exception in production
- Identifying which service owns an HTTP endpoint and what its failure modes are
- Finding the correct `kubectl` command for a given incident (always with `-n chad`)
- Locating the correct Azure resource to check (Cosmos account, Key Vault, APIM)
- Tracing an inter-service call failure (e.g. `partnerapis → fundapis → Cosmos`)
- Identifying whether a 401/403 is APIM-level (pod has zero log entries) or application-level

## What Corvin Cannot Help With

- **Runtime state:** Corvin has no live access to logs, metrics, or pod status. Use Elastic APM, Azure Monitor, and `kubectl` directly.
- **On-call rotations, SLAs, escalation paths:** These are not in the codebase and are not in this corpus.
- **Incidents outside the CHAD platform:** Corvin has no knowledge of AXE/MIP internals, PingFederate internals, or Cosmos DB internals beyond the CHAD-specific integration surface.
- **Business decisions:** Corvin does not know business rules, fund contract terms, or feature roadmap.

---

## Quick Reference for Incidents

```bash
# All CHAD pods are in namespace: chad
kubectl get pods -n chad
kubectl logs -n chad deploy/chad-fundapis --since=1h
kubectl logs -n chad deploy/chad-partnerapis --since=1h
kubectl logs -n chad deploy/chad-fundsso --since=1h

# Check HPA status
kubectl get hpa -n chad

# Check a pod's env for Key Vault or OTEL config
kubectl describe pod -n chad -l service=fundapis
```

**Azure Portal quick links (prod):**
- Cosmos DB: search `cdb14470aepr0101` → Data Explorer
- Key Vault: search `kyv14470aepr0101` → Secrets
- APIM: search `EAI14470` → APIs → chad-fund-apis / chad-partner-apis / chad-sso-apis

---

## Corpus Integrity

All knowledge files in this corpus have been verified against source code via grep, line-number-level reads, and cross-reference checks. The following advisory is open:

> **Security advisory:** `chad-dependencies.md` contains a Key Vault secret value (`xml.access.key`) verbatim. Review before committing to a shared or public repository.
