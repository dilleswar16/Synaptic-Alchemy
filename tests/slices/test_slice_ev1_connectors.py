"""EV1 connector foundation tests.

Covers:
  - outbound connector create/update/test routes
  - YAML-to-DB migration for Teams outbound connectors
  - preserving config_json shape for flexible onboarding
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.main import app
from apps.api.seed_demo import ensure_demo_data
from apps.api.routes.applications import _db as _applications_db_dependency
from corvin.cli.migrate_config import run_migration
from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter
from corvin.connectors.config_resolver import ROLE_APIM_LOGS, ROLE_CONTAINER_INSIGHTS, resolve_log_source_config
from corvin.connectors.base import TestResult
from corvin.storage.models import Base, ApplicationRow, ApplicationServiceRow, LogSourceRow, OutboundConnectorRow, SloConfigRow


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _override_session(sf):
    app.dependency_overrides[_applications_db_dependency] = lambda: sf()


def _cleanup_override():
    app.dependency_overrides.pop(_applications_db_dependency, None)


def _create_app_row(sf) -> str:
    app_id = "app-ev1-001"
    with sf() as s:
        s.add(ApplicationRow(
            id=app_id,
            name="EV1",
            description="EV1 test app",
            team_name="Platform",
            environment_default="dev",
            topology_json={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        s.commit()
    return app_id


def _create_service_row(sf, app_id: str, service_name: str = "fundapis"):
    with sf() as s:
        s.add(ApplicationServiceRow(
            application_id=app_id,
            service_name=service_name,
            display_name=service_name,
            namespace="chad",
            tier="api",
            dependencies=[],
            metadata_json={},
        ))
        s.commit()


def test_outbound_connector_create_update_and_test(monkeypatch):
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs

        class Resp:
            status_code = 200
            text = "ok"

        return Resp()

    monkeypatch.setattr("corvin.delivery.outbound_connectors.httpx.request", fake_request)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/outbound-connectors", json={
            "connector_type": "generic_http",
            "display_name": "Pager Bridge",
            "config_json": {
                "endpoint": "https://example.invalid/hook",
                "endpoint_fields": {"http_method": "POST"},
                "auth": {"type": "bearer", "bearer_token": "abc123"},
                "variables": [{"key": "title", "default_value": "Hello"}],
                "payload_template": "{\"title\": \"{{title}}\"}",
            },
        })
        assert create_resp.status_code == 201
        body = create_resp.json()
        conn_id = body["id"]
        assert body["config_json"]["endpoint"] == "https://example.invalid/hook"

        update_resp = client.put(f"/applications/{app_id}/outbound-connectors/{conn_id}", json={
            "display_name": "Pager Bridge Updated",
            "config_json": {
                "endpoint": "https://example.invalid/new-hook",
                "endpoint_fields": {"http_method": "PUT"},
                "auth": {"type": "none"},
                "variables": [{"key": "title", "default_value": "Updated"}],
                "payload_template": "{\"title\": \"{{title}}\"}",
            },
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["display_name"] == "Pager Bridge Updated"

        test_resp = client.post(f"/applications/{app_id}/outbound-connectors/{conn_id}/test")
        assert test_resp.status_code == 200
        assert test_resp.json()["ok"] is True
        assert captured["method"] == "PUT"
        assert captured["url"] == "https://example.invalid/new-hook"
    finally:
        _cleanup_override()


def test_inbound_connector_update_route():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "byoa",
            "display_name": "BYOA Source",
            "config_json": {
                "base_url": "https://api.example.com",
                "health_endpoint": "/health",
            },
            "credential_type": "env_var",
            "credential_ref": "BYOA_TOKEN",
        })
        assert create_resp.status_code == 201
        src_id = create_resp.json()["id"]

        update_resp = client.put(f"/applications/{app_id}/connectors/{src_id}", json={
            "display_name": "BYOA Source Updated",
            "config_json": {
                "base_url": "https://api.example.com/v2",
                "health_endpoint": "/healthz",
            },
            "credential_type": "kv_reference",
            "credential_ref": "https://vault.example.net|byoa-token",
        })
        assert update_resp.status_code == 200
        body = update_resp.json()
        assert body["display_name"] == "BYOA Source Updated"
        assert body["source_type"] == "byoa"
        assert body["credential_type"] == "kv_reference"
        assert body["config_json"]["base_url"] == "https://api.example.com/v2"
    finally:
        _cleanup_override()


def test_azure_monitor_container_connector_route_normalizes_guided_fields():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "azure_monitor",
            "display_name": "CHAD Container Insights",
            "config_json": {
                "connector_role": "container_insights",
                "workspace_id": "container-ws",
                "cluster_name": "aks-01",
                "resource_group": "rg-observability",
                "subscription_id": "sub-123",
            },
            "credential_type": "env_var",
        })
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert body["config_json"]["connector_role"] == ROLE_CONTAINER_INSIGHTS
        assert body["config_json"]["cluster_name"] == "aks-01"
        assert body["config_json"]["default_namespace"] == "default"
    finally:
        _cleanup_override()


def test_azure_monitor_container_connector_requires_cluster_name():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "azure_monitor",
            "display_name": "Broken Container Insights",
            "config_json": {
                "connector_role": "container_insights",
                "workspace_id": "container-ws",
            },
            "credential_type": "env_var",
        })
        assert create_resp.status_code == 422
        assert "cluster_name" in str(create_resp.json())
    finally:
        _cleanup_override()


def test_connector_update_preserves_existing_env_ref_when_not_replaced():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "byoa",
            "display_name": "BYOA Source",
            "config_json": {
                "base_url": "https://api.example.com",
                "health_endpoint": "/health",
            },
            "credential_type": "env_var",
            "credential_ref": "BYOA_TOKEN",
        })
        assert create_resp.status_code == 201
        src_id = create_resp.json()["id"]

        update_resp = client.put(f"/applications/{app_id}/connectors/{src_id}", json={
            "display_name": "BYOA Source Renamed",
            "credential_type": "env_var",
        })
        assert update_resp.status_code == 200

        with sf() as session:
            row = session.get(LogSourceRow, src_id)
            assert row is not None
            assert row.credential_ref == "BYOA_TOKEN"
    finally:
        _cleanup_override()


def test_aks_connector_can_be_tested_via_registry(monkeypatch):
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    def fake_aks_test(self):
        return TestResult(ok=True, message="Connected successfully", latency_ms=10.0)

    monkeypatch.setattr("corvin.connectors.aks.AKSConnector.test_connection", fake_aks_test)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "aks",
            "display_name": "AKS Cluster",
            "config_json": {
                "cluster_name": "aks-01",
                "resource_group": "rg-01",
                "subscription_id": "sub-01",
                "default_namespace": "chad",
            },
            "credential_type": "env_var",
        })
        assert create_resp.status_code == 201
        src_id = create_resp.json()["id"]

        test_resp = client.post(f"/applications/{app_id}/connectors/{src_id}/test")
        assert test_resp.status_code == 200
        payload = test_resp.json()
        assert payload["ok"] is True
        assert "Connected successfully" in payload["message"]
    finally:
        _cleanup_override()


def test_aks_connector_normalizes_namespaces_on_create():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "aks",
            "display_name": "AKS Multi Namespace",
            "config_json": {
                "cluster_name": "aks-01",
                "resource_group": "rg-01",
                "subscription_id": "sub-01",
                "namespaces": ["chad", "funds", "CHAD", "partner"],
            },
            "credential_type": "env_var",
        })
        assert create_resp.status_code == 201
        cfg = create_resp.json()["config_json"]
        assert cfg["default_namespace"] == "chad"
        assert cfg["namespaces"] == ["chad", "funds", "partner"]
    finally:
        _cleanup_override()


def test_aks_connector_normalizes_explicit_clusters_on_create():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "aks",
            "display_name": "AKS Multi Cluster",
            "config_json": {
                "cluster_name": "legacy-primary",
                "resource_group": "rg-primary",
                "subscription_id": "sub-primary",
                "clusters": [
                    {
                        "cluster_name": "aks-east",
                        "resource_group": "rg-east",
                        "subscription_id": "sub-east",
                        "namespaces": ["chad", "CHAD", "partner"],
                    },
                    {
                        "cluster_name": "aks-west",
                        "resource_group": "rg-west",
                        "subscription_id": "sub-west",
                        "default_namespace": "funds",
                    },
                ],
            },
            "credential_type": "env_var",
        })
        assert create_resp.status_code == 201
        cfg = create_resp.json()["config_json"]
        assert isinstance(cfg.get("clusters"), list)
        assert len(cfg["clusters"]) == 2
        assert cfg["clusters"][0]["namespaces"] == ["chad", "partner"]
        assert cfg["clusters"][0]["default_namespace"] == "chad"
        assert cfg["clusters"][1]["namespaces"] == ["funds"]
        assert cfg["clusters"][1]["default_namespace"] == "funds"
    finally:
        _cleanup_override()


def test_aks_connector_rejects_invalid_cluster_entries():
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/connectors", json={
            "source_type": "aks",
            "display_name": "AKS Invalid Cluster",
            "config_json": {
                "clusters": [
                    {
                        "cluster_name": "aks-east",
                        "resource_group": "rg-east",
                        # missing subscription_id
                        "namespaces": ["chad"],
                    }
                ],
            },
            "credential_type": "env_var",
        })
        assert create_resp.status_code == 422
        assert "subscription_id" in str(create_resp.json())
    finally:
        _cleanup_override()


def test_bootstrap_outbound_connectors_is_idempotent_and_app_scoped(monkeypatch):
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    monkeypatch.setenv("AZURE_DEVOPS_ORG", "MetLife-Global")
    monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "Australia IT_AMS")
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "pat-token")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://outlook.office.com")
    monkeypatch.setenv("CORVIN_SMTP_HOST", "smtp.office365.com")
    monkeypatch.setenv("CORVIN_EMAIL_FROM", "corvin@example.com")
    monkeypatch.setenv("CORVIN_EMAIL_TO", "ops@example.com")
    monkeypatch.setenv("SHAREPOINT_SITE_ID", "my.metlife.com,site-guid,web-guid")

    client = TestClient(app)
    try:
        first = client.post(f"/applications/{app_id}/outbound-connectors/bootstrap")
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["inserted"] == 5
        assert first_payload["updated"] == 0

        second = client.post(f"/applications/{app_id}/outbound-connectors/bootstrap")
        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["inserted"] == 0
        assert second_payload["updated"] == 5

        with sf() as session:
            rows = session.query(OutboundConnectorRow).filter_by(application_id=app_id).all()
            assert len(rows) == 5
            assert {r.connector_type for r in rows} == {
                "teams_webhook",
                "email",
                "azure_devops_boards",
                "azure_devops_wiki",
                "sharepoint",
            }
    finally:
        _cleanup_override()


def test_bootstrap_outbound_connectors_supports_include_types_and_overwrite_policy(monkeypatch):
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://outlook.office.com")

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/outbound-connectors", json={
            "connector_type": "teams_webhook",
            "display_name": "Custom Teams",
            "config_json": {
                "endpoint": "https://custom.invalid/teams",
                "auth": {"type": "none"},
                "variables": [],
                "payload_template": "{}",
            },
        })
        assert create_resp.status_code == 201

        bootstrap = client.post(
            f"/applications/{app_id}/outbound-connectors/bootstrap",
            json={"include_types": ["teams_webhook"], "overwrite_existing": False},
        )
        assert bootstrap.status_code == 200
        payload = bootstrap.json()
        assert payload["inserted"] == 0
        assert payload["updated"] == 0

        with sf() as session:
            row = session.query(OutboundConnectorRow).filter_by(application_id=app_id, connector_type="teams_webhook").one()
            assert row.display_name == "Custom Teams"
            assert row.config_json["endpoint"] == "https://custom.invalid/teams"
    finally:
        _cleanup_override()


def test_outbound_connector_test_resolves_secret_ref(monkeypatch):
    sf = _session_factory()
    _override_session(sf)
    app_id = _create_app_row(sf)

    monkeypatch.setenv("TEAMS_BEARER_TOKEN", "resolved-token")
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})

        class Resp:
            status_code = 200
            text = "ok"

        return Resp()

    monkeypatch.setattr("corvin.delivery.outbound_connectors.httpx.request", fake_request)

    client = TestClient(app)
    try:
        create_resp = client.post(f"/applications/{app_id}/outbound-connectors", json={
            "connector_type": "generic_http",
            "display_name": "Secret Ref Bridge",
            "config_json": {
                "endpoint": "https://example.invalid/hook",
                "endpoint_fields": {"http_method": "POST"},
                "auth": {"type": "bearer", "bearer_token_ref": "env:TEAMS_BEARER_TOKEN"},
                "variables": [],
                "payload_template": "{}",
            },
        })
        assert create_resp.status_code == 201
        conn_id = create_resp.json()["id"]

        test_resp = client.post(f"/applications/{app_id}/outbound-connectors/{conn_id}/test")
        assert test_resp.status_code == 200
        assert test_resp.json()["ok"] is True
        headers = captured.get("headers", {})
        assert headers.get("Authorization") == "Bearer resolved-token"
    finally:
        _cleanup_override()


def test_migrate_from_yaml_seeds_teams_outbound(monkeypatch):
    sf = _session_factory()
    with sf() as session:
        monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.invalid/teams")
        monkeypatch.setenv("CORVIN_ENV", "local")
        monkeypatch.setenv("LOG_ANALYTICS_WORKSPACE_ID", "apim-seeded-ws")
        monkeypatch.setenv("CHAD_LOG_ANALYTICS_WORKSPACE_ID", "container-seeded-ws")
        monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "sub-123")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AKS_CLUSTER_NAME", "aks-seeded")
        monkeypatch.setenv("AKS_RESOURCE_GROUP", "rg-seeded")
        monkeypatch.setenv("AKS_NAMESPACE", "chad")
        result = run_migration(session)
        assert result["status"] == "ok"
        assert result["outbound_connectors_created"] >= 1
        app_row = session.query(ApplicationRow).first()
        assert app_row is not None
        assert len(app_row.outbound_connectors) >= 1
        assert app_row.outbound_connectors[0].config_json["endpoint"] == "https://example.invalid/teams"
        roles = {src.config_json.get("connector_role") for src in app_row.log_sources}
        assert ROLE_APIM_LOGS in roles
        assert ROLE_CONTAINER_INSIGHTS in roles
        apim = next(src for src in app_row.log_sources if src.config_json.get("connector_role") == ROLE_APIM_LOGS)
        container = next(src for src in app_row.log_sources if src.config_json.get("connector_role") == ROLE_CONTAINER_INSIGHTS)
        assert apim.config_json["subscription_id"] == "sub-123"
        assert apim.config_json["tenant_id"] == "tenant-123"
        assert container.config_json["cluster_name"] == "aks-seeded"
        assert container.config_json["resource_group"] == "rg-seeded"


def test_resolve_log_source_config_prefers_db_role_specific_connector(monkeypatch):
    sf = _session_factory()
    app_id = _create_app_row(sf)
    _create_service_row(sf, app_id, service_name="fundapis")

    @contextmanager
    def fake_get_session():
        with sf() as session:
            yield session

    monkeypatch.setattr("corvin.connectors.config_resolver.get_session", fake_get_session)

    with sf() as s:
        s.add(LogSourceRow(
            id="src-apim",
            application_id=app_id,
            source_type="azure_monitor",
            display_name="APIM Workspace",
            config_json={
                "workspace_id": "apim-ws",
                "apim_table": "ApiManagementGatewayLogs",
                "connector_role": ROLE_APIM_LOGS,
            },
            credential_type="env_var",
            credential_ref=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        s.add(LogSourceRow(
            id="src-container",
            application_id=app_id,
            source_type="azure_monitor",
            display_name="Container Workspace",
            config_json={
                "workspace_id": "container-ws",
                "default_namespace": "chad",
                "cluster_name": "aks-01",
                "connector_role": ROLE_CONTAINER_INSIGHTS,
            },
            credential_type="env_var",
            credential_ref=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()

    apim_cfg = resolve_log_source_config(
        "fundapis",
        source_type="azure_monitor",
        role=ROLE_APIM_LOGS,
        fallback={"workspace_id": "fallback-apim"},
    )
    container_cfg = resolve_log_source_config(
        "fundapis",
        source_type="azure_monitor",
        role=ROLE_CONTAINER_INSIGHTS,
        fallback={"workspace_id": "fallback-container", "default_namespace": "fallback"},
    )

    assert apim_cfg["workspace_id"] == "apim-ws"
    assert apim_cfg["connector_role"] == ROLE_APIM_LOGS
    assert container_cfg["workspace_id"] == "container-ws"
    assert container_cfg["connector_role"] == ROLE_CONTAINER_INSIGHTS
    assert container_cfg["default_namespace"] == "chad"


def test_resolve_log_source_config_handles_ambiguous_service_across_apps(monkeypatch):
    sf = _session_factory()
    app_id_without_connectors = _create_app_row(sf)
    _create_service_row(sf, app_id_without_connectors, service_name="fundapis")

    app_id_with_connectors = "app-with-connectors"
    with sf() as s:
        s.add(ApplicationRow(
            id=app_id_with_connectors,
            name="CHAD",
            description="CHAD app",
            team_name="Platform",
            environment_default="dev",
            topology_json={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        s.add(ApplicationServiceRow(
            application_id=app_id_with_connectors,
            service_name="fundapis",
            display_name="fundapis",
            namespace="chad",
            tier="api",
            k8s_app_label="chad-fundapis",
            dependencies=[],
            metadata_json={},
        ))
        s.add(LogSourceRow(
            id="src-container-ambiguous",
            application_id=app_id_with_connectors,
            source_type="azure_monitor",
            display_name="Container Workspace",
            config_json={
                "workspace_id": "container-ws-ambiguous",
                "default_namespace": "chad",
                "cluster_name": "aks-01",
                "connector_role": ROLE_CONTAINER_INSIGHTS,
            },
            credential_type="env_var",
            credential_ref=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()

    @contextmanager
    def fake_get_session():
        with sf() as session:
            yield session

    monkeypatch.setattr("corvin.connectors.config_resolver.get_session", fake_get_session)

    container_cfg = resolve_log_source_config(
        "fundapis",
        source_type="azure_monitor",
        role=ROLE_CONTAINER_INSIGHTS,
        fallback={"workspace_id": "fallback-container", "default_namespace": "fallback"},
    )

    assert container_cfg["workspace_id"] == "container-ws-ambiguous"
    assert container_cfg["connector_role"] == ROLE_CONTAINER_INSIGHTS


def test_resolve_log_source_config_does_not_cross_app_boundaries_by_default(monkeypatch):
    sf = _session_factory()
    app_id_without_connectors = _create_app_row(sf)
    _create_service_row(sf, app_id_without_connectors, service_name="fundapis")

    app_id_with_global_connector = "app-global-connector"
    with sf() as s:
        s.add(ApplicationRow(
            id=app_id_with_global_connector,
            name="Connector App",
            description="Has only connectors",
            team_name="Platform",
            environment_default="dev",
            topology_json={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        s.add(LogSourceRow(
            id="src-container-global",
            application_id=app_id_with_global_connector,
            source_type="azure_monitor",
            display_name="Container Workspace",
            config_json={
                "workspace_id": "container-ws-global",
                "default_namespace": "chad",
                "cluster_name": "aks-01",
                "connector_role": ROLE_CONTAINER_INSIGHTS,
            },
            credential_type="env_var",
            credential_ref=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()

    @contextmanager
    def fake_get_session():
        with sf() as session:
            yield session

    monkeypatch.setattr("corvin.connectors.config_resolver.get_session", fake_get_session)

    container_cfg = resolve_log_source_config(
        "fundapis",
        source_type="azure_monitor",
        role=ROLE_CONTAINER_INSIGHTS,
        fallback={"workspace_id": "fallback-container", "default_namespace": "fallback"},
    )

    assert container_cfg["workspace_id"] == "fallback-container"


def test_resolve_log_source_config_ignores_legacy_global_fallback_env(monkeypatch):
    sf = _session_factory()
    app_id_without_connectors = _create_app_row(sf)
    _create_service_row(sf, app_id_without_connectors, service_name="fundapis")

    app_id_with_global_connector = "app-global-connector"
    with sf() as s:
        s.add(ApplicationRow(
            id=app_id_with_global_connector,
            name="Connector App",
            description="Has only connectors",
            team_name="Platform",
            environment_default="dev",
            topology_json={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        s.add(LogSourceRow(
            id="src-container-global-optin",
            application_id=app_id_with_global_connector,
            source_type="azure_monitor",
            display_name="Container Workspace",
            config_json={
                "workspace_id": "container-ws-global",
                "default_namespace": "chad",
                "cluster_name": "aks-01",
                "connector_role": ROLE_CONTAINER_INSIGHTS,
            },
            credential_type="env_var",
            credential_ref=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()

    @contextmanager
    def fake_get_session():
        with sf() as session:
            yield session

    monkeypatch.setattr("corvin.connectors.config_resolver.get_session", fake_get_session)
    monkeypatch.setenv("CORVIN_ALLOW_GLOBAL_CONNECTOR_FALLBACK", "true")

    container_cfg = resolve_log_source_config(
        "fundapis",
        source_type="azure_monitor",
        role=ROLE_CONTAINER_INSIGHTS,
        fallback={"workspace_id": "fallback-container", "default_namespace": "fallback"},
    )

    assert container_cfg["workspace_id"] == "fallback-container"


def test_azure_adapters_do_not_require_yaml_runtime_fallback(monkeypatch):
    log_adapter = LogAnalyticsAdapter(config=None)
    container_adapter = ContainerLogsAdapter(config=None)

    monkeypatch.setattr(
        "corvin.evidence.log_analytics_adapter.resolve_log_source_config",
        lambda service_name, source_type, role, fallback: {"workspace_id": "db-apim-ws", "apim_table": "ApiManagementGatewayLogs"},
    )
    monkeypatch.setattr(
        "corvin.evidence.container_logs_adapter.resolve_log_source_config",
        lambda service_name, source_type, role, fallback: {"workspace_id": "db-container-ws", "default_namespace": "chad"},
    )

    assert log_adapter._resolved_config("fundapis")["workspace_id"] == "db-apim-ws"
    container_cfg, namespace, minutes = container_adapter._resolved_runtime("fundapis", None, None)
    assert container_cfg["workspace_id"] == "db-container-ws"
    assert namespace == "chad"
    assert minutes == 60


def test_demo_seed_reconciles_missing_chad_services_and_slos():
    sf = _session_factory()
    with sf() as s:
        app_id = "app-chad"
        s.add(ApplicationRow(
            id=app_id,
            name="CHAD",
            description="partial seed",
            team_name="Platform",
            environment_default="dev",
            topology_json={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        s.add(ApplicationServiceRow(
            application_id=app_id,
            service_name="partnerapis",
            display_name="Partner APIs",
            namespace="chad",
            tier="api",
            k8s_app_label="chad-partnerapis",
            dependencies=[],
            metadata_json={"apim_routes_through_gateway": True, "apim_api_id": "partnerapis"},
        ))
        s.add(ApplicationServiceRow(
            application_id=app_id,
            service_name="fundsso",
            display_name="Fund SSO",
            namespace="chad",
            tier="api",
            k8s_app_label="chad-fundsso",
            dependencies=[],
            metadata_json={"is_sso_direct": True},
        ))
        s.commit()

        changed = ensure_demo_data(s)

        assert changed is True
        services = {
            row.service_name: row
            for row in s.query(ApplicationServiceRow).filter_by(application_id=app_id).all()
        }
        assert set(services) == {"fundapis", "fundsso", "partnerapis"}
        assert services["fundapis"].k8s_app_label == "chad-fundapis"
        assert services["fundapis"].metadata_json["apim_routes_through_gateway"] is True
        assert services["fundsso"].metadata_json["is_sso_direct"] is True

        slo_keys = {
            (row.service_name, row.sli_type)
            for row in s.query(SloConfigRow).filter_by(application_id=app_id).all()
        }
        assert ("fundapis", "availability") in slo_keys
        assert ("fundapis", "latency") in slo_keys