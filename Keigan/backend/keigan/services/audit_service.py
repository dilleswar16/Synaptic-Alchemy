"""Audit trail for every write action and every AI tool execution (shared by all services)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.logging_config import current_correlation_id
from keigan.entities.platform_entities import AuditEvent
from keigan.security.current_user import CurrentUser
from keigan.utils.pii_masker import PiiMasker


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        actor: CurrentUser | str,
        action_name: str,
        *,
        target_entity_type: str | None = None,
        target_entity_id: str | None = None,
        application_id: str | None = None,
        action_details: dict[str, Any] | None = None,
        client_ip_address: str | None = None,
    ) -> None:
        """Add an audit row in the caller's transaction. ``action_name`` is ``<area>.<verb>``, e.g. ``application.update``."""
        actor_user_principal_name = actor.user_principal_name if isinstance(actor, CurrentUser) else actor
        self.session.add(
            AuditEvent(
                actor_user_principal_name=actor_user_principal_name,
                action_name=action_name,
                target_entity_type=target_entity_type,
                target_entity_id=target_entity_id,
                application_id=application_id,
                action_details_json=PiiMasker().mask_value(action_details) if action_details else None,
                client_ip_address=client_ip_address,
                correlation_id=current_correlation_id() or None,
            )
        )
