"""keigan/main.py: what the application does when it shuts down (spec 23, 7.5: graceful shutdown of the answers it is running)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.dtos.ask_keigan_dtos import AnswerRequest
from keigan.entities.incident_entities import ChatRunStep
from keigan.entities.status_values import ChatAnswerRunStatus, ChatRunStepStatus
from keigan.main import app, application_lifespan
from keigan.services.ask_keigan_engine import AskKeiganEngine
from keigan.services.ask_keigan_service import AskKeiganService
from support.ask_keigan_conversations import open_investigation_chat, seed_investigation, stored_run
from support.ask_keigan_runs import ScriptedGateway, Turn, user

pytestmark = pytest.mark.usefixtures("seed_context")


async def test_shutting_down_cancels_the_running_answers_and_ends_their_runs_as_interrupted(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "chat_rate_limit_per_minute", 10_000)
    reader = user("lifespan.reader@keigan.local", "CLMJP_reader")
    investigation = await seed_investigation(seed_context.application_ids_by_code["CLMJP"])
    conversation_id = await open_investigation_chat(reader, investigation.investigation_id)
    never_released = asyncio.Event()

    async def wait_forever() -> None:
        await never_released.wait()

    registry = application_context.answer_run_registry()
    async with open_session() as session:
        started = await AskKeiganService(session, registry, AskKeiganEngine(ScriptedGateway([Turn(before=wait_forever, text="never")]))).start(
            reader, conversation_id, AnswerRequest(message_text="Show me evidence E2", client_request_id=uuid.uuid4()),
        )
    task = registry.get(started.answer_run_id).task
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.RUNNING

    async with application_lifespan(app):
        pass  # the application starts and stops

    run = await stored_run(started.answer_run_id)
    assert (run.run_status, run.error_code) == (ChatAnswerRunStatus.FAILED, "answer_interrupted") and task.cancelled()
    assert registry.get(started.answer_run_id) is None
    async with open_session() as session:
        step_statuses = (await session.scalars(select(ChatRunStep.step_status).where(ChatRunStep.answer_run_id == started.answer_run_id))).all()
    assert ChatRunStepStatus.RUNNING not in step_statuses
