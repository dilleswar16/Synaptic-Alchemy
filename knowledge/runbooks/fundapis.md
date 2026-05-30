## Resolution: fundapis is healthy; remediation should focus on restoring the Elastic Agent OTLP receiver endpoint so that telemetry export (metrics, traces, logs) succeeds again without impacting the running application.

- Root cause: The root cause of the observed errors is a failure of the Elastic Agent OTLP receiver endpoint (elastic-agent-otlp.elastic-agent.svc.cluster.local:8200) inside the cluster, which is consistently returning HTTP 503 'Service Unavailable' and connection refused errors to OTLP exporters in the fundapis application containers and their istio-proxy sidecars. This causes all metrics, traces, and logs sent via OTLP to fail to be ingested into Elastic, but the fundapis deployment itself remains fully healthy (2/2 ready replicas, no restarts, low CPU and stable memory) and continues to serve traffic successfully, as seen by passing health checks. Therefore, the incident is confined to the observability/telemetry pipeline rather than the fundapis service runtime.
- Fix applied: Restart elastic-agent-otlp pods in the elastic-agent namespace
- Investigation: `d343d78c-38c2-42a1-8b6a-9c4baa98ab59`


---

## Resolution: Restore availability of the Elastic Agent OTLP receiver backing elastic-agent-otlp.elastic-agent.svc.cluster.local:8200 so that telemetry from fundapis is ingested again, without changing the healthy chad-fundapis deployment.

- Root cause: The observed abnormalities are confined to the observability pipeline rather than the fundapis application or its infrastructure. OpenTelemetry and Micrometer exporters in both the fundapis containers and their istio-proxy sidecars are repeatedly failing to send traces, logs, and metrics to the in-cluster Elastic Agent OTLP receiver at elastic-agent-otlp.elastic-agent.svc.cluster.local:8200, receiving HTTP 503 "Service Unavailable" responses and connection refused errors. At the same time, Kubernetes reports the chad-fundapis deployment as fully healthy (2/2 running and ready pods, no restarts, low CPU and memory well within requests/limits, no probe failures or OOM events), and cluster nodes and network metrics are normal. Therefore, there is no underlying fundapis or cluster outage; the root cause of the investigation findings is the unavailability of the Elastic Agent OTLP receiver endpoint, which prevents telemetry from being ingested into Elastic but does not affect fundapis request handling.
- Fix applied: Perform a rolling restart of the Elastic Agent OTLP receiver deployment
- Investigation: `e0250df1-9e0f-436f-9210-80d56c005214`
