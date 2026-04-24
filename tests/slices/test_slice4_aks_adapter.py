"""
Slice 4 – AKS context adapter tests.

Uses unittest.mock.patch to mock the kubernetes API clients and config loader
so no live cluster is required.  Tests cover:
  - Successful response returns dict with 'pods', 'events', 'deployment' keys.
  - pods list includes serialized pod data.
  - events list is filtered to the named service.
  - API exception on pod list returns empty dict (graceful degradation).
  - Missing deployment (404) returns partial dict without crashing.
  - No kubeconfig (clients None) returns empty dict.
  - namespace falls back to config default_namespace when not provided.
  - explicit namespace is forwarded to kubernetes API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from corvin.evidence.aks_adapter import AKSAdapter

# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------

_CONFIG = {
    "cluster_name": "test-aks",
    "resource_group": "test-rg",
    "kube_config_path": "~/.kube/config",
    "default_namespace": "services",
    "events_lookback_minutes": 60,
}


# ---------------------------------------------------------------------------
# Helpers to build mock kubernetes objects
# ---------------------------------------------------------------------------


def _make_pod(name: str, phase: str = "Running", restart_count: int = 0) -> MagicMock:
    cs = MagicMock()
    cs.name = "app"
    cs.ready = True
    cs.restart_count = restart_count
    cs.state.running = MagicMock()
    cs.state.waiting = None
    cs.state.terminated = None

    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = "services"
    pod.status.phase = phase
    pod.status.container_statuses = [cs]
    return pod


def _make_event(name: str, reason: str, message: str, involved_object_name: str) -> MagicMock:
    event = MagicMock()
    event.metadata.name = name
    event.reason = reason
    event.message = message
    event.type = "Warning"
    event.count = 3
    event.first_timestamp = None
    event.last_timestamp = None
    event.involved_object.name = involved_object_name
    return event


def _make_deployment(name: str, desired: int = 2, ready: int = 2) -> MagicMock:
    dep = MagicMock()
    dep.metadata.name = name
    dep.metadata.namespace = "services"
    dep.spec.replicas = desired
    dep.status.ready_replicas = ready
    dep.status.available_replicas = ready
    dep.status.unavailable_replicas = desired - ready if desired > ready else None
    return dep


def _build_adapter_with_mocks(core_v1, apps_v1):
    """Create an AKSAdapter whose API clients are replaced with the given mocks."""
    with patch("corvin.evidence.aks_adapter.k8s_config"), \
         patch("corvin.evidence.aks_adapter.k8s_client") as MockK8s:
        MockK8s.CoreV1Api.return_value = core_v1
        MockK8s.AppsV1Api.return_value = apps_v1
        adapter = AKSAdapter(config=_CONFIG)
    return adapter


# ---------------------------------------------------------------------------
# Successful query tests
# ---------------------------------------------------------------------------


def test_get_pod_context_returns_expected_keys():
    """Successful call returns a dict with 'pods', 'events', 'deployment' keys."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = [_make_pod("order-service-abc")]
    core_v1.list_namespaced_event.return_value.items = []
    apps_v1.read_namespaced_deployment.return_value = _make_deployment("order-service")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    result = adapter.get_pod_context("order-service")

    assert isinstance(result, dict)
    assert set(result.keys()) == {"pods", "events", "deployment"}


def test_get_pod_context_pods_are_serialized():
    """Pod objects are serialized to plain dicts with name, phase, containers."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = [
        _make_pod("order-service-abc", phase="Running", restart_count=5),
    ]
    core_v1.list_namespaced_event.return_value.items = []
    apps_v1.read_namespaced_deployment.return_value = _make_deployment("order-service")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    result = adapter.get_pod_context("order-service")

    assert len(result["pods"]) == 1
    pod = result["pods"][0]
    assert pod["name"] == "order-service-abc"
    assert pod["phase"] == "Running"
    assert pod["containers"][0]["restart_count"] == 5


def test_get_pod_context_events_filtered_to_service():
    """Only events whose involved_object.name contains the service name are returned."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = []
    core_v1.list_namespaced_event.return_value.items = [
        _make_event("evt-1", "BackOff", "CrashLoopBackOff", "order-service-abc"),
        _make_event("evt-2", "Pulled", "Image pulled", "unrelated-service-xyz"),
    ]
    apps_v1.read_namespaced_deployment.return_value = _make_deployment("order-service")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    result = adapter.get_pod_context("order-service")

    # Only the event for "order-service-abc" should be included
    assert len(result["events"]) == 1
    assert result["events"][0]["reason"] == "BackOff"


def test_get_pod_context_deployment_is_serialized():
    """Deployment object is serialized with desired/ready/unavailable replica counts."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = []
    core_v1.list_namespaced_event.return_value.items = []
    apps_v1.read_namespaced_deployment.return_value = _make_deployment(
        "order-service", desired=3, ready=1
    )

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    result = adapter.get_pod_context("order-service")

    dep = result["deployment"]
    assert dep["name"] == "order-service"
    assert dep["desired_replicas"] == 3
    assert dep["ready_replicas"] == 1


# ---------------------------------------------------------------------------
# Error / degradation tests
# ---------------------------------------------------------------------------


def test_get_pod_context_api_exception_returns_empty_dict():
    """If list_namespaced_pod raises ApiException, get_pod_context returns {}."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.side_effect = ApiException(status=500, reason="Internal Error")
    apps_v1.read_namespaced_deployment.return_value = _make_deployment("order-service")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    result = adapter.get_pod_context("order-service")

    assert result == {}


def test_get_pod_context_missing_deployment_returns_partial_dict():
    """If deployment is not found (404), return pods and events without crashing."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = [_make_pod("order-service-abc")]
    core_v1.list_namespaced_event.return_value.items = []
    apps_v1.read_namespaced_deployment.side_effect = ApiException(status=404, reason="Not Found")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    result = adapter.get_pod_context("order-service")

    assert "pods" in result
    assert "events" in result
    assert result["deployment"] is None


def test_get_pod_context_unconfigured_clients_returns_empty_dict():
    """When kubernetes config fails to load, get_pod_context returns {}."""
    with patch("corvin.evidence.aks_adapter.k8s_config") as mock_cfg:
        mock_cfg.load_kube_config.side_effect = Exception("kubeconfig not found")
        adapter = AKSAdapter(config=_CONFIG)

    result = adapter.get_pod_context("order-service")
    assert result == {}


# ---------------------------------------------------------------------------
# Namespace / config tests
# ---------------------------------------------------------------------------


def test_get_pod_context_uses_default_namespace_from_config():
    """When namespace is not passed, the config default_namespace is used."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = []
    core_v1.list_namespaced_event.return_value.items = []
    apps_v1.read_namespaced_deployment.return_value = _make_deployment("svc")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    adapter.get_pod_context("svc")

    call_kwargs = core_v1.list_namespaced_pod.call_args.kwargs
    assert call_kwargs["namespace"] == "services"  # from _CONFIG["default_namespace"]


def test_get_pod_context_explicit_namespace_is_forwarded():
    """When namespace is explicitly provided, it is forwarded to kubernetes API calls."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value.items = []
    core_v1.list_namespaced_event.return_value.items = []
    apps_v1.read_namespaced_deployment.return_value = _make_deployment("svc")

    adapter = _build_adapter_with_mocks(core_v1, apps_v1)
    adapter.get_pod_context("svc", namespace="production")

    call_kwargs = core_v1.list_namespaced_pod.call_args.kwargs
    assert call_kwargs["namespace"] == "production"
