# 10 — Deployment on AKS

## 1. Topology

| Namespace | Workload | Image | Replicas (prod) | Exposure |
|---|---|---|---|---|
| `keigan-frontend` | `keigan-web` (nginx-unprivileged serving the SPA, proxy `/api` → backend) | `keigan-web` | 2 | Internal ingress (corporate network) `https://keigan.<domain>` |
| `keigan-backend` | `keigan-api` (Uvicorn, 2 workers per pod) | `keigan-backend` | 2–6 (HPA on CPU + RPS) | ClusterIP; ingress paths `/api/alerts/in/*` and `/api/teams/messages` exposed to the required public sources only |
| `keigan-backend` | `keigan-worker` (`python -m keigan.worker_main`) | `keigan-backend` | 2 (HPA on queue depth via KEDA later) | none |

NetworkPolicies: frontend may reach backend API port only; backend egress limited to Azure endpoints, ServiceNow, Graph, LLM endpoint, configured log tools (via egress gateway / firewall).

## 2. Identity

- **Workload identity**: a user-assigned managed identity `id-keigan-<env>` federated with the `keigan-backend` service account. Used for ARM, Log Analytics, Monitor metrics, Key Vault, Blob, Azure SQL, Microsoft Graph (group lookups) and (optionally) Azure OpenAI.
- **Entra app registrations**: `keigan-spa` (SPA, redirect URIs), `keigan-api` (exposes `api://keigan-api/access_as_user`; optional `groupMembershipClaims: SecurityGroup` so tokens also carry group object IDs), `keigan-bot` (Bot Framework + Graph application permissions: `Chat.Create`, `TeamsAppInstallation.ReadWriteForChat.All`, `Mail.Send` restricted by application access policy, `User.Read.All`; RSC `ChatMessage.Read.Chat` in the Teams manifest).
- Cross-tenant applications: multi-tenant registration consented in the other tenant, or Azure Lighthouse delegation of Reader roles.

### 2.1 What application teams see on "Grant access"

The onboarding *Grant access* step shows Keigan's **tenant ID, client ID, object (principal) ID and display name**, and builds
the `az` / PowerShell / portal commands with that object ID. In AKS you do not need to type these IDs anywhere:

| Value | Where Keigan gets it |
|---|---|
| Tenant ID, client ID | `AZURE_TENANT_ID` and `AZURE_CLIENT_ID`, injected into the pod by the workload identity webhook |
| Object (principal) ID | Read from the `oid` claim of Keigan's own Azure Resource Manager token at runtime (no extra permission) |
| Display name | `KEIGAN_MANAGED_IDENTITY_DISPLAY_NAME` in the Helm values (for example `id-keigan-prod`) |

`KEIGAN_MANAGED_IDENTITY_OBJECT_ID` / `_CLIENT_ID` only override discovery; leave them empty. Unedited template values such as
`<managed-identity-object-id>` are ignored. If an ID cannot be found (identity not federated yet), the screen shows a warning
banner and "Not configured" instead of a wrong ID, and Keigan retries every five minutes. Keigan admins see the same values
in the **Keigan identity** panel of **Administration → Settings**.

### 2.2 Who can do what: Keigan admin, application admin, application reader

| Role | Comes from | Set up by |
|---|---|---|
| Keigan admin | Membership of `KEIGAN_ADMIN_GROUP_NAME` (default `KEIGAN_admin`) or `KEIGAN_ADMIN_GROUP_OBJECT_ID` | Helm values, once |
| Application admin | Membership of the application's admin group (default `<CODE>_admin`) | Keigan admin, per application |
| Application reader | Membership of the application's reader group (default `<CODE>_reader`) | Keigan admin, per application |

Keigan does not need to be told about new groups. The steps for a new application are:

1. Request `<CODE>_admin` and `<CODE>_reader` from SailPoint / the Entra groups team and add the owners and readers.
2. A Keigan admin creates the application in **Applications → New application**. Keigan stores the two group names from
   `APPLICATION_ADMIN_GROUP_PATTERN` / `APPLICATION_READER_GROUP_PATTERN`.
3. If the groups have other names, the Keigan admin changes them on the onboarding **Access** step.
4. **Check in Entra** on the same step confirms both groups exist, shows how many members they have, and saves their object IDs.
5. When an owner signs in, Keigan reads their groups from Microsoft Graph (`transitiveMemberOf`, nested groups included, cached
   for 10 minutes) and matches them against every application's group names and object IDs. They see the application at once.

This needs one Graph **application** permission on Keigan's managed identity: `GroupMember.Read.All`. A managed identity has no
"API permissions" blade, so grant it once with the CLI (as a Privileged Role Administrator):

```bash
KEIGAN_OBJECT_ID=$(az identity show -g <rg> -n id-keigan-prod --query principalId -o tsv)
GRAPH_SP_ID=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query id -o tsv)
ROLE_ID=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query "appRoles[?value=='GroupMember.Read.All'].id" -o tsv)
az rest --method POST --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$KEIGAN_OBJECT_ID/appRoleAssignments" \
  --body "{\"principalId\":\"$KEIGAN_OBJECT_ID\",\"resourceId\":\"$GRAPH_SP_ID\",\"appRoleId\":\"$ROLE_ID\"}"
```

Without it, sign-in still works but only through group object IDs in the token (`groupMembershipClaims`), so every
application must have its group object IDs saved, and "Check in Entra" reports that the permission is missing.

## 3. Configuration and secrets

- Non-secret settings: ConfigMap → env (`ENVIRONMENT=prod`, `AUTH_MODE=entra`, `TELEMETRY_MODE=live`, `LLM_PROVIDER=openai_compatible`, endpoints, intervals).
- Secrets: Azure Key Vault via Secrets Store CSI driver (LLM key if not managed identity, ServiceNow credentials, bot secret, SMTP password) mounted as env; application-provided secrets (Elastic keys etc.) written by Keigan to Key Vault at runtime (`SECRET_STORE_MODE=key_vault`, identity has `Key Vault Secrets Officer` on Keigan's vault only).
- Database: **Azure SQL Database**, private endpoint, Entra-only authentication. Keigan signs in with its managed identity
  (`DATABASE_AUTHENTICATION=managed_identity`), so `DATABASE_URL` holds no password:
  `mssql+aioodbc://@<server>.database.windows.net:1433/<database>?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`.
  Tables live in schema `keigan` (`DATABASE_SCHEMA=keigan`). PostgreSQL (`postgresql+asyncpg://…`) remains supported.
  See section 8 for the scripts to run before the first install.
- Files: Azure Blob Storage private container `knowledge` (`FILE_STORAGE_MODE=azure_blob`).

## 4. Images

- Backend: `python:3.12-slim-bookworm` with Microsoft ODBC Driver 18 (`msodbcsql18`) and the `keigan[azuresql]` extra (`aioodbc`), non-root user, read-only root filesystem, `/tmp` emptyDir. Entrypoints: API `uvicorn keigan.main:app --host 0.0.0.0 --port 8080 --workers 2 --proxy-headers`; worker `python -m keigan.worker_main`.
- Frontend: multi-stage `node:22-alpine` build → `nginxinc/nginx-unprivileged:stable-alpine`; security headers and CSP in `nginx.conf`; SPA fallback; `/api` proxy to `http://keigan-api.keigan-backend.svc.cluster.local:8080`.

## 5. Ingress

- Internal ingress (corporate): `/` → web, `/api` → web (proxied) or directly to API.
- Public (restricted) ingress: `POST /api/alerts/in/*` (allow Azure `ActionGroup` service tag and Elastic Cloud egress IPs; rate limit 50 r/s; body ≤ 256 KB) and `POST /api/teams/messages` (Bot Framework).
- TLS via cert-manager / corporate certificates.

## 6. Operations

- Probes: `/api/public/health` (liveness), `/api/public/readiness` (readiness).
- Logs: JSON to stdout → Container Insights; correlation ID per request and per job.
- Scaling: running investigations are bounded by `INVESTIGATION_MAX_CONCURRENT` across all worker pods together (counted in the database when a job is leased); extra investigations wait in the queue. Adding worker replicas raises throughput only up to that limit, so raise the limit with them.
- Database migrations: Helm pre-install/pre-upgrade job runs `python -m alembic upgrade head` (`databaseMigration.enabled`).
  The baseline (`94692c828bd3`) is already recorded by the SQL scripts, so the first install is a no-op and later releases
  apply only their new migrations. Turn the job off if DBAs apply changes themselves (`alembic upgrade <from>:<to> --sql`).
- Backups: Azure SQL point-in-time restore (7–35 days) and long-term retention as required; Blob soft delete.

## 7. Local development

```
backend:  python -m venv .venv && .venv\Scripts\activate && pip install -e . && copy .env.example .env
          python -m keigan.seed_main      # demo data
          uvicorn keigan.main:app --reload --port 8000
frontend: npm install && npm run dev      # http://localhost:5173 (proxies /api → :8000)
```

## 8. First deployment to Azure — order of work

| Step | Who | What |
|---|---|---|
| 1 | Platform team | Create the managed identity `id-keigan-<env>`, federate it with service account `keigan-backend` in namespace `keigan-backend` |
| 2 | Entra admin | Grant the identity Graph `GroupMember.Read.All` (section 2.2); create `KEIGAN_admin` and add the Keigan admins |
| 3 | Entra admin | App registrations `keigan-spa` and `keigan-api` (and `keigan-bot` when Teams goes live) |
| 4 | DBA / SQL Entra admin | Create the Azure SQL database (Entra-only auth, private endpoint), then run `database/azure_sql/run_all.sql` with `-v KeiganIdentityName=id-keigan-<env>` — see `database/azure_sql/README.md` |
| 5 | Platform team | Key Vault secrets (`keigan-database-url`, `keigan-llm-api-key`, …) and the identity's access to them |
| 6 | Platform team | Build and push both images; fill `deploy/helm/keigan/values.yaml` (tenant, client IDs, hosts, LLM gateway); `helm upgrade --install` |
| 7 | Keigan admin | Sign in, check the **Keigan identity** panel in **Administration → Settings** shows tenant, client and object ID, then create the first application and run **Check in Entra** on its Access step |

The SQL scripts create tables only. No users, applications or demo data are inserted: `python -m keigan.seed_main` refuses
to run when `ENVIRONMENT=prod`.
