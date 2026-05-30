"""
F11 — IDE Integration Service.

Provides a structured context API for VS Code / IDE extensions to consume.
Designed to power a VS Code Copilot Chat participant (`@corvin`) that can:

  • Get active investigations + status for current service context
  • Retrieve investigation summaries optimized for inline display
  • Get contextual fix suggestions based on the file/service being edited
  • Query Corvin knowledge base from within the editor
  • Get deployment safety signals before committing

This module produces compact, IDE-friendly payloads (not full HTML/Markdown
documents) — optimized for rendering in VS Code chat panels and hover cards.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult
from corvin.storage.repository import InvestigationRepository

_log = logging.getLogger(__name__)


@dataclass
class IDEContext:
    """Compact context payload for IDE consumption."""
    service_name: str
    active_investigations: list[dict[str, Any]] = field(default_factory=list)
    recent_incidents: list[dict[str, Any]] = field(default_factory=list)
    deployment_safety: dict[str, Any] = field(default_factory=dict)
    knowledge_snippets: list[dict[str, str]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "active_investigations": self.active_investigations,
            "recent_incidents": self.recent_incidents,
            "deployment_safety": self.deployment_safety,
            "knowledge_snippets": self.knowledge_snippets,
            "generated_at": self.generated_at,
        }


@dataclass
class IDEFixSuggestion:
    """Context-aware fix suggestion for the IDE."""
    file_path: str
    service_name: str
    suggestion: str
    rationale: str
    related_investigation_id: str | None = None
    confidence: str = "medium"
    code_snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "service_name": self.service_name,
            "suggestion": self.suggestion,
            "rationale": self.rationale,
            "related_investigation_id": self.related_investigation_id,
            "confidence": self.confidence,
            "code_snippet": self.code_snippet,
        }


@dataclass
class DeploySafetySignal:
    """Pre-deployment safety check result."""
    safe_to_deploy: bool
    service_name: str
    active_incident_count: int
    recent_failure_count: int
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe_to_deploy": self.safe_to_deploy,
            "service_name": self.service_name,
            "active_incident_count": self.active_incident_count,
            "recent_failure_count": self.recent_failure_count,
            "warnings": self.warnings,
            "blockers": self.blockers,
        }


class IDEIntegrationService:
    """
    Provides IDE-optimized investigation context and suggestions.

    Designed to be consumed by VS Code extensions, MCP servers,
    or Copilot Chat participants.
    """

    def __init__(self, repository: InvestigationRepository | None = None) -> None:
        self._repo = repository
        self._config = load_config("models/llm", get_env())

    def _get_model(self) -> str:
        return self._config.get("fallback_model", "azure/gpt-4.1-mini")

    def get_context(self, service_name: str, repo: InvestigationRepository | None = None) -> IDEContext:
        """
        Get full IDE context for a service.

        Returns active investigations, recent incidents, deployment safety,
        and relevant knowledge snippets.
        """
        repository = repo or self._repo
        if not repository:
            return IDEContext(service_name=service_name)

        # Active investigations (last 24h, not completed)
        active = repository.list_recent(hours=24, service_filter=service_name)
        active_items = []
        for inv in (active or [])[:5]:
            active_items.append({
                "id": inv.get("id", inv.get("request_id", "")),
                "status": inv.get("status", "investigating"),
                "alert_summary": inv.get("alert_summary", "")[:100],
                "started_at": inv.get("created_at", ""),
                "confidence": inv.get("confidence", "unknown"),
            })

        # Recent completed investigations (last 7 days)
        recent = repository.list_recent(hours=168, service_filter=service_name)
        recent_items = []
        for inv in (recent or [])[:10]:
            recent_items.append({
                "id": inv.get("id", inv.get("request_id", "")),
                "root_cause": inv.get("root_cause", "")[:80],
                "completed_at": inv.get("completed_at", ""),
                "confidence": inv.get("confidence", "unknown"),
            })

        # Deployment safety signal
        safety = self._check_deploy_safety(service_name, active_items, recent_items)

        return IDEContext(
            service_name=service_name,
            active_investigations=active_items,
            recent_incidents=recent_items,
            deployment_safety=safety.to_dict(),
        )

    def _check_deploy_safety(
        self,
        service_name: str,
        active: list[dict[str, Any]],
        recent: list[dict[str, Any]],
    ) -> DeploySafetySignal:
        """Evaluate whether it's safe to deploy to the given service."""
        warnings = []
        blockers = []
        active_count = len(active)
        recent_failure_count = len(recent)

        if active_count > 0:
            blockers.append(f"{active_count} active investigation(s) — deploying may complicate triage")

        if recent_failure_count >= 3:
            warnings.append(f"{recent_failure_count} incidents in last 7 days — service may be unstable")

        safe = len(blockers) == 0

        return DeploySafetySignal(
            safe_to_deploy=safe,
            service_name=service_name,
            active_incident_count=active_count,
            recent_failure_count=recent_failure_count,
            warnings=warnings,
            blockers=blockers,
        )

    def get_fix_suggestion(
        self,
        service_name: str,
        file_path: str,
        error_context: str,
        repo: InvestigationRepository | None = None,
    ) -> IDEFixSuggestion:
        """
        Get a context-aware fix suggestion for a specific file/error.

        Cross-references with past investigations for the same service
        to provide informed suggestions.
        """
        prompt = f"""You are Corvin, an SRE AI assistant integrated into a developer's IDE.
The developer is working on service '{service_name}' and has encountered an issue.

File: {file_path}
Error/Context: {error_context}

Based on this context, provide a brief fix suggestion. Be concise (2-3 sentences max).
If you can provide a code snippet, include it.

Reply in JSON:
{{"suggestion": "...", "rationale": "...", "confidence": "low|medium|high", "code_snippet": "..." or null}}"""

        try:
            resp = litellm.completion(
                model=self._get_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            import json
            parsed = json.loads(resp.choices[0].message.content)
            return IDEFixSuggestion(
                file_path=file_path,
                service_name=service_name,
                suggestion=parsed.get("suggestion", "No suggestion available"),
                rationale=parsed.get("rationale", ""),
                confidence=parsed.get("confidence", "medium"),
                code_snippet=parsed.get("code_snippet"),
            )
        except Exception as exc:
            _log.warning("IDE fix suggestion LLM call failed: %s", exc)
            return IDEFixSuggestion(
                file_path=file_path,
                service_name=service_name,
                suggestion="Check recent investigations for this service for related issues.",
                rationale="LLM unavailable — providing generic guidance",
                confidence="low",
            )

    def get_deploy_safety(self, service_name: str, repo: InvestigationRepository | None = None) -> DeploySafetySignal:
        """Quick deployment safety check for CI/CD integration."""
        repository = repo or self._repo
        if not repository:
            return DeploySafetySignal(
                safe_to_deploy=True,
                service_name=service_name,
                active_incident_count=0,
                recent_failure_count=0,
            )

        active = repository.list_recent(hours=24, service_filter=service_name)
        recent = repository.list_recent(hours=168, service_filter=service_name)
        return self._check_deploy_safety(
            service_name,
            [{"id": i} for i in range(len(active or []))],
            [{"id": i} for i in range(len(recent or []))],
        )
