"""
Chaos Monkey (V4.5 Hackathon Feature)

Injects intentional faults into AKS workloads (e.g. killing pods) to trigger
Corvin's auto-healing workflow.
"""

import logging
from corvin.evidence.aks_adapter import AKSAdapter

_log = logging.getLogger(__name__)

class ChaosMonkey:
    def __init__(self, aks_adapter: AKSAdapter | None = None):
        self._aks = aks_adapter or AKSAdapter()

    def inject_fault(self, service_name: str, environment: str, fault_type: str) -> dict[str, str]:
        """
        Inject a fault into the cluster.
        fault_type can be 'kill_pod' or 'latency_spike'
        """
        _log.info("ChaosMonkey injecting %s into %s (%s)", fault_type, service_name, environment)

        if fault_type == "kill_pod":
            # For the hackathon, we reuse the restart_pods logic to simulate a pod crash.
            deleted = self._aks.restart_pods(service_name=service_name)
            return {
                "status": "success" if deleted else "failed",
                "message": f"Killed pods for {service_name}: {deleted}" if deleted else f"Failed to kill pods for {service_name}"
            }
        elif fault_type == "latency_spike":
            # In a real environment we'd use a service mesh or chaos mesh.
            # For the hackathon demo we will simulate by returning a success message.
            return {
                "status": "success",
                "message": f"Injected artificial latency spike on {service_name}"
            }
        else:
            raise ValueError(f"Unknown fault type: {fault_type}")
