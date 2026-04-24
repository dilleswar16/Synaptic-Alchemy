# Corvin Target Stack

## Core Platform Stack

| Area | Chosen Direction |
|---|---|
| Control plane language | Python |
| Web app | React plus Vite |
| Database | Postgres |
| Cloud | Azure |
| Primary log store | Elastic |
| Primary app and AKS metrics source | Elastic |
| APIM evidence source | Azure Log Analytics |
| Monitored applications | Java Spring Boot |
| Manual surfaces | CLI, REST API, web app, Teams |
| Automated trigger source | Azure alerts |

## Recommended Backend Stack

The recommended backend stack for the new product is:

- Python 3.12
- FastAPI for the HTTP control plane
- Typer for CLI workflows
- Pydantic v2 for typed contracts
- LiteLLM for model-provider abstraction and future model switching
- SQLAlchemy 2.x plus Alembic for persistence and migrations
- psycopg for Postgres connectivity
- httpx for outbound HTTP integrations
- Azure SDKs or REST adapters where needed
- Elastic Python client for logs and metrics access

## Recommended Frontend Stack

- React
- Vite
- TypeScript
- React Router
- TanStack Query

UI direction:

- operator-facing status and investigation console,
- RCA and fix strategy views,
- version-aware progress and slice visibility,
- future approval workflow support.

## Observability And Evidence Stack

| Source | Role In Corvin |
|---|---|
| Azure Monitor alerts | Primary trigger source |
| Azure Action Groups or webhook routing | Alert delivery path |
| Event Grid or equivalent event flow | Optional event trigger path |
| Elastic logs | Main application and infra log evidence |
| Elastic metrics | Main app and AKS metrics evidence |
| Log Analytics | APIM and Azure-native evidence queries |
| AKS APIs and cluster inspection | Workload state, rollout context, pod state |
| Azure Activity Log | Change intelligence and correlation |

## Delivery Surfaces

| Surface | Role |
|---|---|
| REST API | Core trigger and integration surface |
| CLI | Direct local investigation and replay surface |
| Web app | Operator console and approval center |
| Teams | Conversation and notification surface |

## Authentication Direction

- V1 may operate with no auth or simple internal mode.
- The architecture must leave room for future authentication.
- Future direction should be Entra ID compatible, but not a blocker for early versions.

## Execution Direction

- V1 should not execute fixes.
- V2 should prepare approval and justification flows.
- V3 may execute fixes only through policy-constrained, approval-gated pathways.

## Why Python For The Control Plane

Python is the recommended control-plane language because:

- it is fast to iterate for orchestration and LLM workflows,
- it has strong SDK support for Azure and Elastic,
- it fits API, CLI, and background task development well,
- it avoids coupling the platform implementation to the monitored Java services.

## LLM Runtime Direction

- Use a custom investigation engine rather than a framework-led multi-agent runtime.
- Use LiteLLM or an equivalent provider abstraction so model backends can be switched later without rewriting orchestration.
- Keep prompt control, tool routing, approval boundaries, and stage transitions inside product code.

## LangGraph Position

- LangGraph is not required for V1.
- LangGraph may be considered later only if the product genuinely needs durable workflow graphs, resumable long-running state, or more complex branching than the custom orchestrator can comfortably manage.
- Do not introduce LangGraph early unless a later version proves the orchestration complexity is real.

## What Should Remain Configurable

- model provider and model selection,
- Azure subscription or workspace bindings,
- Elastic endpoints and index strategies,
- Log Analytics workspace bindings,
- Teams delivery configuration,
- tool enablement and policy mode,
- execution permissions,
- version and feature flags.