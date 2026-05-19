"""
Corvin Command Center API routes.

Prefix: /corvin  (registered in main.py)

Endpoints
---------
POST   /corvin/sessions                        — create a new chat session
GET    /corvin/sessions                        — list all sessions (newest first)
GET    /corvin/sessions/{session_id}           — get session + full message history
DELETE /corvin/sessions/{session_id}           — delete a session
POST   /corvin/sessions/{session_id}/chat      — send a message, stream the response
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from corvin.storage.db import get_session
from corvin.storage.models import CorvinMessageRow, CorvinSessionRow

_log = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    thinking: str | None = None
    tool_calls: dict | list | None = None
    tool_results: dict | None = None
    created_at: str


class SessionDetailOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageOut]


class ChatRequest(BaseModel):
    message: str  # The new user message


# ── Session management ────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session() -> SessionOut:
    """Create a new empty chat session and return its ID."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with get_session() as db:
        row = CorvinSessionRow(
            id=session_id,
            title="New conversation",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
    return SessionOut(
        id=session_id,
        title="New conversation",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        message_count=0,
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions() -> list[SessionOut]:
    """Return all sessions, newest first, with message counts."""
    with get_session() as db:
        rows = db.execute(
            select(CorvinSessionRow).order_by(CorvinSessionRow.updated_at.desc())
        ).scalars().all()
        result = []
        for row in rows:
            count = db.execute(
                select(CorvinMessageRow).where(CorvinMessageRow.session_id == row.id)
            ).scalars().all()
            result.append(SessionOut(
                id=row.id,
                title=row.title,
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
                message_count=len(count),
            ))
        return result


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
def get_session_detail(session_id: str) -> SessionDetailOut:
    """Return a session and all its messages."""
    with get_session() as db:
        session_row = db.get(CorvinSessionRow, session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found.")
        msg_rows = db.execute(
            select(CorvinMessageRow)
            .where(CorvinMessageRow.session_id == session_id)
            .order_by(CorvinMessageRow.created_at)
        ).scalars().all()
        messages = [
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                thinking=m.thinking,
                tool_calls=m.tool_calls,
                tool_results=m.tool_results,
                created_at=m.created_at.isoformat(),
            )
            for m in msg_rows
        ]
        return SessionDetailOut(
            id=session_row.id,
            title=session_row.title,
            created_at=session_row.created_at.isoformat(),
            updated_at=session_row.updated_at.isoformat(),
            messages=messages,
        )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """Delete a session and all its messages."""
    with get_session() as db:
        session_row = db.get(CorvinSessionRow, session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found.")
        db.execute(
            CorvinMessageRow.__table__.delete().where(  # type: ignore[attr-defined]
                CorvinMessageRow.session_id == session_id
            )
        )
        db.delete(session_row)
        db.commit()


# ── Chat streaming ────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/chat")
def chat(
    session_id: str,
    body: ChatRequest,
) -> StreamingResponse:
    """Send a user message and stream the agentic response.

    The user message is persisted immediately. The assistant reply (text only,
    no tool results) is persisted after streaming completes.
    Tool call events are streamed to the frontend but not stored individually
    (the assistant message captures the final interpreted answer).
    """
    from corvin.strategy.agent_service import CorvinAgentService

    # Verify session exists
    with get_session() as db:
        session_row = db.get(CorvinSessionRow, session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found.")

        # Load full history for context
        msg_rows = db.execute(
            select(CorvinMessageRow)
            .where(CorvinMessageRow.session_id == session_id)
            .order_by(CorvinMessageRow.created_at)
        ).scalars().all()
        history = [{"role": m.role, "content": m.content} for m in msg_rows]

    # Persist the user message immediately
    now = datetime.now(timezone.utc)
    user_content = body.message.strip()
    with get_session() as db:
        db.add(CorvinMessageRow(
            session_id=session_id,
            role="user",
            content=user_content,
            created_at=now,
        ))
        # Auto-title the session from the first message (truncated)
        session_row = db.get(CorvinSessionRow, session_id)
        if session_row and session_row.title == "New conversation":
            session_row.title = user_content[:60] + ("…" if len(user_content) > 60 else "")
        if session_row:
            session_row.updated_at = now
        db.commit()

    # Build full history including the new user message
    history.append({"role": "user", "content": user_content})
    svc = CorvinAgentService()

    def _stream_and_persist():
        text_chunks: list[str] = []
        thinking_chunks: list[str] = []
        tool_calls_seen: list[dict] = []
        # key: tool_name → last result payload (for tools called multiple times, last wins)
        tool_results_seen: dict[str, object] = {}

        for chunk in svc.stream_chat_simple(history):
            yield chunk
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = json.loads(chunk[6:])
                    if data.get("type") == "text" and data.get("text"):
                        text_chunks.append(data["text"])
                    elif data.get("type") == "thinking" and data.get("text"):
                        thinking_chunks.append(data["text"])
                    elif data.get("type") == "tool_call":
                        tool_calls_seen.append({
                            "tool_name": data.get("tool_name"),
                            "arguments": data.get("arguments"),
                        })
                    elif data.get("type") == "tool_result" and data.get("tool_name"):
                        tool_results_seen[data["tool_name"]] = data.get("data")
                except Exception:
                    pass

        # Persist the assistant reply
        full_reply = "".join(text_chunks)
        if full_reply.strip():
            try:
                persist_now = datetime.now(timezone.utc)
                with get_session() as db:
                    db.add(CorvinMessageRow(
                        session_id=session_id,
                        role="assistant",
                        content=full_reply,
                        thinking="".join(thinking_chunks) if thinking_chunks else None,
                        tool_calls={"calls": tool_calls_seen} if tool_calls_seen else None,
                        tool_results=tool_results_seen if tool_results_seen else None,
                        created_at=persist_now,
                    ))
                    session_row = db.get(CorvinSessionRow, session_id)
                    if session_row:
                        session_row.updated_at = persist_now
                    db.commit()
            except Exception as exc:
                _log.warning("Failed to persist assistant reply: %s", exc)

    return StreamingResponse(
        _stream_and_persist(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
