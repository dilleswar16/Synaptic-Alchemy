---
prompt_key: hypothesis_infrastructure
version: 4
model_tier: deep
output_schema: HypothesisResult
---
{% set perspective_title = "Infrastructure" %}
{% set lens = "compute (nodes, pods, plans), memory and CPU saturation, scaling and quotas, storage, networking, load balancers and firewalls, platform incidents, mainframe subsystems and batch scheduling, hardware faults." %}
{% include "_hypothesis_body.md" %}
