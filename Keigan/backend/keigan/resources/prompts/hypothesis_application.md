---
prompt_key: hypothesis_application
version: 4
model_tier: deep
output_schema: HypothesisResult
---
{% set perspective_title = "Application" %}
{% set lens = "code defects and bad releases, configuration or feature-flag changes, unhandled exceptions, resource leaks, thread and connection pool exhaustion, retry storms, data-dependent bugs, schema or contract changes." %}
{% include "_hypothesis_body.md" %}
