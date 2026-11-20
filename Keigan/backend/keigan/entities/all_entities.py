"""Imports every entity module so SQLAlchemy's metadata knows all tables (used by schema creation)."""

from keigan.entities.alert_entities import *  # noqa: F403
from keigan.entities.application_entities import *  # noqa: F403
from keigan.entities.incident_entities import *  # noqa: F403
from keigan.entities.knowledge_entities import *  # noqa: F403
from keigan.entities.notification_entities import *  # noqa: F403
from keigan.entities.platform_entities import *  # noqa: F403
from keigan.entities.slo_entities import *  # noqa: F403
