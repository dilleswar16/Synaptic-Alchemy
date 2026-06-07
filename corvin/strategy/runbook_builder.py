"""
Conversational Runbook Builder — V6

Upgrades the one-shot runbook generation to a multi-turn conversational experience.
The operator can iteratively refine runbook steps through natural conversation:

  1. Initial draft is generated from investigation context
  2. User can ask to expand, simplify, add caveats, add rollback steps, etc.
  3. Each revision shows a diff preview
  4. Final version requires explicit "save" approval before persisting

All saves require human approval — no auto-writing to knowledge base.

Sessions are persisted to the ``runbook_sessions`` database table so they
survive server restarts and are safe to access from multiple FastAPI workers.
The Python object carries no mutable state — every method reads from and
writes to the DB, making the class safe to use as a module-level singleton.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

import litellm

from corvin.core.config_loader import get_env, load_config

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert SRE runbook author for the Corvin incident response platform.

Your job is to help operators build high-quality runbook steps through conversation.
You ALWAYS output runbook content in Markdown format.

Rules:
- Start runbook steps with ## heading
- Use bullet points for procedural steps
- Include a dedicated "Pre-checks (before restart)" section before any restart action
- Include rollback instructions when relevant
- Include "When to apply" context
- Keep each step under 300 words
- Be specific: include actual commands, service names, thresholds
- When asked to revise, output the FULL updated runbook step (not just the diff)
- Prefer parameterized placeholders over hardcoded cluster identities, for example:
    - {{AKS_CONTEXT}}
    - {{TARGET_NAMESPACE}}
    - {{TARGET_SERVICE}}
    - {{OTLP_SERVICE_FQDN}}
    - {{KNOWN_GOOD_MANIFEST_PATH}}

Safety guardrails:
- Never suggest a restart as first step when simple validation can disprove the hypothesis.
- Add at least 3 pre-checks before any restart/rollback command.
- Include explicit verification criteria and success thresholds.

You have context from the investigation that generated this runbook entry.
Use it to provide specific, actionable steps."""


@dataclass
class RunbookDraft:
    """Current draft of the runbook being built."""
    content: str
    version: int
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "version": self.version,
            "generated_at": self.generated_at,
        }


@dataclass
class RunbookSession:
    """In-memory view of a runbook building session loaded from the DB row."""
    session_id: str
    request_id: str
    service_name: str
    environment: str
    messages: list[dict[str, str]]
    current_draft: RunbookDraft | None
    status: str  # drafting | approved | saved
    approved_by: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "service_name": self.service_name,
            "environment": self.environment,
            "message_count": len([m for m in self.messages if m["role"] != "system"]),
            "current_draft": self.current_draft.to_dict() if self.current_draft else None,
            "status": self.status,
            "approved_by": self.approved_by,
            "created_at": self.created_at,
        }


class RunbookBuilder:
    """Conversational runbook builder with DB-backed session persistence.

    The class carries no mutable Python state — all session data lives in
    the ``runbook_sessions`` database table.  It is safe to use as a
    module-level singleton across multiple FastAPI worker threads.
    """

    def __init__(self) -> None:
        self._model_config = load_config("models/llm", get_env())

    # ── Public API ─────────────────────────────────────────────────────────────

    def start_session(
        self,
        request_id: str,
        service_name: str,
        environment: str,
        investigation_context: str,
    ) -> RunbookSession:
        """Create a new runbook session and persist it to the DB."""
        from corvin.storage.db import get_session as db_ctx
        from corvin.storage.models import RunbookSessionRow

        session_id = str(uuid.uuid4())
        system_msg = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"## Investigation Context\n"
            f"Service: {service_name}\n"
            f"Environment: {environment}\n"
            f"Investigation ID: {request_id}\n\n"
            f"{investigation_context}"
        )
        messages = [{"role": "system", "content": system_msg}]

        with db_ctx() as db:
            row = RunbookSessionRow(
                id=session_id,
                request_id=request_id,
                service_name=service_name,
                environment=environment,
                status="drafting",
                messages_json=messages,
            )
            db.add(row)

        return self._row_to_session_obj(
            session_id, request_id, service_name, environment,
            messages, None, "drafting", None,
            datetime.now(timezone.utc).isoformat(),
        )

    def get_session(self, session_id: str) -> RunbookSession | None:
        """Load a session from the DB. Returns None if not found."""
        from corvin.storage.db import get_session as db_ctx
        from corvin.storage.models import RunbookSessionRow

        with db_ctx() as db:
            row = db.get(RunbookSessionRow, session_id)
            if row is None:
                return None
            return self._row_to_session(row)

    async def chat(self, session_id: str, user_message: str) -> dict[str, Any]:
        """Send a message and get the assistant response (non-streaming).

        The LLM call is offloaded to a thread-pool worker via asyncio.to_thread
        so the FastAPI event loop is never blocked.
        """
        from corvin.storage.db import get_session as db_ctx
        from corvin.storage.models import RunbookSessionRow

        with db_ctx() as db:
            row = db.get(RunbookSessionRow, session_id)
            if row is None:
                return {"error": "Session not found", "session_id": session_id}
            if row.status == "saved":
                return {"error": "Session already saved. Start a new session to make changes."}

            messages: list[dict[str, str]] = list(row.messages_json or [])
            messages.append({"role": "user", "content": user_message})

            completion_kwargs = self._build_completion_kwargs()
            if completion_kwargs is None:
                _log.warning("Runbook builder: LLM credentials missing, using deterministic fallback")
                assistant_content = self._fallback_runbook_response(
                    row.current_draft_content, user_message
                )
            else:
                try:
                    resp = await asyncio.to_thread(
                        litellm.completion,
                        messages=messages,
                        **completion_kwargs,
                    )
                    assistant_content = (resp.choices[0].message.content or "").strip()
                except Exception as exc:
                    _log.warning("Runbook builder LLM call failed; using fallback: %s", exc)
                    assistant_content = self._fallback_runbook_response(
                        row.current_draft_content, user_message
                    )

            messages.append({"role": "assistant", "content": assistant_content})

            draft_content = self._extract_runbook_content(assistant_content)
            new_version = (row.current_draft_version or 0) + 1 if draft_content else row.current_draft_version

            row.messages_json = messages
            if draft_content:
                row.current_draft_content = draft_content
                row.current_draft_version = new_version
            row.updated_at = datetime.now(timezone.utc)

            current_draft = (
                RunbookDraft(content=row.current_draft_content, version=row.current_draft_version or 1)
                if row.current_draft_content else None
            )

        return {
            "session_id": session_id,
            "response": assistant_content,
            "draft": current_draft.to_dict() if current_draft else None,
            "message_count": len([m for m in messages if m["role"] != "system"]),
        }

    def stream_chat(
        self, session_id: str, user_message: str
    ) -> Generator[dict[str, Any], None, None]:
        """Stream runbook response tokens.

        Runs synchronously — FastAPI dispatches sync routes to a thread-pool
        worker so the event loop is not blocked. Accumulates the full response
        and persists to DB once the generator is exhausted.
        """
        from corvin.storage.db import get_session as db_ctx
        from corvin.storage.models import RunbookSessionRow

        with db_ctx() as db:
            row = db.get(RunbookSessionRow, session_id)
            if row is None:
                yield {"type": "error", "error": f"Session '{session_id}' not found."}
                return
            if row.status == "saved":
                yield {"type": "error", "error": "Session already saved. Start a new session to make changes."}
                return

            messages: list[dict[str, str]] = list(row.messages_json or [])

        messages.append({"role": "user", "content": user_message})

        completion_kwargs = self._build_completion_kwargs()
        assistant_content = ""

        if completion_kwargs is None:
            _log.warning("Runbook builder: LLM credentials missing, using deterministic fallback")
            # Load prior draft content for fallback
            with db_ctx() as db:
                row = db.get(RunbookSessionRow, session_id)
                prior_draft = row.current_draft_content if row else None
            assistant_content = self._fallback_runbook_response(prior_draft, user_message)
            yield {"type": "token", "text": assistant_content}
        else:
            try:
                response = litellm.completion(
                    messages=messages,
                    stream=True,
                    **completion_kwargs,
                )
                for chunk in response:
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta
                    text = getattr(delta, "content", None)
                    if text:
                        assistant_content += text
                        yield {"type": "token", "text": text}
            except Exception as exc:
                _log.warning("Runbook builder stream failed; using fallback: %s", exc)
                with db_ctx() as db:
                    row = db.get(RunbookSessionRow, session_id)
                    prior_draft = row.current_draft_content if row else None
                assistant_content = self._fallback_runbook_response(prior_draft, user_message)
                yield {"type": "token", "text": assistant_content}

        messages.append({"role": "assistant", "content": assistant_content})
        draft_content = self._extract_runbook_content(assistant_content)

        with db_ctx() as db:
            row = db.get(RunbookSessionRow, session_id)
            if row is not None:
                row.messages_json = messages
                if draft_content:
                    row.current_draft_content = draft_content
                    row.current_draft_version = (row.current_draft_version or 0) + 1
                row.updated_at = datetime.now(timezone.utc)
                current_draft = (
                    RunbookDraft(content=row.current_draft_content, version=row.current_draft_version or 1)
                    if row.current_draft_content else None
                )
            else:
                current_draft = None

        yield {
            "type": "done",
            "session_id": session_id,
            "response": assistant_content,
            "draft": current_draft.to_dict() if current_draft else None,
            "message_count": len([m for m in messages if m["role"] != "system"]),
        }

    async def generate_initial_draft(self, session_id: str) -> dict[str, Any]:
        """Generate the first draft without user input."""
        return await self.chat(
            session_id,
            "Generate an initial runbook step based on the investigation context. "
            "Include: heading, when to apply, procedural steps, rollback, and verification."
        )

    def approve_draft(self, session_id: str, approved_by: str) -> dict[str, Any]:
        """Mark the current draft as approved (ready to save). Persists approved_by."""
        from corvin.storage.db import get_session as db_ctx
        from corvin.storage.models import RunbookSessionRow

        with db_ctx() as db:
            row = db.get(RunbookSessionRow, session_id)
            if row is None:
                return {"error": "Session not found"}
            if not row.current_draft_content:
                return {"error": "No draft to approve"}
            row.status = "approved"
            row.approved_by = approved_by
            row.updated_at = datetime.now(timezone.utc)
            current_draft = RunbookDraft(
                content=row.current_draft_content,
                version=row.current_draft_version or 1,
            )

        return {
            "session_id": session_id,
            "status": "approved",
            "approved_by": approved_by,
            "draft": current_draft.to_dict(),
        }

    def get_final_content(self, session_id: str) -> str | None:
        """Return approved draft content and mark session as saved."""
        from corvin.storage.db import get_session as db_ctx
        from corvin.storage.models import RunbookSessionRow

        with db_ctx() as db:
            row = db.get(RunbookSessionRow, session_id)
            if row is None or row.status != "approved" or not row.current_draft_content:
                return None
            content = row.current_draft_content
            row.status = "saved"
            row.updated_at = datetime.now(timezone.utc)

        return content

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_session(row: Any) -> RunbookSession:
        draft = None
        if row.current_draft_content:
            draft = RunbookDraft(
                content=row.current_draft_content,
                version=row.current_draft_version or 1,
            )
        created = row.created_at
        if isinstance(created, datetime):
            created = created.isoformat()
        return RunbookSession(
            session_id=row.id,
            request_id=row.request_id,
            service_name=row.service_name,
            environment=row.environment,
            messages=list(row.messages_json or []),
            current_draft=draft,
            status=row.status,
            approved_by=row.approved_by,
            created_at=created or "",
        )

    @staticmethod
    def _row_to_session_obj(
        session_id: str,
        request_id: str,
        service_name: str,
        environment: str,
        messages: list,
        draft: RunbookDraft | None,
        status: str,
        approved_by: str | None,
        created_at: str,
    ) -> RunbookSession:
        return RunbookSession(
            session_id=session_id,
            request_id=request_id,
            service_name=service_name,
            environment=environment,
            messages=messages,
            current_draft=draft,
            status=status,
            approved_by=approved_by,
            created_at=created_at,
        )

    def _build_completion_kwargs(self) -> dict[str, Any] | None:
        """Build LiteLLM kwargs. Returns None when credentials are absent."""
        model = self._model_config.get("fallback_model") or self._model_config.get("model")
        if not model:
            return None

        endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
        api_version = os.environ.get("AZURE_API_VERSION", "").strip()
        api_key = (
            os.environ.get("LITELLM_API_KEY", "").strip()
            or os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        )
        ad_token = os.environ.get("AZURE_OPENAI_AD_TOKEN", "").strip()

        if not api_key and not ad_token:
            return None

        kwargs: dict[str, Any] = {
            "model": model,
            "api_base": endpoint if endpoint else "",
            "temperature": self._model_config.get("temperature", 0.2),
            "max_tokens": self._model_config.get("max_tokens", 2048),
        }
        if api_version:
            kwargs["api_version"] = api_version
        if api_key:
            kwargs["api_key"] = api_key
        if ad_token:
            kwargs["azure_ad_token"] = ad_token
        return kwargs

    @staticmethod
    def _fallback_runbook_response(prior_draft: str | None, user_message: str) -> str:
        """Deterministic markdown fallback used when LLM is unavailable."""
        message = (user_message or "").strip().lower()
        is_initial = "generate an initial runbook" in message or "initial" in message
        title = "Initial Runbook Draft" if is_initial else "Runbook Revision"
        refinement = (
            f"Requested refinement: {user_message.strip()}"
            if user_message.strip()
            else "Requested refinement: update the runbook for better clarity"
        )

        base = f"""## {title} — {{{{TARGET_SERVICE}}}} (env: {{{{TARGET_ENVIRONMENT}}}})

### When to apply
- Use when incident telemetry indicates sustained failures, timeout symptoms, or exporter/dependency resolution issues for **{{{{TARGET_SERVICE}}}}**.

### Pre-checks (before restart)
- Confirm cluster context is correct: `kubectl config current-context` should match **{{{{AKS_CONTEXT}}}}**.
- Validate namespace and service existence:
    - `kubectl get ns {{{{TARGET_NAMESPACE}}}}`
    - `kubectl get svc {{{{TARGET_SERVICE}}}} -n {{{{TARGET_NAMESPACE}}}}`
- Validate endpoint readiness before any restart:
    - `kubectl get endpoints {{{{TARGET_SERVICE}}}} -n {{{{TARGET_NAMESPACE}}}}`
    - `kubectl get pods -n {{{{TARGET_NAMESPACE}}}} -l app={{{{TARGET_SERVICE}}}}`
- If incident is OTLP-related, verify FQDN resolution target: **{{{{OTLP_SERVICE_FQDN}}}}**.

### Steps
- Confirm current incident scope in Corvin evidence and RCA sections.
- Validate dependency endpoints, service discovery, and configuration alignment.
- If service object is missing/misconfigured, re-apply from known-good manifest: `kubectl apply -f {{{{KNOWN_GOOD_MANIFEST_PATH}}}} -n {{{{TARGET_NAMESPACE}}}}`.
- Apply the smallest safe remediation first (config correction, then targeted restart only if pre-checks pass).
- Observe error rate and latency for 15 minutes before further changes.

### Rollback
- Revert to the last known good deployment/config if error rate increases:
    - `kubectl rollout undo deployment/{{{{TARGET_SERVICE}}}} -n {{{{TARGET_NAMESPACE}}}}`
- Escalate to incident channel if rollback does not stabilize service.

### Verification
- No new critical alerts for this service.
- RCA signals no longer reproducing.
- Core health checks pass across the namespace.

### Notes
- {refinement}
"""

        if prior_draft and not is_initial:
            return f"{base}\n### Previous Draft Context\n{prior_draft[:1200]}"
        return base

    @staticmethod
    def _extract_runbook_content(text: str) -> str | None:
        """Extract the runbook markdown from assistant response."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("##"):
                return "\n".join(lines[i:]).strip()
        if any(line.strip().startswith("- ") for line in lines):
            return text.strip()
        return None
