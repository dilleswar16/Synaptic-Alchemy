"""keigan/services/reference_release.py (H11, H12): deleting a service, runbook or document first releases the rows that still point at it."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import Alert, AlertGroup, AlertGroupAffectedService, MaintenanceWindowAppliesToService
from keigan.entities.application_entities import MonitoredService
from keigan.entities.incident_entities import IncidentAffectedService, InvestigationInvestigatedService, InvestigationMatchedRunbook
from keigan.entities.knowledge_entities import RunbookAppliesToService, TopologySourceDocument
from keigan.entities.notification_entities import StakeholderSubscribedService
from keigan.entities.slo_entities import PredictiveSignal, ServiceLevelIndicator
from keigan.security.current_user import CurrentUser
from keigan.services.knowledge_service import KnowledgeService
from keigan.services.onboarding_service import OnboardingService
from keigan.services.runbook_service import RunbookService
from keigan.services.service_catalog_service import ServiceCatalogService
from support.application_graph import ApplicationGraph, create_application_graph

pytestmark = pytest.mark.usefixtures("seed_context")
ADMIN = CurrentUser(user_principal_name="admin@example.com", display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


async def linked_service_ids(link_entity: type, owner_column: str, owner_id: str) -> list[str]:
    async with open_session() as session:
        return list((await session.scalars(select(link_entity.service_id).where(getattr(link_entity, owner_column) == owner_id).order_by(link_entity.position))).all())


async def test_deleting_a_service_removes_it_from_every_list_that_named_it(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        await ServiceCatalogService(session).delete_service(ADMIN, graph.application_id, graph.first_service_id)
    assert await linked_service_ids(IncidentAffectedService, "incident_id", graph.incident_id) == [graph.second_service_id]
    assert await linked_service_ids(InvestigationInvestigatedService, "investigation_id", graph.investigation_id) == [graph.second_service_id]
    assert await linked_service_ids(AlertGroupAffectedService, "alert_group_id", graph.alert_group_id) == [graph.second_service_id]
    async with open_session() as session:
        for link_entity in (MaintenanceWindowAppliesToService, StakeholderSubscribedService, RunbookAppliesToService):
            assert await session.scalar(select(func.count()).select_from(link_entity).where(link_entity.service_id == graph.first_service_id)) == 0


async def test_deleting_a_service_clears_the_optional_service_references_instead_of_deleting_those_rows(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        await ServiceCatalogService(session).delete_service(ADMIN, graph.application_id, graph.first_service_id)
    async with open_session() as session:
        assert await session.scalar(select(func.count()).select_from(Alert).where(Alert.application_id == graph.application_id, Alert.service_id.is_(None))) == 1
        assert await session.scalar(select(AlertGroup.primary_service_id).where(AlertGroup.alert_group_id == graph.alert_group_id)) is None
        assert await session.scalar(select(ServiceLevelIndicator.service_id).where(ServiceLevelIndicator.sli_id == graph.sli_id)) is None
        assert await session.scalar(select(PredictiveSignal.service_id).where(PredictiveSignal.sli_id == graph.sli_id)) is None


async def test_removing_a_component_releases_the_lists_that_named_its_services(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        component_id = await session.scalar(select(MonitoredService.component_id).where(MonitoredService.service_id == graph.first_service_id))
        await OnboardingService(session).delete_component(ADMIN, graph.application_id, component_id)
    assert await linked_service_ids(IncidentAffectedService, "incident_id", graph.incident_id) == [graph.second_service_id]


async def test_deleting_a_runbook_removes_it_from_the_runbooks_an_investigation_matched(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        await RunbookService(session).delete_runbook(ADMIN, graph.application_id, graph.runbook_id)
    async with open_session() as session:
        matched = await session.scalar(select(func.count()).select_from(InvestigationMatchedRunbook).where(InvestigationMatchedRunbook.investigation_id == graph.investigation_id))
    assert matched == 0


async def test_deleting_a_document_removes_it_from_the_documents_a_topology_was_built_from(seed_context) -> None:
    graph: ApplicationGraph = await create_application_graph()
    async with open_session() as session:
        await KnowledgeService(session).delete_document(ADMIN, graph.application_id, graph.knowledge_document_id)
    async with open_session() as session:
        sources = await session.scalar(select(func.count()).select_from(TopologySourceDocument).where(TopologySourceDocument.knowledge_document_id == graph.knowledge_document_id))
    assert sources == 0
