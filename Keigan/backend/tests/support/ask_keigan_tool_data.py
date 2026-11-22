"""Data for the Ask Keigan tools that read activity, runbooks, the application map and SLOs: builders for tests that call the tools and for tests that ask whole questions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.entities.application_entities import MonitoredService
from keigan.entities.knowledge_entities import ApplicationTopology, Runbook
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement
from keigan.integrations.telemetry_gateway import ChangeEvent
from keigan.utils.time_utils import utc_now
from support.telemetry_scope import create_scoped_application


class ActivityLogStub:
    """The part of the telemetry gateway the Activity Log read uses: returns events, or fails, and records the window it was asked for."""

    def __init__(self, events: list[ChangeEvent] | None = None, failure: Exception | None = None, *, simulated: bool = False) -> None:
        self.events = events or []
        self.failure = failure
        self.simulated = simulated
        self.requests: list[tuple[str, datetime, datetime]] = []

    def activity_is_simulated(self, use_simulation: bool = False) -> bool:
        return self.simulated or use_simulation

    async def query_activity_changes(
        self, application_id: str, _tenant_id: str | None, _subscription_id: str | None, _resource_group_name: str | None, start: datetime, end: datetime, use_simulation: bool = False,
    ) -> list[ChangeEvent]:
        self.requests.append((application_id, start, end))
        if self.failure:
            raise self.failure
        return self.events


def use_activity_log(monkeypatch: pytest.MonkeyPatch, stub: ActivityLogStub) -> None:
    monkeypatch.setattr(application_context, "telemetry_gateway", lambda: stub)


def change_event(occurred_at: datetime, description: str = "Release deployed", *, caller: str | None = "release-pipeline", kind: str = "deployment") -> ChangeEvent:
    return ChangeEvent(occurred_at=occurred_at, change_kind=kind, operation_name="Microsoft.Web/sites/deployments/write", resource_identifier="/subscriptions/x", description=description, caller=caller)


THREE_CHANGES = [
    change_event(datetime(2026, 1, 5, 7, 5, tzinfo=UTC), "Scaled the claims plan", kind="scaling"),
    change_event(datetime(2026, 1, 5, 9, 42, tzinfo=UTC), "Release 41 deployed"),
    change_event(datetime(2026, 1, 5, 8, 10, tzinfo=UTC), "Connection string changed", kind="configuration_change"),
]


async def add_runbook(application_id: str, title: str, trigger_symptoms: str, steps: str) -> str:
    async with open_session() as session:
        runbook = Runbook(application_id=application_id, runbook_title=title, trigger_symptoms_text=trigger_symptoms, runbook_steps_markdown=steps, created_by_user_principal_name="system:test")
        session.add(runbook)
        await session.flush()
        return runbook.runbook_id


TOPOLOGY_NODES = [
    {"node_key": "claims-api", "label": "claims-api", "node_type": "service", "technology": "AKS", "description": "Public claims API", "criticality": "tier_1"},
    {"node_key": "claims-db", "label": "Claims database", "node_type": "database", "technology": "Azure SQL", "description": "Stores claims", "criticality": "tier_1"},
    {"node_key": "payments-queue", "label": "Payments queue", "node_type": "queue", "technology": "Service Bus", "description": None, "criticality": None},
]
TOPOLOGY_EDGES = [
    {"source_node_key": "claims-api", "target_node_key": "claims-db", "relationship": "reads and writes", "protocol": "TDS", "description": "Claim records"},
    {"source_node_key": "claims-api", "target_node_key": "payments-queue", "relationship": "publishes to", "protocol": None, "description": None},
]


async def add_topology(application_id: str, version_number: int, *, is_current: bool, nodes: list[dict[str, Any]] | None = None, understanding: str | None = None) -> None:
    async with open_session() as session:
        session.add(ApplicationTopology(
            application_id=application_id, topology_version_number=version_number,
            topology_graph_json={"nodes": nodes if nodes is not None else TOPOLOGY_NODES, "edges": TOPOLOGY_EDGES, "uncertainties": ["Is the queue shared?"]},
            understanding_summary_markdown=understanding, generation_status="ready", review_status="reviewed", is_current_version=is_current,
        ))


@dataclass(frozen=True)
class SloApplication:
    application_id: str
    application_code: str
    application_name: str
    service_name: str


# (SLI name, kind, target, good events, total events): breached, healthy, at risk, and one that has no measurements yet.
SLO_ROWS = [
    ("Checkout availability", "availability", 99.9, 990, 1000),
    ("Claims latency", "latency", 99.0, 999, 1000),
    ("Queue freshness", "freshness", 99.0, 9925, 10000),
    ("Batch success", "run_success", 99.0, None, None),
]


async def create_slo_application(rows: list[tuple[str, str, float, int | None, int | None]] | None = None) -> SloApplication:
    scoped = await create_scoped_application()
    service_name = f"svc-{uuid.uuid4().hex[:6]}"
    async with open_session() as session:
        service = MonitoredService(application_id=scoped.application_id, service_name=service_name, service_type="app_service", created_by_user_principal_name="system:test")
        session.add(service)
        await session.flush()
        for sli_name, sli_kind, target, good, total in rows or SLO_ROWS:
            sli = ServiceLevelIndicator(
                application_id=scoped.application_id, service_id=service.service_id, sli_name=sli_name, sli_kind=sli_kind, data_source_kind="log_query", is_approximate=sli_kind == "freshness",
                created_by_user_principal_name="system:test",
            )
            session.add(sli)
            await session.flush()
            session.add(ServiceLevelObjective(sli_id=sli.sli_id, application_id=scoped.application_id, target_percentage=target, rolling_window_days=30, created_by_user_principal_name="system:test"))
            if total is not None:
                session.add(SliMeasurement(sli_id=sli.sli_id, measurement_window_start=utc_now() - timedelta(days=2), good_event_count=good, total_event_count=total))
        return SloApplication(scoped.application_id, scoped.application_code, f"Scope {scoped.application_code}", service_name)
