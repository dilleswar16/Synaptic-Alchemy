# Runbook: AKS Pod CrashLoopBackOff Investigation

**Trigger keyword:** `aks-crashloop`

Match when alert description or rule name contains: `crashloop`, `CrashLoopBackOff`, `pod`, `OOMKilled`, `restart`

---

## 1. Trigger

Azure Monitor or AKS alert fires for a pod entering CrashLoopBackOff or
being OOMKilled in a monitored namespace.

---

## 2. Evidence to Collect

Priority order:

1. **AKS context** – pod status, restart count, recent events for the deployment
2. **Elastic logs** – last 500 lines from the crashing pod's log stream
   - Filter by: `kubernetes.pod.name: <pod-name>`, `log.level: ERROR OR FATAL`
3. **Elastic metrics** – JVM heap usage, CPU, memory for the service
   - Look for: `jvm.memory.heap.used` approaching `jvm.memory.heap.max`
4. **Azure Activity Log** – any deployments, config map changes, or secret rotations in last 60 min

---

## 3. Common Root Causes

1. JVM OutOfMemoryError — heap not sized for current traffic (check JVM metrics)
2. Application startup failure — missing env var or secret (check pod Events)
3. Liveness probe failing — app is starting too slowly (check probe config)
4. OOMKilled by kernel — container memory limit too low (check container limits)
5. Infinite restart loop from dependency failure (DB down, config missing)
6. Recent deployment introduced a startup crash (check Activity Log)

---

## 4. Fix Patterns

- OOM: increase JVM `-Xmx` and container memory limit; consider HPA
- Startup failure: check environment variable and secret mounts in pod spec
- Liveness probe: increase `initialDelaySeconds` or `failureThreshold`
- Deployment regression: roll back to previous image tag (V3 feature; V1 flag for manual action)

---

## 5. Escalation Path

- First: notify owning service team of pod crash details
- If JVM OOM: notify Java platform team for heap tuning
- If repeated across pods: consider traffic reduction while investigating
- SLA breach risk: notify Engineering Manager
