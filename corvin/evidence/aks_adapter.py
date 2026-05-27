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

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_deployment_name(self, service_name: str, namespace: str) -> str:
        """Return the actual deployment name for *service_name* in *namespace*.

        Tries the bare name first; if a 404 is returned, tries the
        ``{namespace}-{service_name}`` convention used by many Helm charts.
        Falls back to the bare name if both lookups fail (so the caller sees
        a meaningful 404 error rather than a silent empty result).
        """
        if self._apps_v1 is None:
            return service_name
        try:
            self._apps_v1.read_namespaced_deployment(name=service_name, namespace=namespace)
            return service_name
        except ApiException as exc:
            if exc.status == 404:
                prefixed = f"{namespace}-{service_name}"
                try:
                    self._apps_v1.read_namespaced_deployment(name=prefixed, namespace=namespace)
                    return prefixed
                except ApiException:
                    pass
        return service_name

    def _resolve_workload(
        self, service_name: str, namespace: str
    ) -> tuple[str, str]:
        """Resolve *service_name* to its backing workload (Deployment or DaemonSet).

        Strategy:
        1. Try as a Deployment directly (bare name, then ``{ns}-{name}``).
        2. If not a Deployment, try as a DaemonSet (bare name, then ``{ns}-{name}``).
        3. If neither, check if *service_name* is a Service — read its selector
           and find the owning Deployment or DaemonSet from the pods it selects.

        Returns ``(workload_name, kind)`` where kind is ``"deployment"`` or
        ``"daemonset"``.  Falls back to ``(service_name, "deployment")`` when
        nothing is found so the caller gets a clear 404 on the patch call.
        """
        if self._apps_v1 is None or self._core_v1 is None:
            return service_name, "deployment"

        prefixed = f"{namespace}-{service_name}"

        # 1. Check Deployment (bare → prefixed)
        for name in (service_name, prefixed):
            try:
                self._apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                return name, "deployment"
            except ApiException:
                pass

        # 2. Check DaemonSet (bare → prefixed)
        for name in (service_name, prefixed):
            try:
                self._apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
                return name, "daemonset"
            except ApiException:
                pass

        # 3. Check if it's a Service — follow its selector to the owner
        try:
            svc = self._core_v1.read_namespaced_service(name=service_name, namespace=namespace)
            selector = svc.spec.selector or {}
            if selector:
                label_str = ",".join(f"{k}={v}" for k, v in selector.items())
                pods = self._core_v1.list_namespaced_pod(
                    namespace=namespace, label_selector=label_str
                )
                for pod in (pods.items or []):
                    for owner in (pod.metadata.owner_references or []):
                        if owner.kind == "ReplicaSet":
                            # ReplicaSet → owned by a Deployment
                            try:
                                rs = self._apps_v1.read_namespaced_replica_set(
                                    name=owner.name, namespace=namespace
                                )
                                for rs_owner in (rs.metadata.owner_references or []):
                                    if rs_owner.kind == "Deployment":
                                        return rs_owner.name, "deployment"
                            except ApiException:
                                pass
                        elif owner.kind == "DaemonSet":
                            return owner.name, "daemonset"
                    break  # only need the first pod's owner
        except ApiException:
            pass

        return service_name, "deployment"

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
        dep_name = self._resolve_deployment_name(service_name, ns)
        prefixed_name = f"{ns}-{service_name}"

        try:
            # ── Pods ──────────────────────────────────────────────────────────
            # Try bare label first; fall back to namespace-prefixed label.
            pod_list = self._core_v1.list_namespaced_pod(
                namespace=ns, label_selector=f"app={service_name}"
            )
            if not pod_list.items:
                pod_list = self._core_v1.list_namespaced_pod(
                    namespace=ns, label_selector=f"app={prefixed_name}"
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
                dep = self._apps_v1.read_namespaced_deployment(name=dep_name, namespace=ns)
                deployment = _deployment_to_dict(dep)
            except ApiException as dep_exc:
                logger.warning(
                    "AKSAdapter: could not read deployment '%s': %s", dep_name, dep_exc
                )

            return {"pods": pods, "events": events, "deployment": deployment}

        except Exception as exc:
            logger.warning(
                "AKSAdapter.get_pod_context failed for service=%s: %s", service_name, exc
            )
            return {}

    # ── Execution methods (V2 — require ApprovalStatus.APPROVED) ─────────────

    def restart_pods(
        self,
        service_name: str,
        namespace: str | None = None,
    ) -> list[str]:
        """Perform a rolling restart of the workload backing *service_name*.

        Primary strategy: resolve the actual workload (Deployment or DaemonSet)
        — even if *service_name* is a Service name — then patch its pod template
        with a restart annotation (equivalent to ``kubectl rollout restart``).

        Fallback: if the workload cannot be found, fall back to deleting
        individual pods matched by label selector.

        Returns a list of restarted workload/pod names on success.
        Returns an empty list if clients are not configured or on error.
        """
        if self._core_v1 is None or self._apps_v1 is None:
            logger.warning(
                "AKSAdapter.restart_pods skipped: clients not configured (service=%s)",
                service_name,
            )
            return []

        ns = namespace or self._config.get("default_namespace", "default")
        workload_name, workload_kind = self._resolve_workload(service_name, ns)

        # ── Primary: rollout restart via workload patch ───────────────────
        try:
            from datetime import datetime, timezone

            restart_annotation = datetime.now(timezone.utc).isoformat()
            patch_body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": restart_annotation
                            }
                        }
                    }
                }
            }
            if workload_kind == "daemonset":
                self._apps_v1.patch_namespaced_daemon_set(
                    name=workload_name, namespace=ns, body=patch_body
                )
            else:
                self._apps_v1.patch_namespaced_deployment(
                    name=workload_name, namespace=ns, body=patch_body
                )
            logger.info(
                "AKSAdapter.restart_pods: rollout restart triggered for %s/%s in %s",
                workload_kind, workload_name, ns,
            )
            return [f"{workload_kind}/{workload_name} (rollout restart)"]
        except ApiException as exc:
            if exc.status == 404:
                logger.info(
                    "AKSAdapter.restart_pods: %s '%s' not found in %s, "
                    "falling back to pod deletion by label",
                    workload_kind, workload_name, ns,
                )
            else:
                logger.warning(
                    "AKSAdapter.restart_pods: rollout restart failed for %s/%s: %s, "
                    "falling back to pod deletion by label",
                    workload_kind, workload_name, exc,
                )

        # ── Fallback: delete pods by label selector ───────────────────────
        prefixed_name = f"{ns}-{service_name}"
        deleted: list[str] = []

        try:
            pod_list = self._core_v1.list_namespaced_pod(
                namespace=ns, label_selector=f"app={service_name}"
            )
            if not pod_list.items:
                pod_list = self._core_v1.list_namespaced_pod(
                    namespace=ns, label_selector=f"app={prefixed_name}"
                )
            if not pod_list.items:
                pod_list = self._core_v1.list_namespaced_pod(
                    namespace=ns, label_selector=f"app.kubernetes.io/name={service_name}"
                )
            for pod in pod_list.items:
                pod_name = pod.metadata.name
                self._core_v1.delete_namespaced_pod(name=pod_name, namespace=ns)
                deleted.append(pod_name)
                logger.info(
                    "AKSAdapter.restart_pods: deleted pod %s in namespace %s", pod_name, ns
                )
        except Exception as exc:
            logger.warning(
                "AKSAdapter.restart_pods failed for service=%s: %s", service_name, exc
            )

        return deleted

    def list_all_pods(self, namespace: str | None = None) -> dict[str, Any]:
        """List ALL pods in the namespace, grouped by service (via the `app` label).

        Returns a dict with key ``services``: a list of dicts, each with:
          - ``name``: service/deployment label value
          - ``namespace``: kubernetes namespace
          - ``pods``: list of pod dicts (same format as get_pod_context)
          - ``status``: 'hot' | 'recovering' | 'high' (healthy)

        Returns ``{"services": []}`` if clients are not configured or on error.
        """
        if self._core_v1 is None:
            logger.warning("AKSAdapter.list_all_pods skipped: clients not configured")
            return {"services": []}

        ns = namespace or self._config.get("default_namespace", "default")
        try:
            pod_list = self._core_v1.list_namespaced_pod(namespace=ns)
        except Exception as exc:
            logger.warning("AKSAdapter.list_all_pods failed: %s", exc)
            return {"services": []}

        # Group pods by their `app` label (fall back to deployment prefix)
        by_service: dict[str, list[dict[str, Any]]] = {}
        for pod in pod_list.items:
            labels = pod.metadata.labels or {}
            svc = labels.get("app") or labels.get("app.kubernetes.io/name") or ""
            if not svc:
                # Derive from pod name: strip last two hash segments
                parts = (pod.metadata.name or "").split("-")
                svc = "-".join(parts[:-2]) if len(parts) > 2 else pod.metadata.name
            by_service.setdefault(svc, []).append(_pod_to_dict(pod))

        services = []
        for svc_name, pods in by_service.items():
            # Determine service status from pod health
            any_failed = any(
                p.get("phase") not in ("Running", "Succeeded") or
                any(not c.get("ready", True) for c in p.get("containers", []))
                for p in pods
            )
            any_restarting = any(
                any(c.get("restart_count", 0) > 3 for c in p.get("containers", []))
                for p in pods
            )
            status = "hot" if any_failed else ("recovering" if any_restarting else "high")
            services.append({
                "name": svc_name,
                "namespace": ns,
                "pods": pods,
                "status": status,
            })

        return {"services": services}

    def rollback_deployment(
        self,
        service_name: str,
        namespace: str | None = None,
        revision: int | None = None,
    ) -> bool:
        """Roll back *service_name* deployment to a previous revision.

        Uses a patch to trigger a rollout undo via the ``rollout.kubernetes.io/revision``
        annotation.  When *revision* is ``None`` the controller rolls back to the
        previous stable revision automatically.

        Returns ``True`` on success, ``False`` on any error.
        """
        if self._apps_v1 is None:
            logger.warning(
                "AKSAdapter.rollback_deployment skipped: clients not configured (service=%s)",
                service_name,
            )
            return False

        ns = namespace or self._config.get("default_namespace", "default")
        dep_name = self._resolve_deployment_name(service_name, ns)

        try:
            # Annotate the deployment to trigger a rollback.
            # kubectl rollout undo sets rollout.kubernetes.io/revision to "" (empty string)
            # to roll to previous, or to the specific revision number.
            revision_value = "" if revision is None else str(revision)
            patch_body = {
                "metadata": {
                    "annotations": {
                        "corvin.io/rollback-requested": "true",
                        "rollout.kubernetes.io/revision": revision_value,
                    }
                }
            }
            self._apps_v1.patch_namespaced_deployment(
                name=dep_name, namespace=ns, body=patch_body
            )
            logger.info(
                "AKSAdapter.rollback_deployment: triggered rollback for %s in namespace %s "
                "(revision=%s)",
                service_name,
                ns,
                revision_value or "previous",
            )
            return True
        except Exception as exc:
            logger.warning(
                "AKSAdapter.rollback_deployment failed for service=%s: %s", service_name, exc
            )
            return False

    def scale_deployment(
        self,
        service_name: str,
        replicas: int,
        namespace: str | None = None,
    ) -> bool:
        """Scale *service_name* deployment to *replicas*.

        Returns ``True`` on success, ``False`` on any error.
        """
        if self._apps_v1 is None:
            logger.warning(
                "AKSAdapter.scale_deployment skipped: clients not configured (service=%s)",
                service_name,
            )
            return False

        ns = namespace or self._config.get("default_namespace", "default")
        dep_name = self._resolve_deployment_name(service_name, ns)

        try:
            patch_body = {"spec": {"replicas": replicas}}
            self._apps_v1.patch_namespaced_deployment_scale(
                name=dep_name, namespace=ns, body=patch_body
            )
            logger.info(
                "AKSAdapter.scale_deployment: scaled %s to %d replicas in namespace %s",
                service_name,
                replicas,
                ns,
            )
            return True
        except Exception as exc:
            logger.warning(
                "AKSAdapter.scale_deployment failed for service=%s replicas=%d: %s",
                service_name,
                replicas,
                exc,
            )
            return False

    # ── Log retrieval (V3.9+) ─────────────────────────────────────────────────

    def get_pod_logs(
        self,
        service_name: str,
        namespace: str | None = None,
        tail_lines: int = 60,
        since_seconds: int | None = 30,
    ) -> list[dict[str, str]]:
        """Fetch recent logs from all pods matching *service_name*.

        Returns a list of ``{"pod": "<name>", "logs": "<text>"}`` dicts.
        Returns an empty list if clients are not configured or on error.
        """
        if self._core_v1 is None:
            logger.warning(
                "AKSAdapter.get_pod_logs skipped: clients not configured (service=%s)",
                service_name,
            )
            return []

        ns = namespace or self._config.get("default_namespace", "default")
        prefixed_name = f"{ns}-{service_name}"
        results: list[dict[str, str]] = []

        try:
            pod_list = self._core_v1.list_namespaced_pod(
                namespace=ns, label_selector=f"app={service_name}"
            )
            if not pod_list.items:
                pod_list = self._core_v1.list_namespaced_pod(
                    namespace=ns, label_selector=f"app={prefixed_name}"
                )
            for pod in pod_list.items:
                pod_name = pod.metadata.name
                try:
                    log_text = self._core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=ns,
                        tail_lines=tail_lines,
                        since_seconds=since_seconds,
                    )
                    results.append({"pod": pod_name, "logs": log_text or ""})
                except Exception as exc:
                    logger.warning(
                        "AKSAdapter.get_pod_logs: failed reading logs for pod %s: %s",
                        pod_name, exc,
                    )
                    results.append({"pod": pod_name, "logs": f"(log read failed: {exc})"})
        except Exception as exc:
            logger.warning(
                "AKSAdapter.get_pod_logs failed for service=%s: %s", service_name, exc,
            )

        return results
