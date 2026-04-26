# CHAD Context Extraction Prompt (v2 — Hardened)

**INSTRUCTIONS FOR USER:**  
1. Open the CHAD application codebase on your org laptop in VS Code.  
2. Open GitHub Copilot Chat.  
3. Prefix the prompt with `@workspace` — this forces Copilot to index the entire project, not just the open file.  
4. Copy everything inside the `--- PROMPT START ---` / `--- PROMPT END ---` markers.  
5. After Copilot responds, copy the **5** generated markdown files into `knowledge/runbooks/` in the Corvin project.

---

--- PROMPT START ---

@workspace You are an expert SRE Architect. I am building "Corvin", an AI-powered SRE Co-Pilot that monitors the CHAD application in production. Corvin's LLM is completely blind to this codebase. Your job is to extract real, accurate knowledge from this workspace so the LLM can diagnose incidents correctly.

**KNOWN TECH STACK (use these to focus your search):**
- Build tool: **Maven** (`pom.xml` — do NOT look for `build.gradle`)
- Framework: **Spring Boot**
- Database: **Azure Cosmos DB** (look for `spring.cloud.azure.cosmos`, `CosmosClient`, `@Container`, `CosmosRepository`)
- Deployment: **AKS (Azure Kubernetes Service)**

**RULES — READ THESE CAREFULLY:**
1. Do NOT summarize. Do NOT explain your reasoning. Do NOT add headers like "Here is what I found".
2. Output ONLY raw Markdown content for **5 files**, each delimited clearly by `### FILE: <filename>` and `### END FILE`.
3. Do NOT invent endpoints, services, or errors that do not exist in the code. Extract only real ones.
4. Each file MUST start with a YAML frontmatter `keywords:` block — infer real keywords from actual class names, service names, and namespace names you find. Do NOT use my example keywords.
5. Count every microservice you find in this repo (each `pom.xml` with its own `<artifactId>`, each sub-module, each `@SpringBootApplication` entry point counts as one service).

---

**SEARCH TARGETS PER FILE:**

### FILE: `chad-api-spec.md`
Search for: `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, OpenAPI/Swagger config (`springdoc`, `springfox`), any APIM XML policy files.  
Produce a list of ALL exposed HTTP endpoints. For Spring Boot, also check `@RequestParam`, `@PathVariable`, and `@RequestBody` to understand input shape.

Required format:
```
---
keywords: [<infer from real service names, HTTP paths, and status codes found>]
---
# CHAD API Specification & APIM Policies

## Endpoints
- `METHOD /real/path/here`: <description>
  - **Auth:** <JWT/API Key/None — from actual config>
  - **Rate Limit:** <value from actual APIM policy or config>
  - **Failure Mode:** <what HTTP code it returns on error>
```

---

### FILE: `chad-dependencies.md`
Search for: `application.yml`, `application.properties`, `bootstrap.yml`, `pom.xml` (specifically `<dependencies>` and `<properties>`), `docker-compose.yml`, `@FeignClient` annotations, `RestTemplate` beans, `WebClient` beans.  
**Cosmos DB specific:** Look for `spring.cloud.azure.cosmos.endpoint`, `spring.cloud.azure.cosmos.database`, `CosmosClient`, `CosmosAsyncClient`, `ReactiveCosmosRepository`.  
Produce a complete map of what the CHAD app depends on externally.

Required format:
```
---
keywords: [<infer from real DB names, service URLs, host names found in config>]
---
# CHAD Upstream & Downstream Dependencies

## Azure Cosmos DB
- **Database name:** <from spring.cloud.azure.cosmos.database>
- **Containers:** <list @Container class names or repository interfaces found>
- **Connection mode:** <Gateway/Direct — from CosmosClientBuilder or config>
- **Failure Mode:** <exact exception — CosmosException, RequestRateTooLargeException, etc.>
- **SRE Action:** <specific action>

## External Services / APIs
- **<Service name from FeignClient or RestTemplate URL>:**
  - **Failure Mode:** <exact exception or HTTP code thrown>
  - **SRE Action:** <NEVER just say "restart the pod" if the fault is external>

## Message Queues / Brokers (if any)
- **<Kafka/RabbitMQ/Service Bus topic>:**
  - **Failure Mode:** <what happens if broker is down>
```

---

### FILE: `chad-known-errors.md`
Search for: `@ControllerAdvice`, `@ExceptionHandler`, custom Exception classes (files ending in `Exception.java`), `logger.error(...)` call sites, and any documented error codes in Swagger annotations.

Required format:
```
---
keywords: [<infer from actual exception class names found in code>]
---
# CHAD Known Errors & Exception Reference

| Exception / Log String | Business Meaning | Root Cause | SRE Action |
| :--- | :--- | :--- | :--- |
| `<ExactExceptionClassName>` | <Is this a user error or system fault?> | <Root cause> | <Action> |
```

---

### FILE: `chad-service-topology.md`
Search for: Kubernetes `deployment.yaml`, `service.yaml`, Helm chart `values.yaml`, ConfigMaps, any `docker-compose.yml`.  
**Scope: Physical AKS layout ONLY.** Do NOT include inter-service call graphs here — that belongs in `chad-service-inventory.md`.  
This file teaches the LLM the physical shape of the deployment so it can trace which pod an error is coming from.

Required format:
```
---
keywords: [<infer from actual namespace names, deployment names, pod labels found>]
---
# CHAD Service Topology

## Kubernetes Deployment
- **Namespace:** <real value>
- **Deployments:** <list of real deployment names>
- **Key Labels:** <app=, tier=, etc. from actual manifests>

## Service Call Graph
- `<ServiceA>` → calls → `<ServiceB>` (sync/async, protocol)
- If `<ServiceB>` fails, `<ServiceA>` throws `<ExactException>`

## HPA & Scaling
- **HPA target:** <real metric — CPU/memory/custom>
- **Known constraint:** <e.g., metrics-server issue if any>
```

---

### FILE: `chad-service-inventory.md`
Search for: every Maven `<module>` in the root `pom.xml`, every directory containing a `@SpringBootApplication` class, every Kubernetes `Deployment` manifest, any `@FeignClient` or `RestTemplate`/`WebClient` call that calls another internal service.  
**Scope: Service count, purpose, and inter-service call graph ONLY.** Do NOT repeat AKS topology details here.

Required format:
```
---
keywords: [<list of all real service/module names found>]
---
# CHAD Service Inventory

## Total Service Count
- **Number of microservices:** <exact count>

## Service List
| Service Name | Maven Module / artifactId | Port | AKS Deployment Name | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| <real name> | <real artifactId> | <port from config> | <deployment name from k8s yaml> | <1-line purpose> |

## Inter-Service Dependencies
- `<ServiceA>` depends on `<ServiceB>` — <reason: sync HTTP / async event / shared DB>
- If `<ServiceB>` goes down, `<ServiceA>` will <exact behaviour: return 503, throw X, degrade gracefully>
```

---

### FILE: `chad-security-context.md`
Search for: `SecurityFilterChain`, `@PreAuthorize`, `@EnableWebSecurity`, `DefaultAzureCredential`, `@AzureClientBean`, `azure.activedirectory.*` in config files, Application Insights connection string or instrumentation key in `application.yml` or `bootstrap.yml`, any JWT validation config.  
This file teaches the LLM about the auth layer so it can distinguish an Azure AD token rejection from a real application crash.

Required format:
```
---
keywords: [unauthorized, 401, 403, forbidden, token, jwt, azure ad, identity]
---
# CHAD Security & Observability Context

## Authentication
- **Method:** <Azure AD / API Key / JWT / None — from actual Spring Security config>
- **Token validation:** <what validates the JWT — APIM policy / Spring Security filter>
- **Failure Mode:** If token is expired/invalid, the app returns <HTTP code and exact error body if visible in code>

## Azure Managed Identity
- **Used:** <Yes/No — is DefaultAzureCredential or @AzureClientBean present?>
- **Accesses:** <list of Azure services accessed via managed identity — Cosmos, Key Vault, Storage, etc.>

## Application Insights
- **Instrumentation key / connection string:** <present in config: Yes/No>
- **What is traced:** <if OTel or App Insights SDK present, what is auto-instrumented>

## SRE Note
- An HTTP 401 from CHAD almost always means Azure AD token expired or APIM policy blocked the request — do NOT restart the pod.
- An HTTP 403 means the Managed Identity lacks the required RBAC role on the target Azure resource.
```

--- PROMPT END ---
