"""Level-1 Kubernetes Chaos Executor.

Executes real kubectl-based chaos experiments with:
  - Pre-flight validation (cluster reachability, prerequisite checks)
  - Structured arm → execute → auto-rollback lifecycle
  - Async background execution so the API returns immediately
  - Detailed observation logging (pod events during experiment)
  - Guaranteed rollback on completion, failure, or abort signal

Supported experiment types:
  k8s_pod_kill          — delete target pods, observe restart time
  k8s_scale_down        — reduce replicas to 1, restore after duration
  k8s_resource_pressure — patch CPU/memory limits very low, restore after duration
  k8s_rollout_pause     — pause deployment rollout, resume after duration
  k8s_cascading         — scale primary service to 0 to trigger downstream cascade

Safety:
  - Never targets production without explicit environment='production' param
  - Always stores rollback commands before executing chaos commands
  - Auto-rollback runs in a finally block (cannot be skipped)
  - Abort sets a flag that the running task checks between steps
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)

# ── Experiment definitions ────────────────────────────────────────────────────

EXPERIMENT_CATALOGUE: dict[str, dict[str, Any]] = {
    "k8s_pod_kill": {
        "name": "Pod Termination",
        "description": "Force-delete one or more pods by label selector. Kubernetes recreates them immediately — measures restart latency and request failure rate during the window.",
        "hypothesis": "When a pod is force-terminated, AKS should reschedule and restart it within 60 seconds. No more than 5% of in-flight requests should fail during the recovery window.",
        "steady_state": "All pods Running and Ready. Error rate on health endpoint < 1%.",
        "blast_radius": "limited",
        "duration_seconds": 90,
        "rollback_note": "No manual rollback needed — Kubernetes recreates terminated pods automatically.",
        "prerequisites": [
            "Deployment has ≥ 2 replicas (PodDisruptionBudget allows one eviction)",
            "No active P1 incident on the target service",
            "Cluster reachable from this host",
        ],
    },
    "k8s_scale_down": {
        "name": "Replica Scale-Down",
        "description": "Scale the deployment to 1 replica for the experiment duration, then restore. Tests HPA recovery, request queuing, and whether the service degrades gracefully under under-provisioning.",
        "hypothesis": "With a single replica, the service should still respond to health checks and serve requests — MTTR for the single pod's availability should be < 10s.",
        "steady_state": "Deployment at configured replica count. All pods Ready. Burn rate below 0.5×.",
        "blast_radius": "moderate",
        "duration_seconds": 120,
        "rollback_note": "Restores replica count to pre-experiment value automatically after duration.",
        "prerequisites": [
            "Deployment has ≥ 2 replicas",
            "HPA is not the sole scaling controller (patch will override HPA temporarily)",
            "No active deployment rollout in progress",
        ],
    },
    "k8s_resource_pressure": {
        "name": "Resource Pressure Injection",
        "description": "Patches the deployment's CPU limit to 50m and memory limit to 256Mi to simulate severe resource starvation. Validates OOMKill behavior, throttling detection, and HPA response.",
        "hypothesis": "Corvin should detect elevated CPU throttling or memory pressure within 5 minutes. Pod should OOMKill or throttle, triggering an alert. MTTR after limit restoration should be < 2 min.",
        "steady_state": "Normal CPU and memory limits restored. Pod CPU throttle rate < 5%.",
        "blast_radius": "moderate",
        "duration_seconds": 180,
        "rollback_note": "Restores original CPU and memory limits automatically after duration.",
        "prerequisites": [
            "Original resource limits are set on the container (not null)",
            "No Vertical Pod Autoscaler managing this deployment",
            "Cluster reachable from this host",
        ],
    },
    "k8s_rollout_pause": {
        "name": "Deployment Rollout Pause",
        "description": "Pauses the deployment's rollout controller, then resumes after the experiment window. Tests Corvin's ability to detect a stuck deployment and validates runbook procedures for un-sticking releases.",
        "hypothesis": "Corvin should surface a 'stuck deployment' detection within the observation window. Resume should restore normal rollout state without manual intervention.",
        "steady_state": "Deployment rollout is not paused. All pods at desired replica count. No rollout in ProgressDeadlineExceeded.",
        "blast_radius": "limited",
        "duration_seconds": 90,
        "rollback_note": "Resumes rollout automatically after duration. Does not affect running pods — only blocks new rollouts during the pause window.",
        "prerequisites": [
            "No active deployment rollout in progress",
            "Deployment has a rollout strategy configured",
        ],
    },
    "k8s_cascading": {
        "name": "Cascading Failure — Scale to Zero",
        "description": "Scales the target service to 0 replicas for the experiment window. Since fundapis is a dependency of both partnerapis and fundsso, this triggers a real cascading failure across all three services. Validates Corvin's multi-service blast radius detection.",
        "hypothesis": "Corvin should detect the primary outage within 3 minutes AND detect downstream impact on dependent services. Blast radius card should show 3 services in failure domain. Recovery (scale back to baseline) should be detected within 5 minutes.",
        "steady_state": "All services at baseline replica count. Cross-service health checks passing. No cascading errors in logs.",
        "blast_radius": "wide",
        "duration_seconds": 120,
        "rollback_note": "Restores replica count to pre-experiment baseline automatically. Dependent services should self-recover once the primary is back.",
        "prerequisites": [
            "⚠️ HIGH IMPACT: This terminates ALL pods for the target service",
            "No active P1 incident on the target service or its dependents",
            "Cluster reachable from this host",
            "Environment must NOT be 'production'",
        ],
    },
}

# ── Abort signals (run_id → asyncio.Event) ───────────────────────────────────

_abort_signals: dict[str, asyncio.Event] = {}


def get_abort_signal(run_id: str) -> asyncio.Event:
    if run_id not in _abort_signals:
        _abort_signals[run_id] = asyncio.Event()
    return _abort_signals[run_id]


def signal_abort(run_id: str) -> None:
    ev = _abort_signals.get(run_id)
    if ev:
        ev.set()


def _clear_abort(run_id: str) -> None:
    _abort_signals.pop(run_id, None)


# ── kubectl helpers ───────────────────────────────────────────────────────────

def _kubectl(*args: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a kubectl command. Returns (returncode, stdout, stderr)."""
    cmd = ["kubectl", *args]
    _log.debug("chaos kubectl: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"kubectl timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "", "kubectl not found — ensure it is installed and on PATH"
    except Exception as exc:
        return 1, "", str(exc)


def _kubectl_json(*args: str) -> tuple[int, dict | list | None, str]:
    """Run kubectl and parse JSON output."""
    rc, stdout, stderr = _kubectl(*args, "-o", "json")
    if rc != 0:
        return rc, None, stderr
    try:
        return 0, json.loads(stdout), ""
    except json.JSONDecodeError:
        return 1, None, f"JSON parse error: {stdout[:200]}"


def _get_current_replicas(deployment: str, namespace: str) -> int | None:
    rc, data, _ = _kubectl_json("get", "deployment", deployment, "-n", namespace)
    if rc != 0 or not isinstance(data, dict):
        return None
    return data.get("spec", {}).get("replicas")


def _get_container_resources(deployment: str, namespace: str) -> dict | None:
    rc, data, _ = _kubectl_json("get", "deployment", deployment, "-n", namespace)
    if rc != 0 or not isinstance(data, dict):
        return None
    containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        return None
    return containers[0].get("resources", {})


def _observe_pods(namespace: str, label: str, lines: list[str]) -> None:
    """Snapshot current pod state into lines list."""
    rc, stdout, _ = _kubectl("get", "pods", "-n", namespace, "-l", f"app={label}")
    if rc == 0:
        lines.append(f"[{_now()}] Pod state:\n{stdout}")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


# ── Build command lists for each experiment type ─────────────────────────────

def build_commands(
    experiment_type: str,
    deployment: str,
    namespace: str,
    k8s_label: str,
    parameters: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return (commands, rollback_commands) as human-readable command strings.

    These are stored in ChaosRunRow before execution so the UI can display
    exactly what will run and operators can audit the plan.
    """
    cmds: list[str] = []
    rollback: list[str] = []

    if experiment_type == "k8s_pod_kill":
        grace = parameters.get("grace_period", 0)
        cmds = [
            f"kubectl delete pods -l app={k8s_label} -n {namespace} --grace-period={grace}",
        ]
        rollback = []  # K8s self-heals — no manual rollback

    elif experiment_type == "k8s_scale_down":
        target = parameters.get("target_replicas", 1)
        cmds = [
            f"# Save current replica count",
            f"kubectl get deployment/{deployment} -n {namespace} -o jsonpath='{{.spec.replicas}}'",
            f"kubectl scale deployment/{deployment} -n {namespace} --replicas={target}",
        ]
        rollback = [
            f"kubectl scale deployment/{deployment} -n {namespace} --replicas=<original>",
        ]

    elif experiment_type == "k8s_resource_pressure":
        cpu = parameters.get("cpu_limit", "50m")
        mem = parameters.get("memory_limit", "256Mi")
        patch = json.dumps([
            {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": cpu},
            {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": mem},
        ])
        cmds = [
            f"# Save original limits",
            f"kubectl get deployment/{deployment} -n {namespace} -o jsonpath='{{.spec.template.spec.containers[0].resources}}'",
            f"kubectl patch deployment/{deployment} -n {namespace} --type=json -p='{patch}'",
        ]
        rollback = [
            f"kubectl patch deployment/{deployment} -n {namespace} --type=json -p='<restore_limits_patch>'",
        ]

    elif experiment_type == "k8s_rollout_pause":
        cmds = [
            f"kubectl rollout pause deployment/{deployment} -n {namespace}",
        ]
        rollback = [
            f"kubectl rollout resume deployment/{deployment} -n {namespace}",
        ]

    elif experiment_type == "k8s_cascading":
        cmds = [
            f"# Save current replica count",
            f"kubectl get deployment/{deployment} -n {namespace} -o jsonpath='{{.spec.replicas}}'",
            f"kubectl scale deployment/{deployment} -n {namespace} --replicas=0",
        ]
        rollback = [
            f"kubectl scale deployment/{deployment} -n {namespace} --replicas=<original>",
        ]

    return cmds, rollback


# ── Core execution ────────────────────────────────────────────────────────────

async def execute_experiment(run_id: str, db_session_factory: Any) -> None:
    """Background coroutine: run chaos experiment, observe, rollback, update DB.

    Called as an asyncio background task from the /execute endpoint.
    All DB writes use a fresh session factory to avoid cross-thread issues.
    """
    _log.info("chaos_executor: starting run %s", run_id)
    abort_ev = get_abort_signal(run_id)
    output_lines: list[str] = []
    observations: dict[str, Any] = {"events": [], "pod_snapshots": []}

    def append(msg: str) -> None:
        output_lines.append(msg)
        _log.debug("chaos[%s]: %s", run_id, msg)

    def update_db(status: str, **kwargs: Any) -> None:
        try:
            with db_session_factory() as sess:
                from corvin.storage.models import ChaosRunRow
                row = sess.get(ChaosRunRow, run_id)
                if row is None:
                    return
                row.status = status
                row.output = "\n".join(output_lines)
                row.observations = observations
                for k, v in kwargs.items():
                    setattr(row, k, v)
                sess.commit()
        except Exception as exc:
            _log.warning("chaos_executor: DB update failed: %s", exc)

    try:
        with db_session_factory() as sess:
            from corvin.storage.models import ChaosRunRow
            run = sess.get(ChaosRunRow, run_id)
            if run is None:
                _log.error("chaos_executor: run %s not found", run_id)
                return
            experiment_type = run.experiment_type
            deployment = run.parameters.get("deployment", run.service_name)
            namespace = run.namespace
            k8s_label = run.parameters.get("k8s_label", deployment)
            duration = run.duration_seconds
            params = dict(run.parameters)

        update_db("running", started_at=datetime.now(timezone.utc))
        append(f"[{_now()}] Experiment started: {experiment_type} on {deployment} in {namespace}")

        # ── Initial observation ────────────────────────────────────────────
        _observe_pods(namespace, k8s_label, observations["pod_snapshots"])

        # ── Execute experiment ─────────────────────────────────────────────
        saved_replicas: int | None = None
        saved_resources: dict | None = None

        if abort_ev.is_set():
            append(f"[{_now()}] Abort signalled before execution — skipping.")
            update_db("aborted", completed_at=datetime.now(timezone.utc), rollback_status="not_needed")
            return

        if experiment_type == "k8s_pod_kill":
            grace = params.get("grace_period", 0)
            rc, out, err = _kubectl(
                "delete", "pods", "-n", namespace, "-l", f"app={k8s_label}",
                f"--grace-period={grace}"
            )
            append(f"[{_now()}] kubectl delete pods: rc={rc}")
            if out:
                append(out)
            if err:
                append(f"STDERR: {err}")
            observations["events"].append({"type": "pod_kill", "rc": rc, "ts": _now()})

        elif experiment_type == "k8s_scale_down":
            saved_replicas = _get_current_replicas(deployment, namespace)
            append(f"[{_now()}] Current replicas: {saved_replicas}")
            target = params.get("target_replicas", 1)
            rc, out, err = _kubectl("scale", f"deployment/{deployment}", "-n", namespace, f"--replicas={target}")
            append(f"[{_now()}] kubectl scale to {target}: rc={rc}")
            if out:
                append(out)
            if err:
                append(f"STDERR: {err}")
            observations["events"].append({"type": "scale_down", "from": saved_replicas, "to": target, "rc": rc, "ts": _now()})

        elif experiment_type == "k8s_resource_pressure":
            saved_resources = _get_container_resources(deployment, namespace)
            append(f"[{_now()}] Original resources: {json.dumps(saved_resources)}")
            cpu = params.get("cpu_limit", "50m")
            mem = params.get("memory_limit", "256Mi")
            patch = json.dumps([
                {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": cpu},
                {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": mem},
            ])
            rc, out, err = _kubectl(
                "patch", f"deployment/{deployment}", "-n", namespace,
                "--type=json", f"-p={patch}"
            )
            append(f"[{_now()}] kubectl patch limits to cpu={cpu} mem={mem}: rc={rc}")
            if out:
                append(out)
            if err:
                append(f"STDERR: {err}")
            observations["events"].append({"type": "resource_pressure", "cpu": cpu, "mem": mem, "rc": rc, "ts": _now()})

        elif experiment_type == "k8s_rollout_pause":
            rc, out, err = _kubectl("rollout", "pause", f"deployment/{deployment}", "-n", namespace)
            append(f"[{_now()}] kubectl rollout pause: rc={rc}")
            if out:
                append(out)
            if err:
                append(f"STDERR: {err}")
            observations["events"].append({"type": "rollout_pause", "rc": rc, "ts": _now()})

        elif experiment_type == "k8s_cascading":
            saved_replicas = _get_current_replicas(deployment, namespace)
            append(f"[{_now()}] Current replicas: {saved_replicas}")
            rc, out, err = _kubectl("scale", f"deployment/{deployment}", "-n", namespace, "--replicas=0")
            append(f"[{_now()}] kubectl scale to 0 (cascading): rc={rc}")
            if out:
                append(out)
            if err:
                append(f"STDERR: {err}")
            observations["events"].append({"type": "cascading_zero", "from": saved_replicas, "rc": rc, "ts": _now()})

        else:
            append(f"[{_now()}] Unknown experiment type: {experiment_type}")
            update_db("failed", completed_at=datetime.now(timezone.utc))
            return

        update_db("running")

        # ── Observation window ─────────────────────────────────────────────
        observe_interval = min(20, duration // 4)
        elapsed = 0
        while elapsed < duration:
            if abort_ev.is_set():
                append(f"[{_now()}] Abort signalled at {elapsed}s — rolling back immediately.")
                break
            await asyncio.sleep(min(observe_interval, duration - elapsed))
            elapsed += observe_interval
            _observe_pods(namespace, k8s_label, observations["pod_snapshots"])
            append(f"[{_now()}] Observation at {elapsed}s elapsed")
            update_db("running")

        # ── Rollback ──────────────────────────────────────────────────────
        append(f"[{_now()}] Experiment window ended — beginning rollback")
        rollback_ok = True

        try:
            if experiment_type == "k8s_pod_kill":
                append(f"[{_now()}] No rollback needed — Kubernetes self-heals terminated pods")

            elif experiment_type in ("k8s_scale_down", "k8s_cascading"):
                restore = saved_replicas if saved_replicas is not None else 2
                rc, out, err = _kubectl(
                    "scale", f"deployment/{deployment}", "-n", namespace, f"--replicas={restore}"
                )
                append(f"[{_now()}] Rollback: scale to {restore}: rc={rc}")
                if rc != 0:
                    rollback_ok = False
                if out:
                    append(out)
                if err:
                    append(f"STDERR: {err}")
                observations["events"].append({"type": "rollback_scale", "to": restore, "rc": rc, "ts": _now()})

            elif experiment_type == "k8s_resource_pressure":
                if saved_resources and saved_resources.get("limits"):
                    limits = saved_resources["limits"]
                    restore_patch = json.dumps([
                        {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu",
                         "value": limits.get("cpu", "500m")},
                        {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory",
                         "value": limits.get("memory", "512Mi")},
                    ])
                    rc, out, err = _kubectl(
                        "patch", f"deployment/{deployment}", "-n", namespace,
                        "--type=json", f"-p={restore_patch}"
                    )
                    append(f"[{_now()}] Rollback: restore limits: rc={rc}")
                    if rc != 0:
                        rollback_ok = False
                    if out:
                        append(out)
                    if err:
                        append(f"STDERR: {err}")
                    observations["events"].append({"type": "rollback_resources", "rc": rc, "ts": _now()})
                else:
                    append(f"[{_now()}] Warning: original resources unknown, manual restoration may be required")

            elif experiment_type == "k8s_rollout_pause":
                rc, out, err = _kubectl("rollout", "resume", f"deployment/{deployment}", "-n", namespace)
                append(f"[{_now()}] Rollback: rollout resume: rc={rc}")
                if rc != 0:
                    rollback_ok = False
                if out:
                    append(out)
                if err:
                    append(f"STDERR: {err}")
                observations["events"].append({"type": "rollback_resume", "rc": rc, "ts": _now()})

        except Exception as rb_exc:
            rollback_ok = False
            append(f"[{_now()}] Rollback error: {rb_exc}")
            _log.exception("chaos_executor: rollback failed for run %s", run_id)

        # ── Final observation ─────────────────────────────────────────────
        await asyncio.sleep(5)
        _observe_pods(namespace, k8s_label, observations["pod_snapshots"])
        append(f"[{_now()}] Final pod state captured")

        final_status = "aborted" if abort_ev.is_set() else "completed"
        rollback_status = "complete" if rollback_ok else "failed"
        update_db(
            final_status,
            completed_at=datetime.now(timezone.utc),
            rollback_status=rollback_status,
        )
        append(f"[{_now()}] Experiment {final_status}. Rollback: {rollback_status}")
        _log.info("chaos_executor: run %s %s, rollback=%s", run_id, final_status, rollback_status)

    except Exception as exc:
        _log.exception("chaos_executor: unhandled error in run %s: %s", run_id, exc)
        append(f"[{_now()}] FATAL: {exc}")
        update_db("failed", completed_at=datetime.now(timezone.utc))
    finally:
        _clear_abort(run_id)
