"""
AKS context evidence adapter.

Collects pod state, deployment status, and recent events for a named service
in an AKS cluster using the kubernetes Python client.

Config is loaded from config/integrations/aks.yaml with an optional environment
overlay. Supports both local kubeconfig (kube_config_path) and in-cluster mode
(in_cluster: true). API clients are built once in __init__ and reused across
calls.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException

from corvin.core.config_loader import get_env, load_config

logger = logging.getLogger(__name__)


def _pod_to_dict(pod: Any) -> dict[str, Any]:
    """Serialize a kubernetes Pod object to a plain dict for evidence output."""
    containers = []
    if pod.status and pod.status.container_statuses:
        for cs in pod.status.container_statuses:
            state_info: dict[str, Any] = {}
            if cs.state:
                if cs.state.running:
                    state_info = {"running": True}
                elif cs.state.waiting:
                    state_info = {
                        "waiting": True,
                        "reason": cs.state.waiting.reason,
                        "message": cs.state.waiting.message,
                    }
                elif cs.state.terminated:
                    state_info = {
                        "terminated": True,
                        "exit_code": cs.state.terminated.exit_code,
                        "reason": cs.state.terminated.reason,
                    }
            containers.append(
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": state_info,
                }
            )
    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "phase": pod.status.phase if pod.status else None,
        "containers": containers,
    }


def _event_to_dict(event: Any) -> dict[str, Any]:
    """Serialize a kubernetes Event object to a plain dict."""
    return {
        "name": event.metadata.name,
        "reason": event.reason,
        "message": event.message,
        "type": event.type,
        "count": event.count,
        "first_time": str(event.first_timestamp) if event.first_timestamp else None,
        "last_time": str(event.last_timestamp) if event.last_timestamp else None,
    }


def _deployment_to_dict(dep: Any) -> dict[str, Any]:
    """Serialize a kubernetes Deployment object to a plain dict."""
    spec_replicas = dep.spec.replicas if dep.spec else None
    status = dep.status or {}
    return {
        "name": dep.metadata.name,
        "namespace": dep.metadata.namespace,
        "desired_replicas": spec_replicas,
        "ready_replicas": getattr(status, "ready_replicas", None),
        "available_replicas": getattr(status, "available_replicas", None),
        "unavailable_replicas": getattr(status, "unavailable_replicas", None),
    }


class AKSAdapter:
    """Adapter for collecting AKS workload context for a named service."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = (
            config if config is not None else load_config("integrations/aks", get_env())
        )
        # Build API clients once so the connection is reused across calls.
        # Guard construction so that missing kubeconfig in CI/dev doesn't raise.
        self._core_v1: k8s_client.CoreV1Api | None = None
        self._apps_v1: k8s_client.AppsV1Api | None = None
        try:
            if self._config.get("in_cluster", False):
                k8s_config.load_incluster_config()
            else:
                raw_path = self._config.get("kube_config_path", "~/.kube/config")
                kube_path = str(Path(os.path.expanduser(raw_path)))
                k8s_config.load_kube_config(config_file=kube_path)
            self._core_v1 = k8s_client.CoreV1Api()
            self._apps_v1 = k8s_client.AppsV1Api()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AKSAdapter: could not load kubernetes config (will return empty results): %s", exc
            )

    def get_pod_context(
        self,
        service_name: str,
        namespace: str | None = None,
        environment: str | None = None,
    ) -> dict[str, Any]:
        """
        Collect pod status, recent events, and deployment rollout state for a service.

        Args:
            service_name: Kubernetes deployment / service name (used as label selector `app=<name>`).
            namespace:    Kubernetes namespace. Falls back to config `default_namespace`.
            environment:  Optional environment hint (unused internally but kept for interface parity).

        Returns:
            Dict with keys ``pods`` (list), ``events`` (list), ``deployment`` (dict or None).
            Returns ``{}`` on any error.
        """
        if self._core_v1 is None or self._apps_v1 is None:
            logger.warning(
                "AKSAdapter.get_pod_context skipped: clients not configured (service=%s)",
                service_name,
            )
            return {}

        ns = namespace or self._config.get("default_namespace", "default")
        label_selector = f"app={service_name}"

        try:
            # ── Pods ──────────────────────────────────────────────────────────
            pod_list = self._core_v1.list_namespaced_pod(
                namespace=ns, label_selector=label_selector
            )
            pods = [_pod_to_dict(p) for p in pod_list.items]

            # ── Events ────────────────────────────────────────────────────────
            all_events = self._core_v1.list_namespaced_event(namespace=ns)
            events = [
                _event_to_dict(e)
                for e in all_events.items
                if service_name in (e.involved_object.name or "")
            ][:20]

            # ── Deployment ────────────────────────────────────────────────────
            deployment: dict[str, Any] | None = None
            try:
                dep = self._apps_v1.read_namespaced_deployment(
                    name=service_name, namespace=ns
                )
                deployment = _deployment_to_dict(dep)
            except ApiException as dep_exc:
                if dep_exc.status == 404:
                    logger.warning(
                        "AKSAdapter: deployment '%s' not found in namespace '%s'",
                        service_name,
                        ns,
                    )
                else:
                    logger.warning(
                        "AKSAdapter: could not read deployment '%s': %s", service_name, dep_exc
                    )

            return {"pods": pods, "events": events, "deployment": deployment}

        except Exception as exc:
            logger.warning(
                "AKSAdapter.get_pod_context failed for service=%s: %s", service_name, exc
            )
            return {}
