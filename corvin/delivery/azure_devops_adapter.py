import httpx
import logging
import base64
import itertools
from typing import Optional, Dict, Any
from corvin.core.contracts import InvestigationResult

logger = logging.getLogger(__name__)

_CONFIDENCE_PRIORITY = {"high": 1, "medium": 2, "low": 3}

# Module-level round-robin counters per category
_round_robin_counters: dict[str, int] = {}


def _classify_incident(root_cause: str | None, routing: dict) -> str:
    """
    Classify an incident as 'code', 'devops', or 'default' based on root cause keywords.
    Returns a category key matching assignment_routing config.
    """
    text = (root_cause or "").lower()
    for category, cfg in routing.items():
        if category == "default_assignee":
            continue
        for kw in cfg.get("keywords", []):
            if kw and kw.lower() in text:
                return category
    return "default"


def _pick_assignee(category: str, routing: dict) -> Optional[str]:
    """Round-robin pick from the assignees list for the given category."""
    if category == "default":
        return routing.get("default_assignee")
    cfg = routing.get(category, {})
    assignees = cfg.get("assignees", [])
    if not assignees:
        return routing.get("default_assignee")
    # Deterministic round-robin using module-level counter
    idx = _round_robin_counters.get(category, 0)
    pick = assignees[idx % len(assignees)]
    _round_robin_counters[category] = idx + 1
    return pick


class AzureDevOpsAdapter:
    """
    Adapter for creating and updating Work Items in Azure Boards (Azure DevOps).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.org = config.get("org_name")
        self.project = config.get("project_name")
        self.pat = config.get("pat")
        self.item_type = config.get("work_item_type", "Issue")

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _build_auth_headers(self) -> dict:
        auth_str = f":{self.pat}"
        auth_b64 = base64.b64encode(auth_str.encode("ascii")).decode("ascii")
        return {
            "Authorization": f"Basic {auth_b64}",
        }

    def _is_configured(self) -> bool:
        if not self.enabled or not self.org or not self.project or not self.pat:
            logger.warning("Azure DevOps adapter is disabled or missing credentials.")
            return False
        return True

    # ── Create ────────────────────────────────────────────────────────────────

    def create_incident(self, result: InvestigationResult) -> Optional[str]:
        """
        Creates a new Work Item in Azure Boards from an investigation result.
        Returns the work item ID string, or None on failure / disabled.
        """
        if not self._is_configured():
            return None

        url = (
            f"https://dev.azure.com/{self.org}/{self.project}"
            f"/_apis/wit/workitems/${self.item_type}?api-version=7.1"
        )

        confidence_raw = result.rca.confidence.value if hasattr(result.rca.confidence, "value") else str(result.rca.confidence or "medium")
        confidence = (confidence_raw or "medium").lower()
        priority = _CONFIDENCE_PRIORITY.get(confidence, 2)
        fixed_tags = self.config.get("fixed_tags", "corvin")
        tags = f"{fixed_tags}; {result.request.environment}; {result.request.service_name}; {confidence}"

        headers = {**self._build_auth_headers(), "Content-Type": "application/json-patch+json"}

        _root_cause_text = (result.rca.root_cause or "No root cause identified")
        payload = [
            {
                "op": "add",
                "path": "/fields/System.Title",
                "value": (
                    f"[Corvin] {result.request.service_name} ({result.request.environment})"
                    f" — {_root_cause_text[:80]}"
                ),
            },
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": self._build_description(result),
            },
            # ADO "Issue" type renders description in ReproSteps — set both so it shows regardless of work item type
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.TCM.ReproSteps",
                "value": self._build_description(result),
            },
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Common.Priority",
                "value": priority,
            },
            {
                "op": "add",
                "path": "/fields/System.Tags",
                "value": tags,
            },
        ]

        area_path = self.config.get("area_path")
        if area_path:
            payload.append({
                "op": "add",
                "path": "/fields/System.AreaPath",
                "value": area_path,
            })

        # Auto-assign based on incident category
        routing = self.config.get("assignment_routing", {})
        if routing:
            category = _classify_incident(result.rca.root_cause or None, routing)
            assignee = _pick_assignee(category, routing)
            if assignee:
                payload.append({
                    "op": "add",
                    "path": "/fields/System.AssignedTo",
                    "value": assignee,
                })
                logger.info("Assigning work item to %s (category: %s)", assignee, category)

        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                work_item_id = str(data.get("id"))
                logger.info(
                    "Created Azure Boards work item %s for investigation %s",
                    work_item_id, result.request_id,
                )
                return work_item_id
        except Exception as exc:
            logger.error("Failed to create Azure Boards work item: %s", exc)
            return None

    # ── Update state ──────────────────────────────────────────────────────────

    def update_work_item_state(self, work_item_id: str, state: str) -> bool:
        """
        Update the State field of an existing work item.
        state — e.g. "Active", "Resolved", "Closed"
        Returns True on success, False on failure / disabled.
        """
        if not self._is_configured():
            return False

        url = (
            f"https://dev.azure.com/{self.org}/{self.project}"
            f"/_apis/wit/workitems/{work_item_id}?api-version=7.1"
        )
        headers = {**self._build_auth_headers(), "Content-Type": "application/json-patch+json"}
        payload = [{"op": "replace", "path": "/fields/System.State", "value": state}]

        try:
            with httpx.Client() as client:
                response = client.patch(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info("Updated work item %s state → %s", work_item_id, state)
                return True
        except Exception as exc:
            logger.error("Failed to update work item %s state: %s", work_item_id, exc)
            return False

    # ── Add comment ───────────────────────────────────────────────────────────

    def add_comment(self, work_item_id: str, comment_html: str) -> bool:
        """
        Add an HTML comment to an existing Azure Boards work item.
        Returns True on success, False on failure / disabled.
        """
        if not self._is_configured():
            return False

        url = (
            f"https://dev.azure.com/{self.org}/{self.project}"
            f"/_apis/wit/workitems/{work_item_id}/comments?api-version=7.1-preview.3"
        )
        headers = {**self._build_auth_headers(), "Content-Type": "application/json"}
        payload = {"text": comment_html}

        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info("Added comment to work item %s", work_item_id)
                return True
        except Exception as exc:
            logger.error("Failed to add comment to work item %s: %s", work_item_id, exc)
            return False

    # ── Description builder ───────────────────────────────────────────────────

    def _build_description(self, result: InvestigationResult) -> str:
        """Build a rich HTML description for the Work Item."""
        rca = result.rca
        fix = result.fix_strategy
        confidence_raw_d = rca.confidence.value if hasattr(rca.confidence, "value") else str(rca.confidence or "medium")
        confidence_d = (confidence_raw_d or "medium").upper()

        html = "<h2>Corvin Investigation Report</h2>"
        html += f"<p><b>Investigation ID:</b> {result.request_id}</p>"
        html += f"<p><b>Service:</b> {result.request.service_name} ({result.request.environment})</p>"
        html += f"<p><b>Confidence:</b> {confidence_d}</p>"
        html += f"<p><b>Trigger:</b> {result.request.trigger_source.value}</p>"
        html += "<h3>Root Cause Summary</h3>"
        html += f"<p>{rca.summary}</p>"
        html += "<h3>Root Cause Detail</h3>"
        html += f"<p>{rca.root_cause}</p>"

        if fix.actions:
            html += "<h3>Proposed Fix Actions</h3><ul>"
            for action in fix.actions:
                html += f"<li><b>{action.title}</b>: {action.description}</li>"
            html += "</ul>"

        html += f"<p><i>Generated by Corvin AI SRE Co-Pilot</i></p>"
        return html

