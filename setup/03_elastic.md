# Setup Guide 3 — Elastic

Corvin queries Elastic for your Java application logs and JVM metrics.
This is the primary evidence source for RCA — stacktraces, OOM errors,
slow queries, and GC pressure all come from here.

The two values you need at the end:
- `ELASTIC_HOST`
- `ELASTIC_API_KEY`

---

## Which setup applies to you?

| Your situation | Go to |
|---|---|
| Using Elastic Cloud (managed) | Section A |
| Self-hosted Elastic on AKS / VM | Section B |
| Logs not in Elastic yet (in Log Analytics only) | Skip this guide |

---

## Section A — Elastic Cloud

### A1 — Get your cluster endpoint

1. Log in to https://cloud.elastic.co
2. Open your deployment → **Copy endpoint** under Elasticsearch
3. It looks like: `https://abc123.us-east-1.aws.elastic-cloud.com:9243`

This is your `ELASTIC_HOST`.

### A2 — Create an API key (read-only)

Never use your master password. Create a scoped API key:

1. In Kibana → **Stack Management** → **API Keys** → **Create API key**
2. Name: `corvin-readonly`
3. Set privileges:
   ```json
   {
     "corvin": {
       "indices": [
         {
           "names": ["logs-*", "metrics-*"],
           "privileges": ["read", "view_index_metadata"]
         }
       ]
     }
   }
   ```
4. Click **Create API key**
5. Copy the **encoded** value (the long base64 string) — this is your `ELASTIC_API_KEY`

---

## Section B — Self-hosted Elastic on AKS / VM

### B1 — Get the endpoint

If Elastic is running inside AKS and Corvin is also on AKS:
```
http://elasticsearch.elastic-system.svc.cluster.local:9200
```

If Corvin is running locally and Elastic is on AKS, port-forward:
```powershell
kubectl port-forward svc/elasticsearch-master 9200:9200 -n elastic-system
# Then use: http://localhost:9200
```

If Elastic is on a VM: `https://<vm-ip>:9200`

### B2 — Create an API key via Dev Tools

In Kibana → **Dev Tools**, run:
```json
POST /_security/api_key
{
  "name": "corvin-readonly",
  "role_descriptors": {
    "corvin": {
      "indices": [
        {
          "names": ["logs-*", "metrics-*"],
          "privileges": ["read", "view_index_metadata"]
        }
      ]
    }
  }
}
```

Copy the `encoded` field from the response → `ELASTIC_API_KEY`

---

## Step — Verify your index patterns exist

Corvin queries `logs-*` and `metrics-*` by default.
Check what indices you actually have:

In Kibana → **Dev Tools**:
```json
GET /_cat/indices/logs-*?h=index,docs.count&s=docs.count:desc
GET /_cat/indices/metrics-*?h=index,docs.count&s=docs.count:desc
```

If your Java app logs are in a different index (e.g. `app-logs-prod-*`), update
`config/integrations/elastic.yaml`:

```yaml
log_index_pattern: "app-logs-prod-*"
metrics_index_pattern: "metrics-*"
```

---

## Step — Verify field names match

Corvin filters logs by `service.name` and `service.environment` (ECS standard).
Check a sample document:

```json
GET /logs-*/_search
{
  "size": 1,
  "query": { "match_all": {} }
}
```

Look at the `_source` — if your Java app uses different field names (e.g.
`app_name` instead of `service.name`), update the query in
`corvin/evidence/elastic_adapter.py` `get_logs()` to match.

Common Spring Boot / Logstash field mappings:

| ECS (expected) | Common alternative |
|---|---|
| `service.name` | `app_name`, `application`, `spring.application.name` |
| `service.environment` | `env`, `environment`, `deployment.environment` |
| `@timestamp` | `timestamp` (usually fine) |
| `log.level` | `level`, `severity` |

---

## Getting Java app logs into Elastic

If your Java containers are not yet shipping logs to Elastic, the standard path:

### Option 1 — Filebeat sidecar on AKS (recommended)
Deploy Filebeat as a DaemonSet — it reads container stdout/stderr and ships
to Elastic automatically. Official Helm chart:
```powershell
helm repo add elastic https://helm.elastic.co
helm install filebeat elastic/filebeat `
  --set daemonset.hostNetworking=true
```

### Option 2 — Logback appender (in-process)
Add to your Spring Boot `pom.xml`:
```xml
<dependency>
  <groupId>co.elastic.logging</groupId>
  <artifactId>logback-ecs-encoder</artifactId>
  <version>1.5.0</version>
</dependency>
```
Then configure Logback to output ECS JSON — Filebeat or Logstash picks it up.

### Option 3 — OpenTelemetry Java agent
Attach the OTel Java agent to your container — it auto-instruments Spring Boot
and ships logs + metrics to an OTel Collector which forwards to Elastic.

---

## Values to add to `.env`

```env
ELASTIC_HOST=https://your-cluster-endpoint:9243
ELASTIC_API_KEY=<encoded API key>
```

See [04_env_file.md](04_env_file.md) for the complete `.env` template.
