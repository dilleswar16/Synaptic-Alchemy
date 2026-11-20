"""Singleton beans (the Spring ApplicationContext equivalent).

Services obtain shared, stateless-or-thread-safe collaborators from here instead of constructing them.
Each getter is cached so there is exactly one instance per process.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from keigan.config.settings import get_settings

if TYPE_CHECKING:
    from keigan.ai.llm_gateway import LlmGateway
    from keigan.ai.prompt_library import PromptLibrary
    from keigan.integrations.azure_client import AzureClient
    from keigan.integrations.azure_identity_provider import AzureCredentialProvider
    from keigan.integrations.file_storage import FileStorage
    from keigan.integrations.log_tool_clients import LogToolClientFactory
    from keigan.integrations.secret_store import SecretStore
    from keigan.integrations.simulation.telemetry_simulator import TelemetrySimulator
    from keigan.integrations.telemetry_gateway import TelemetryGateway


@lru_cache
def azure_credential_provider() -> "AzureCredentialProvider":
    from keigan.integrations.azure_identity_provider import AzureCredentialProvider

    return AzureCredentialProvider(get_settings())


@lru_cache
def azure_client() -> "AzureClient":
    from keigan.integrations.azure_client import AzureClient

    return AzureClient(azure_credential_provider())


@lru_cache
def log_tool_client_factory() -> "LogToolClientFactory":
    from keigan.integrations.log_tool_clients import LogToolClientFactory

    return LogToolClientFactory(secret_store())


@lru_cache
def telemetry_simulator() -> "TelemetrySimulator":
    from keigan.integrations.simulation.telemetry_simulator import TelemetrySimulator

    return TelemetrySimulator()


@lru_cache
def telemetry_gateway() -> "TelemetryGateway":
    from keigan.integrations.telemetry_gateway import TelemetryGateway

    return TelemetryGateway(get_settings(), azure_client(), log_tool_client_factory(), telemetry_simulator())


@lru_cache
def secret_store() -> "SecretStore":
    from keigan.integrations.secret_store import create_secret_store

    return create_secret_store(get_settings(), azure_credential_provider())


@lru_cache
def file_storage() -> "FileStorage":
    from keigan.integrations.file_storage import create_file_storage

    return create_file_storage(get_settings(), azure_credential_provider())


@lru_cache
def prompt_library() -> "PromptLibrary":
    from keigan.ai.prompt_library import PromptLibrary

    return PromptLibrary()


@lru_cache
def llm_gateway() -> "LlmGateway":
    from keigan.ai.llm_gateway import LlmGateway

    return LlmGateway(get_settings())
