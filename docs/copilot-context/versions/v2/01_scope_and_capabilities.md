# Corvin V2 Scope And Capabilities

## V2 Goal

V2 strengthens operator control, collaboration, and decision quality without crossing into uncontrolled execution.

## V2 Focus Areas

1. Approval-ready operator workflow
2. Better correlation and change intelligence
3. Stronger Teams and web collaboration flows
4. Replay and evaluation capability
5. Improved learning and incident comparison
6. Azure Cost Management daily report with anomaly detection

## V2 Required Capabilities

- Approval request objects and approval state handling
- Better Teams interaction model
- Web-based approval and review views
- Change-correlation enrichment
- Historical replay or evaluation support
- Stronger progress and incident visibility
- **Azure Cost Management scheduler** (see below)

## Azure Cost Management Scheduler (V2)

A daily background report equivalent to Vishwakarma's AWS cost reporter, rebuilt for Azure.

**What it does:**
- Fetches 30-day spend from Azure Cost Management API grouped by resource/service
- Computes daily baseline averages, week-over-week trend, month-over-month trend
- Detects anomalies (service cost exceeds configurable threshold vs baseline)
- For anomalous services: fetches Azure Monitor metrics that explain the billing change (request counts, DTUs, connections, bandwidth)
- LLM analyzes all data and produces a structured cost report
- Posts report as a Teams card + optional PDF attachment
- Scheduled daily at a configurable UTC time (`config/policies/scheduler.yaml`)
- Scheduled runs: only post when anomalies detected
- On-demand runs (Teams command): always post full report

**What it does NOT do in V2:**
- Does not auto-trigger a full agentic investigation (V3 option)
- Does not execute any remediation actions

**Config:**
```yaml
# config/policies/scheduler.yaml
cost_report:
  enabled: true
  schedule_utc: "06:30"
  anomaly_threshold: 0.20   # 20% above baseline = anomaly
  subscription_id: "<from integrations/azure_alerts.yaml>"
```

**Implementation notes:**
- APScheduler or a `threading.Timer` daemon thread started alongside FastAPI
- Uses `azure-mgmt-costmanagement` or Azure Cost Management REST API
- Same adapter pattern as evidence adapters — `CostManagementAdapter` in `corvin/evidence/`
- Teams delivery via `TeamsAdapter` (same delivery surface as investigations)

## V2 Still Excludes

- automatic fix execution,
- uncontrolled remediation,
- production action loops without approval,
- broad rollback automation.

## V2 Product Standard

V2 should make Corvin feel operationally mature even before execution exists.

That means:

- better reviewability,
- clearer justification,
- stronger traceability,
- stronger replay and evaluation support.