# Corvin Infrastructure & Application Knowledge Setup Guide

## Why This File Matters

`knowledge/site.md` is the **most important non-code file in this entire project.**

Every time Corvin runs an investigation, before it even reads a single log line,
it injects `site.md` into the AI's system prompt. This means the AI knows:
- Which AKS cluster to look at
- Which services are deployed and where
- Which Elastic index holds your logs
- What your APIM gateway is called

Without filling this in with real values, the AI will query generic placeholder
names and return useless results. This is a V1.5 task that MUST be done before
V2 can begin.

---

## What You Need To Fill In

Open `knowledge/site.md` and replace every placeholder with real values.
Here is exactly what information you need to gather and where to find it:

### Section 1: AKS Cluster

| Field | What to put | Where to find it |
|---|---|---|
| `Cluster name` | The name of your AKS cluster | Azure Portal → Kubernetes Services |
| `Resource group` | The RG that contains the cluster | Azure Portal → Kubernetes Services → Overview |
| `Region` | e.g. `eastus` or `southeastasia` | Azure Portal → Overview |
| `Node pool name` | Usually `agentpool` or `system` | Azure Portal → Node pools |
| `Kubernetes version` | e.g. `1.29` | Azure Portal → Overview |
| `Default namespace` | The namespace your app runs in | `kubectl get namespaces` |

### Section 2: Elastic

| Field | What to put | Where to find it |
|---|---|---|
| `Log index pattern` | e.g. `java-logs-*` or `app-logs-*` | Elastic Cloud → Kibana → Index Management |
| `Service name field` | The field that stores your service name | Check a log doc in Kibana Dev Tools |
| `Timestamp field` | Almost always `@timestamp` | Kibana Dev Tools |

### Section 3: APIM

| Field | What to put | Where to find it |
|---|---|---|
| `APIM name` | Your API Management instance name | Azure Portal → API Management |
| `Gateway log table` | Almost always `ApiManagementGatewayLogs` | Log Analytics → Tables |

### Section 4: Monitored Services (THE MOST IMPORTANT PART)

This is the table of every microservice Corvin should be able to investigate.
For each service, you need:

| Column | Example | Where to find it |
|---|---|---|
| `Service Name` | `order-service` | Your codebase / AKS deployment names |
| `Technology` | `Spring Boot 3.2` | Your team's docs |
| `Namespace` | `production` or `default` | `kubectl get deployments -A` |
| `AKS Deployment` | `order-service` | `kubectl get deployments` |
| `Elastic Index` | `java-logs-order-*` | Kibana → Index Management |
| `APIM API path` | `/api/orders/` | Azure APIM → APIs |

---

## What Runbooks You Need To Write

Runbooks in `knowledge/runbooks/` are matched by keyword. When an alert fires
with the word "crashloop" in it, Corvin automatically loads `aks-crashloop.md`.

You already have 2 runbooks:
- `aks-crashloop.md` — AKS pod OOM / CrashLoopBackOff ✅
- `apim-5xx.md` — Azure APIM gateway 5xx errors ✅

### Suggested New Runbooks To Write (V1.5 Task)

| Filename | Alert keyword trigger | When to use |
|---|---|---|
| `java-heap-oom.md` | `OutOfMemoryError`, `heap`, `jvm` | Java application heap exhaustion |
| `db-connection-pool.md` | `connection pool`, `HikariCP`, `timeout` | Database connection pool exhaustion |
| `apim-latency.md` | `latency`, `slow`, `p99`, `timeout` | High latency at the APIM gateway |
| `pod-pending.md` | `pending`, `scheduling`, `insufficient` | Pod stuck in Pending (node capacity) |
| `deployment-failure.md` | `rollout`, `deployment failed`, `image pull` | AKS deployment rollout failure |

### Runbook Template

Each runbook must follow this structure (copy `aks-crashloop.md` as your template):

```markdown
# Runbook: [Issue Name]

**Trigger keyword:** [keyword]
Match when alert contains: [list of keywords]

## 1. Trigger
[Describe what causes this alert]

## 2. Evidence to Collect
[Priority-ordered list of what data to pull]

## 3. Common Root Causes
[Numbered list of known causes]

## 4. Fix Patterns
[What actions resolve each cause]

## 5. Escalation Path
[Who to notify and when]
```

---

## Suggested Skills & Tools For Building This Project

### For Backend Development
- **Cursor** (AI code editor) — reads `.github/instructions` natively, perfect for building slices
- **GitHub Copilot** — already configured via your `.github/prompts` files
- **Postman** — for testing FastAPI endpoints during V2 development

### For System Design
- **Excalidraw** (excalidraw.com) — free, fast whiteboard for drawing the adapter flow
- **Eraser.io** — generates architecture diagrams from text descriptions
- **Mermaid** (built into VS Code) — for creating sequence diagrams directly in Markdown

### For MS Teams Bot Development
- **Bot Framework Emulator** — test your `botbuilder-python` bot locally before deploying to Teams
- **ngrok** — expose your local FastAPI port to the Teams webhook during development

### For Frontend
- **Stitch by Google** — AI UI design tool already available in your environment
- **Framer Motion** — for React micro-animations in V3 UI polish

### For Monitoring During Demo
- **k9s** — terminal-based Kubernetes dashboard, great to show alongside the Corvin UI

---

## Which Version Does This Belong To?

| Task | Version |
|---|---|
| Fill in `knowledge/site.md` with real AKS + Elastic values | **V1.5** (MUST do before V2) |
| Write the 5 new runbooks listed above | **V1.5** (MUST do before V2) |
| Update `knowledge/runbooks/catalog.json` with new runbook entries | **V1.5** |
| Add new services to the monitored services table | **Ongoing — update as you deploy** |
