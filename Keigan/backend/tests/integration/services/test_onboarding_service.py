"""keigan/services/onboarding_service.py: a SaaS component's synthetic probe URL follows the outbound URL policy (V16)."""

from __future__ import annotations

import pytest

from keigan.config.database_config import open_session
from keigan.dtos.onboarding_dtos import ComponentCreateRequest, ComponentUpdateRequest
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.onboarding_service import OnboardingService
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")

APPLICATION_ADMIN = CurrentUser(
    user_principal_name="requester@example.com", display_name="Requester", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=False
)
PRIVATE_ADDRESS_MESSAGE = "This address points at a private or internal network, which Keigan does not call."


def saas_request(probe_url: str) -> ComponentCreateRequest:
    return ComponentCreateRequest(
        component_type="saas_platform", component_name="Vendor", component_configuration={"vendor_name": "Vendor", "synthetic_probe_url": probe_url}
    )


async def test_saas_component_with_a_probe_url_inside_the_network_is_rejected() -> None:
    application = await create_scoped_application()
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as rejection:
            await OnboardingService(session).add_component(APPLICATION_ADMIN, application.application_id, saas_request("https://10.1.2.3/health"))
    assert rejection.value.extra["fieldErrors"] == [{"field": "componentConfiguration.synthetic_probe_url", "message": PRIVATE_ADDRESS_MESSAGE}]


async def test_saas_component_with_a_plain_http_probe_url_is_rejected() -> None:
    application = await create_scoped_application()
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as rejection:
            await OnboardingService(session).add_component(APPLICATION_ADMIN, application.application_id, saas_request("http://vendor.example/health"))
    assert rejection.value.extra["fieldErrors"][0]["message"] == "Use an https:// address."


async def test_saas_component_with_a_public_https_probe_url_is_saved() -> None:
    application = await create_scoped_application()
    async with open_session() as session:
        component = await OnboardingService(session).add_component(APPLICATION_ADMIN, application.application_id, saas_request("https://vendor.example/health"))
    assert component.component_configuration["synthetic_probe_url"] == "https://vendor.example/health"


async def test_changing_a_probe_url_to_an_internal_address_is_rejected() -> None:
    application = await create_scoped_application()
    async with open_session() as session:
        onboarding_service = OnboardingService(session)
        component = await onboarding_service.add_component(APPLICATION_ADMIN, application.application_id, saas_request("https://vendor.example/health"))
        with pytest.raises(BusinessValidationException):
            await onboarding_service.update_component(
                APPLICATION_ADMIN, application.application_id, component.component_id,
                ComponentUpdateRequest(component_configuration={"synthetic_probe_url": "https://127.0.0.1/health"}),
            )
