"""
Corvin Command Center — Agent Tool Definitions & Executors.

Each tool maps 1-to-1 with a real live endpoint or adapter in the platform.
No fake data. Every executor calls the same code paths used by the existing
investigation pipeline and dashboard pages.

Tool groups
-----------
Platform (DB-backed):
    get_platform_stats          → InvestigationRepository.get_investigation_stats()
    list_recent_incidents       → InvestigationRepository.list_investigations()
    get_investigation_detail    → InvestigationRepository.get_investigation_result()
    get_predictive_alerts       → InvestigationRepository.list_predictive_alerts()
    get_service_score           → build_service_score() (existing strategy module)
    get_roi                     → build_roi_stats() (existing strategy module)
    get_service_topology        → build_service_topology() (existing strategy module)
    get_blast_radius            → InvestigationRepository + blast_radius logic
    get_postmortem              → InvestigationRepository.get_post_mortem()
    get_similar_incidents       → InvestigationRepository.get_similar_incidents()

Knowledge (file-backed):
    get_site_knowledge          → KnowledgeLoader.load_site_knowledge()
    get_runbook                 → KnowledgeLoader.load_matching_runbooks()

Data (Azure-backed — requires network to org cluster):
    run_kql                     → LogAnalyticsAdapter.get_apim_logs()
    get_aks_health              → AKSAdapter.get_pod_context()
    get_container_resource_metrics → ContainerLogsAdapter.get_resource_metrics()
"""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

# ── Tool Schema Definitions (OpenAI function-calling format) ──────────────────

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_platform_stats",
            "description": (
                "Return aggregated SRE health metrics for the entire Corvin platform: "
                "total investigation count, today's count, mean time to resolve (MTTR), "
                "confidence distribution (high/medium/low), approval and execution rates, "
                "and the most recently investigated services. "
                "Use this when the user asks about overall platform health, MTTR, or statistics."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_incidents",
            "description": (
                "Return a list of the most recent investigations on the Corvin platform, "
                "newest first. Each item includes: request_id, service_name, environment, "
                "trigger_source, description, approval_status, created_at, completed_at. "
                "Use this when the user asks about recent incidents, history, or wants to find an investigation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of incidents to return (default 10, max 50).",
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Optional filter: only return incidents for this service.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_investigation_detail",
            "description": (
                "Return the full details of a specific investigation by its ID, including "
                "the RCA (root cause analysis), fix strategy, evidence bundle, and post-mortem "
                "if generated. Use this when the user mentions a specific investigation ID or "
                "asks for details about a particular incident."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "investigation_id": {
                        "type": "string",
                        "description": "The UUID of the investigation (request_id).",
                    }
                },
                "required": ["investigation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_predictive_alerts",
            "description": (
                "Return the current list of predictive alerts — proactive detections of "
                "likely-upcoming incidents based on trend analysis. Each alert includes: "
                "alert_type, title, summary, severity, confidence, estimated_breach_at. "
                "Use this when the user asks about upcoming risks or predictive monitoring."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_score",
            "description": (
                "Return a composite health score (0–100) for a specific service and environment, "
                "based on incident frequency, MTTR, confidence, and fix success rate. "
                "Use this when the user asks 'how healthy is X service?' or 'what's the score for Y?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "The service to score (e.g. 'fundsso', 'partnerapis').",
                    },
                    "environment": {
                        "type": "string",
                        "description": "Target environment (default: 'dev').",
                    },
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_roi",
            "description": (
                "Return ROI metrics for the Corvin platform: estimated engineering hours saved, "
                "cost saved vs a manual baseline MTTR, and the number of incidents auto-resolved. "
                "Use this when the user asks about value, savings, or ROI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "integer",
                        "description": "Look-back window in months (1–12, default 1).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_topology",
            "description": (
                "Return the service dependency topology derived from recent investigations: "
                "which services call which, discovered dependencies, and incident hotspots. "
                "Use this when the user asks about architecture, dependencies, or service maps."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_blast_radius",
            "description": (
                "Return the blast radius analysis: which downstream services and users are likely "
                "affected by an incident or a hypothetical failure. Provide either an investigation_id "
                "(for a real incident) or a service_name (for a speculative what-if scenario). "
                "Use this when the user asks about impact, affected services, or blast radius."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "investigation_id": {
                        "type": "string",
                        "description": "The UUID of a specific investigation (optional).",
                    },
                    "service_name": {
                        "type": "string",
                        "description": "The name of the service to analyze (optional, e.g. 'partnerapis').",
                    },
                    "environment": {
                        "type": "string",
                        "description": "Environment for speculative analysis (default: 'dev').",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_postmortem",
            "description": (
                "Return the post-mortem document for a specific investigation, including "
                "timeline, root cause, actions taken, and prevention recommendations. "
                "Use this when the user asks for a post-mortem or incident report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "investigation_id": {
                        "type": "string",
                        "description": "The UUID of the investigation.",
                    }
                },
                "required": ["investigation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_similar_incidents",
            "description": (
                "Return past incidents for the same service and environment. Useful for "
                "identifying recurring patterns, known issues, or historical context for "
                "a current incident. Use when the user asks 'has this happened before?' "
                "or 'what are past issues with X?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Service name to look up.",
                    },
                    "environment": {
                        "type": "string",
                        "description": "Environment (default: 'dev').",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Max results to return (default 5).",
                    },
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_site_knowledge",
            "description": (
                "Return the CHAD site knowledge base: architecture overview, service descriptions, "
                "AKS cluster details, APIM configuration, namespaces, and infrastructure conventions. "
                "Use this whenever the user asks about CHAD architecture, how services are deployed, "
                "cluster names, namespaces, or any infrastructure-level question."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_runbook",
            "description": (
                "Return the runbook for a specific service or incident type from the CHAD knowledge base. "
                "Runbooks contain step-by-step investigation and resolution procedures. "
                "Use this when the user asks about how to fix or diagnose a specific service or issue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A keyword or phrase to match the correct runbook, e.g. "
                            "'fundsso memory leak' or 'partnerapis 401 jwt'."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_kql",
            "description": (
                "Fetch APIM gateway logs from Azure Log Analytics for a named service. "
                "Returns request logs, response codes, latency, and error details from the "
                "Azure API Management gateway. Requires network access to the org Azure subscription. "
                "Use this when the user asks about API logs, APIM errors, 4xx/5xx rates, or latency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "The API or backend service name (e.g. 'partnerapis', 'fundapis').",
                    },
                    "environment": {
                        "type": "string",
                        "description": "Environment to filter by (default: 'dev').",
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "description": "How many minutes back to retrieve logs (default: 60).",
                    },
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_aks_health",
            "description": (
                "Fetch live AKS pod status, restart counts, resource pressure, recent events, "
                "and deployment rollout state for a named service from the CHAD cluster. "
                "Use this when the user asks about pod health, restarts, OOMKill, deployment status, "
                "or anything Kubernetes-related."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Kubernetes deployment or service name (e.g. 'fundsso', 'partnerapis').",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: 'chad').",
                    },
                    "environment": {
                        "type": "string",
                        "description": "Target environment.",
                    },
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_apim_analytics",
            "description": (
                "Query live APIM gateway analytics from Azure Log Analytics. "
                "Returns structured data with rows, columns, and a chart_type hint "
                "(area, bar, pie, heatmap, table, tiles) that the UI renders as a visual chart. "
                "ALWAYS use this — not run_kql — when the user asks about: API traffic volumes, "
                "success/error rates, latency percentiles, unique member counts, fund code "
                "breakdowns, caller IPs, TLS compliance, peak hours, or anything about "
                "partnerapis or fundapis performance. "
                "TWO MODES: "
                "(1) Template mode: pass template_name to use a pre-validated query. "
                "(2) Custom mode: if no template fits, write your own KQL and pass it as `kql`. "
                "Available templates: kpi_summary, traffic_over_time, success_rate, "
                "response_code_distribution, api_traffic_split, unique_members_by_fund, "
                "requests_by_fund, top_members, fund_activity_heatmap, partnerapis_operations, "
                "fundapis_traffic, fundapis_operations_by_fund, latency_percentiles, "
                "backend_vs_overhead, slowest_operations, error_rate, errors_by_code, "
                "error_origin, top_caller_ips, tls_versions, traffic_source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": (
                            "The pre-validated analytics template to run. Choose based on the user's question. "
                            "'how many users/members today' → unique_members_by_fund. "
                            "'overall health/KPIs/summary' → kpi_summary. "
                            "'traffic over time' → traffic_over_time. "
                            "'error rate/errors' → error_rate or errors_by_code. "
                            "'latency/performance/slow' → latency_percentiles or slowest_operations. "
                            "'which fund gets most traffic' → requests_by_fund. "
                            "'peak hours/heatmap' → fund_activity_heatmap. "
                            "'backend vs gateway overhead' → backend_vs_overhead. "
                            "'partnerapis ops' → partnerapis_operations. "
                            "'fundapis ops/flow' → fundapis_operations_by_fund. "
                            "'tls/security' → tls_versions. "
                            "'caller ips' → top_caller_ips. "
                            "Omit this field when using custom `kql` mode."
                        ),
                    },
                    "kql": {
                        "type": "string",
                        "description": (
                            "Custom KQL query to execute. Use this when the user's question "
                            "cannot be answered by any named template. "
                            "The primary table is ApiManagementGatewayLogs. "
                            "Do NOT include a top-level `| where TimeGenerated` filter — "
                            "the time range is applied automatically via time_range_minutes. "
                            "Example: 'ApiManagementGatewayLogs | summarize count() by ResponseCode | order by count_ desc'. "
                            "Omit this field when using template_name mode."
                        ),
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["area", "bar", "pie", "heatmap", "table", "tiles"],
                        "description": (
                            "Chart type for the UI renderer. Required in custom kql mode. "
                            "In template mode, each template has a sensible default but the user "
                            "can request a different visualization — if they do, set this to override it. "
                            "'area' for time-series, 'bar' for category comparisons, "
                            "'pie' for distribution/share, 'heatmap' for fund×hour grids, "
                            "'tiles' for single-row KPI aggregates, 'table' for raw rows. "
                            "Omit to use the template default."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Human-readable chart title. Required in custom kql mode.",
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "description": (
                            "Lookback window in minutes. Convert the user's exact phrasing — "
                            "any integer is valid, do NOT round to presets unless the user is vague. "
                            "'last 5 minutes' → 5, 'last 50 minutes' → 50, 'last 90 minutes' → 90, "
                            "'last hour' → 60, 'last 4 hours' → 240, 'today' → 1440, "
                            "'this week' → 10080. Default when no time hint given: 1440."
                        ),
                    },
                    "api_filter": {
                        "type": "string",
                        "enum": ["all", "partnerapis", "fundapis"],
                        "description": "Filter to a specific API. Only applies in template mode. Default: 'all'.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_container_resource_metrics",
            "description": (
                "Fetch live CPU and memory usage with requests/limits from AKS Container Insights "
                "(Log Analytics Perf/K8SContainer) for a service. "
                "Use this whenever the user asks for CPU usage, memory usage, resource limits, "
                "capacity, or utilization percentages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Kubernetes service/deployment name to query (e.g. 'fundapis').",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: 'chad').",
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "description": "Look-back window in minutes (default: 60).",
                    },
                },
                "required": ["service_name"],
            },
        },
    },
]


# ── Tool Executors ────────────────────────────────────────────────────────────

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch a tool call to the appropriate live adapter or repository function.

    All calls are live — no mock data. Functions mirror exactly what the
    existing dashboard endpoints call.
    """
    try:
        return _EXECUTORS[tool_name](arguments)
    except KeyError:
        raise ValueError(f"Unknown tool: {tool_name!r}")
    except Exception as exc:
        _log.warning("Tool %r failed: %s", tool_name, exc)
        return {"error": str(exc), "tool": tool_name}


def _exec_platform_stats(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    repo = InvestigationRepository()
    return repo.get_investigation_stats()


def _exec_list_recent_incidents(args: dict) -> list:
    from corvin.storage.repository import InvestigationRepository
    limit = min(int(args.get("limit", 10)), 50)
    service_filter = args.get("service_name", "").strip().lower()
    repo = InvestigationRepository()
    results = repo.list_investigations()
    if service_filter:
        results = [r for r in results if r.get("service_name", "").lower() == service_filter]
    return results[:limit]


def _exec_investigation_detail(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    inv_id = args["investigation_id"]
    repo = InvestigationRepository()
    result = repo.get_investigation_result(inv_id)
    if result is None:
        return {"error": f"Investigation {inv_id!r} not found."}
    import json as _json
    return _json.loads(result.model_dump_json())


def _exec_predictive_alerts(args: dict) -> list:
    from corvin.storage.repository import InvestigationRepository
    from corvin.triggers.predictive import PredictiveMonitor
    repo = InvestigationRepository()
    monitor = PredictiveMonitor(repo=repo)
    alerts = monitor.refresh_alerts()
    return [a.model_dump(mode="json") for a in alerts]


def _exec_service_score(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    service = args["service_name"]
    env = args.get("environment", "dev")
    repo = InvestigationRepository()
    return repo.get_service_score(service_name=service, environment=env)


def _exec_roi(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    from corvin.strategy.roi import build_roi_stats, _parse_dt
    from corvin.core.config_loader import get_env, load_config
    from datetime import datetime, timedelta, timezone
    months = max(1, min(int(args.get("months", 1)), 12))
    repo = InvestigationRepository()
    investigations = repo.list_investigations()
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    filtered = [
        r for r in investigations
        if (dt := _parse_dt(r.get("completed_at") or r.get("created_at"))) and dt >= cutoff
    ]
    policy = load_config("policies/investigation", get_env())
    stats = build_roi_stats(filtered, policy=policy)
    stats.period_months = months
    return stats.model_dump()


def _exec_topology(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    from corvin.investigation.topology import (
        build_service_topology,
        ServiceTopology,
        TopologyNode,
        TopologyEdge,
        _inject_apim_topology,
        build_pod_topology_node,
        _resource_summary,
        _resource_summary_by_pod,
    )
    repo = InvestigationRepository()
    results = repo.list_recent_results(limit=30)

    if results:
        # Start from persisted investigation topology, then overlay live metrics.
        base = build_service_topology(results)
        nodes = {n.id: n for n in base.nodes}
        edges = {(e.source, e.target, e.label): e for e in base.edges}
    else:
        # No investigations yet — fall back to static CHAD architecture + live AKS pods.
        static_services = [
            ("fundapis", "high"),
            ("partnerapis", "high"),
            ("fundsso", "high"),
        ]
        nodes = {}
        edges = {}
        for svc_name, status in static_services:
            svc_id = f"svc:{svc_name}"
            nodes[svc_id] = TopologyNode(id=svc_id, label=svc_name, kind="service", status=status)
        _inject_apim_topology(nodes, edges)

    try:
        from corvin.evidence.aks_adapter import AKSAdapter
        from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
        _AKS_NAME_MAP = {
            "chad-fundapis":    "fundapis",
            "chad-fundsso":     "fundsso",
            "chad-partnerapis": "partnerapis",
        }
        adapter = AKSAdapter()
        logs_adapter = ContainerLogsAdapter()
        live = adapter.list_all_pods()
        for svc in live.get("services", []):
            raw_name = svc["name"]
            svc_name = _AKS_NAME_MAP.get(raw_name, raw_name)
            svc_id = f"svc:{svc_name}"
            try:
                metric_rows = logs_adapter.get_resource_metrics(svc_name)
            except Exception:
                metric_rows = []
            service_resource = _resource_summary(metric_rows)
            pod_resource_map = _resource_summary_by_pod(metric_rows)
            nodes[svc_id] = TopologyNode(
                id=svc_id,
                label=svc_name,
                kind="service",
                status=svc.get("status", "high"),
                cpu_mcores=service_resource["cpu_mcores"],
                cpu_request_mcores=service_resource["cpu_request_mcores"],
                cpu_limit_mcores=service_resource["cpu_limit_mcores"],
                cpu_utilization_pct=service_resource["cpu_utilization_pct"],
                memory_mib=service_resource["memory_mib"],
                memory_request_mib=service_resource["memory_request_mib"],
                memory_limit_mib=service_resource["memory_limit_mib"],
                memory_utilization_pct=service_resource["memory_utilization_pct"],
            )
            for pod in svc.get("pods", []):
                if not isinstance(pod, dict):
                    continue
                pod_copy = dict(pod)
                pod_name = str(pod_copy.get("name") or pod_copy.get("pod") or "").strip()
                pod_resource = pod_resource_map.get(pod_name, {})
                for key, value in pod_resource.items():
                    if value is not None:
                        pod_copy[key] = value
                pod_node = build_pod_topology_node(pod_copy)
                nodes[pod_node.id] = pod_node
                edges[(svc_id, pod_node.id, "runs")] = TopologyEdge(source=svc_id, target=pod_node.id, label="runs")
    except Exception:
        pass

    return ServiceTopology(nodes=list(nodes.values()), edges=list(edges.values())).model_dump()


def _exec_blast_radius(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    from corvin.strategy.blast_radius import estimate_blast_radius, BlastRadiusEstimate
    from corvin.core.contracts import EvidenceBundle
    from corvin.core.config_loader import get_env, load_config

    inv_id = args.get("investigation_id")
    repo = InvestigationRepository()
    
    if inv_id:
        result = repo.get_investigation_result(inv_id)
        if result is None:
            return {"error": f"Investigation {inv_id!r} not found."}
        return estimate_blast_radius(
            service_name=result.request.service_name,
            environment=result.request.environment,
            evidence=result.evidence,
            policy=load_config("policies/investigation", get_env())
        ).model_dump()
    
    # Speculative analysis
    service_name = args.get("service_name")
    if not service_name:
        return {"error": "Either investigation_id or service_name must be provided."}
    
    env = args.get("environment", "dev")
    # For speculative analysis, we pass an empty evidence bundle
    # The estimator will use downstream API counts if evidence is empty
    # But here we should ideally try to find some recent evidence if possible
    empty_evidence = EvidenceBundle(request_id="speculative")
    return estimate_blast_radius(
        service_name=service_name,
        environment=env,
        evidence=empty_evidence,
        policy=load_config("policies/investigation", get_env())
    ).model_dump()


def _exec_postmortem(args: dict) -> dict:
    from corvin.storage.repository import InvestigationRepository
    inv_id = args["investigation_id"]
    repo = InvestigationRepository()
    pm = repo.get_post_mortem(inv_id)
    if pm is None:
        return {"error": f"No post-mortem found for investigation {inv_id!r}."}
    import json as _json
    return _json.loads(pm.model_dump_json())


def _exec_similar_incidents(args: dict) -> list:
    from corvin.storage.repository import InvestigationRepository
    service = args["service_name"]
    env = args.get("environment", "dev")
    n = max(1, min(int(args.get("n", 5)), 10))
    repo = InvestigationRepository()
    return repo.get_similar_incidents(service_name=service, environment=env, n=n)


def _exec_site_knowledge(args: dict) -> str:
    from corvin.core.knowledge_loader import KnowledgeLoader
    return KnowledgeLoader().load_site_knowledge()


def _exec_runbook(args: dict) -> str:
    from corvin.core.knowledge_loader import KnowledgeLoader
    query = args.get("query", "")
    runbooks = KnowledgeLoader().load_matching_runbooks(query)
    if not runbooks:
        return f"No runbook found matching '{query}'. Consider drafting one."
    return "\n\n---\n\n".join(runbooks)


def _exec_run_kql(args: dict) -> Any:
    from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter
    adapter = LogAnalyticsAdapter()
    return adapter.get_apim_logs(
        service_name=args["service_name"],
        environment=args.get("environment", "dev"),
        time_range_minutes=int(args.get("time_range_minutes", 60)),
    )


def _exec_apim_analytics(args: dict) -> dict:
    from corvin.evidence.apim_analytics_adapter import APIMAnalyticsAdapter
    adapter = APIMAnalyticsAdapter()
    time_range = int(args.get("time_range_minutes", 1440))

    if args.get("kql"):
        # Custom mode — LLM wrote its own KQL query
        return adapter.run_kql_raw(
            kql=args["kql"],
            time_range_minutes=time_range,
            chart_type=args.get("chart_type", "table"),
            title=args.get("title", "Custom Query"),
            subtitle="",
        )

    template = args.get("template_name")
    if not template:
        return {
            "error": "Provide either template_name or kql.",
            "row_count": 0,
            "rows": [],
            "columns": [],
            "chart_type": "table",
            "title": "No query specified",
            "subtitle": "",
            "template_name": "none",
            "time_range_minutes": time_range,
            "api_filter": "all",
        }

    return adapter.query_template(
        template_name=template,
        time_range_minutes=time_range,
        api_filter=args.get("api_filter", "all"),
        chart_type_override=args.get("chart_type"),
    )


def _exec_aks_health(args: dict) -> Any:
    from corvin.evidence.aks_adapter import AKSAdapter
    adapter = AKSAdapter()
    return adapter.get_pod_context(
        service_name=args["service_name"],
        namespace=args.get("namespace"),
        environment=args.get("environment"),
    )


def _exec_container_resource_metrics(args: dict) -> dict[str, Any]:
    from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
    from corvin.investigation.topology import _resource_summary, _resource_summary_by_pod

    service_name = args["service_name"]
    namespace = args.get("namespace")
    minutes = int(args.get("time_range_minutes", 60))

    rows = ContainerLogsAdapter().get_resource_metrics(
        service_name=service_name,
        namespace=namespace,
        time_range_minutes=minutes,
    )
    service_summary = _resource_summary(rows)
    by_pod = _resource_summary_by_pod(rows)
    pods = [{"pod_name": pod_name, **metrics} for pod_name, metrics in by_pod.items()]
    pods.sort(key=lambda p: str(p.get("pod_name", "")))

    return {
        "service_name": service_name,
        "namespace": namespace or "chad",
        "time_range_minutes": minutes,
        "sample_count": len(rows),
        "service": service_summary,
        "pods": pods,
    }


_EXECUTORS = {
    "get_platform_stats":       _exec_platform_stats,
    "list_recent_incidents":    _exec_list_recent_incidents,
    "get_investigation_detail": _exec_investigation_detail,
    "get_predictive_alerts":    _exec_predictive_alerts,
    "get_service_score":        _exec_service_score,
    "get_roi":                  _exec_roi,
    "get_service_topology":     _exec_topology,
    "get_blast_radius":         _exec_blast_radius,
    "get_postmortem":           _exec_postmortem,
    "get_similar_incidents":    _exec_similar_incidents,
    "get_site_knowledge":       _exec_site_knowledge,
    "get_runbook":              _exec_runbook,
    "run_kql":                  _exec_run_kql,
    "get_aks_health":           _exec_aks_health,
    "get_container_resource_metrics": _exec_container_resource_metrics,
    "query_apim_analytics":     _exec_apim_analytics,
}
