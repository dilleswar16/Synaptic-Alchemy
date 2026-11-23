"""Keigan API entrypoint (the ``@SpringBootApplication`` equivalent): ``uvicorn keigan.main:app``."""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from keigan.config import application_context
from keigan.config.database_config import create_database_schema
from keigan.config.logging_config import configure_logging
from keigan.config.settings import get_settings
from keigan.exceptions.keigan_exceptions import register_exception_handlers
from keigan.security.security_middleware import SecurityMiddleware
from keigan.services.ask_keigan_interruption import RunInterruption

logger = logging.getLogger(__name__)

CONTROLLER_MODULES = (
    "keigan.controllers.public_controller",
    "keigan.controllers.authentication_controller",
    "keigan.controllers.application_controller",
    "keigan.controllers.operating_notes_controller",
    "keigan.controllers.onboarding_controller",
    "keigan.controllers.knowledge_controller",
    "keigan.controllers.incident_controller",
    "keigan.controllers.investigation_controller",
    "keigan.controllers.action_item_controller",
    "keigan.controllers.alert_controller",
    "keigan.controllers.alert_intake_controller",
    "keigan.controllers.slo_controller",
    "keigan.controllers.error_budget_controller",
    "keigan.controllers.intelligence_controller",
    "keigan.controllers.chat_controller",
    "keigan.controllers.notification_controller",
    "keigan.controllers.teams_bot_controller",
    "keigan.controllers.dashboard_controller",
    "keigan.controllers.metrics_controller",
    "keigan.controllers.administration_controller",
)


@asynccontextmanager
async def application_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.auto_create_schema:
        await create_database_schema()
    background_tasks: list[asyncio.Task[None]] = []
    stoppable_components: list[object] = []
    if settings.run_workers_in_process:
        from keigan.workers.job_queue import JobWorker
        from keigan.workers.schedulers import Scheduler

        job_worker, scheduler = JobWorker(), Scheduler()
        stoppable_components = [job_worker, scheduler]
        background_tasks = [asyncio.create_task(job_worker.run_forever()), asyncio.create_task(scheduler.run_forever())]
        logger.info("Workers running inside the API process (RUN_WORKERS_IN_PROCESS=true)")
    logger.info(
        "Keigan %s started · environment=%s · auth=%s · llm=%s · telemetry=%s",
        settings.product_version, settings.environment, settings.auth_mode, settings.llm_provider, settings.telemetry_mode,
    )
    try:
        yield
    finally:
        # Answers run as detached tasks (they outlive their request): cut them and end their runs as interrupted, so nothing is left "running" by this pod.
        await RunInterruption(application_context.answer_run_registry()).interrupt_live_runs()
        for stoppable_component in stoppable_components:
            stoppable_component.stop()  # type: ignore[attr-defined]
        if background_tasks:
            await asyncio.wait(background_tasks, timeout=10)


def create_application() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, use_json_format=not settings.is_local_environment)
    documentation_enabled = settings.enable_api_docs and settings.environment != "prod"
    keigan_application = FastAPI(
        title="Keigan API",
        description="慧眼 Keigan — the discerning eye for our systems.",
        version=settings.product_version,
        docs_url="/api/docs" if documentation_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if documentation_enabled else None,
        lifespan=application_lifespan,
    )
    keigan_application.add_middleware(SecurityMiddleware)
    keigan_application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-Id"],
        expose_headers=["X-Correlation-Id"],
    )
    register_exception_handlers(keigan_application)
    for controller_module_path in CONTROLLER_MODULES:
        keigan_application.include_router(importlib.import_module(controller_module_path).router)
    return keigan_application


app = create_application()
