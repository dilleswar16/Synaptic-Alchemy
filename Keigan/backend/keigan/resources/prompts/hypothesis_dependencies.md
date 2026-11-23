---
prompt_key: hypothesis_dependencies
version: 5
model_tier: deep
output_schema: HypothesisResult
---
{% set perspective_title = "Dependencies" %}
{% set lens = "downstream APIs, databases, queues, caches, identity providers, third-party and SaaS services, network paths between services, expired certificates, DNS, rate limits and throttling, partner outages." %}
{% include "_hypothesis_body.md" %}
