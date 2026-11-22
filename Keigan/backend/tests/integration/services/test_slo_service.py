"""keigan/services/slo_service.py and sli_measurement_reader.py: custom SLI queries are validated, and SLI lists are loaded in bulk."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import event, select

from keigan.config.database_config import open_session
from keigan.entities.slo_entities import ServiceLevelIndicator
from keigan.services.sli_measurement_reader import SliMeasurementReader
from keigan.services.slo_service import SloService
from keigan.utils.query_safety import QueryRejectedError
from support import users
from support.http import AuthHeaders

GOOD_KQL = "AppRequests | summarize good=countif(Success == true), total=count() by window_start=bin(TimeGenerated, 5m)"


def _sli_body(service_id: str, name: str, kql: str) -> dict:
    return {"serviceId": service_id, "sliName": name, "sliKind": "availability", "dataSourceKind": "log_query", "queryDefinition": {"kql": kql}}


class TestCustomSliQueryIsValidatedOnSave:
    async def test_create_accepts_a_query_over_allowed_tables(self, client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
        application_id = seed_context.application_ids_by_code["CLMJP"]
        response = await client.post(
            f"/api/applications/{application_id}/slis", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json=_sli_body(seed_context.service_id("CLMJP", "claims-api"), "Pytest good SLI", GOOD_KQL)
        )
        assert response.status_code == 201, response.text

    @pytest.mark.parametrize(
        "kql",
        [
            "SecurityEvent | summarize good=count(), total=count() by window_start=bin(TimeGenerated, 5m)",
            "AppRequests | union SecurityEvent | summarize good=count(), total=count() by window_start=bin(TimeGenerated, 5m)",
            'AppRequests | where Name == "//" | union workspace("other").SecurityEvent | summarize good=count(), total=count()',
            "Syslog | summarize good=count(), total=count() by window_start=bin(TimeGenerated, 5m)",
            "AppRequests | evaluate http_request('https://evil.example')",
        ],
    )
    async def test_create_rejects_a_query_over_tables_or_functions_that_are_not_allowed(self, client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context, kql: str) -> None:
        application_id = seed_context.application_ids_by_code["CLMJP"]
        response = await client.post(
            f"/api/applications/{application_id}/slis", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json=_sli_body(seed_context.service_id("CLMJP", "claims-api"), "Pytest bad SLI", kql)
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["fieldErrors"][0]["field"] == "queryDefinition"
        assert body["fieldErrors"][0]["message"]
        assert "query" in body["detail"].lower()

    async def test_a_rejected_create_stores_nothing(self, client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
        application_id = seed_context.application_ids_by_code["CLMJP"]
        await client.post(
            f"/api/applications/{application_id}/slis", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
            json=_sli_body(seed_context.service_id("CLMJP", "claims-api"), "Pytest never stored", "SecurityEvent | count"),
        )
        async with open_session() as session:
            assert await session.scalar(select(ServiceLevelIndicator.sli_id).where(ServiceLevelIndicator.sli_name == "Pytest never stored")) is None

    async def test_update_rejects_a_bad_query_and_keeps_the_old_one(self, client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
        application_id = seed_context.application_ids_by_code["CLMJP"]
        headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
        created = await client.post(f"/api/applications/{application_id}/slis", headers=headers, json=_sli_body(seed_context.service_id("CLMJP", "claims-api"), "Pytest update SLI", GOOD_KQL))
        sli_id = created.json()["sliId"]
        response = await client.patch(f"/api/slis/{sli_id}", headers=headers, json={"queryDefinition": {"kql": "AppRequests | union SecurityEvent | count"}})
        assert response.status_code == 422, response.text
        assert response.json()["fieldErrors"][0]["field"] == "queryDefinition"
        async with open_session() as session:
            stored = await session.get(ServiceLevelIndicator, sli_id)
        assert stored is not None and stored.query_definition_json == {"kql": GOOD_KQL}

    async def test_update_accepts_a_good_query(self, client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
        application_id = seed_context.application_ids_by_code["CLMJP"]
        headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
        created = await client.post(f"/api/applications/{application_id}/slis", headers=headers, json=_sli_body(seed_context.service_id("CLMJP", "claims-api"), "Pytest update ok SLI", GOOD_KQL))
        response = await client.patch(f"/api/slis/{created.json()['sliId']}", headers=headers, json={"queryDefinition": {"kql": GOOD_KQL + " | take 10"}})
        assert response.status_code == 200, response.text


class TestCustomSliQueryIsValidatedBeforeExecution:
    async def test_the_reader_refuses_a_stored_query_that_is_not_allowed(self, seed_context) -> None:
        end = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        async with open_session() as session:
            reader = SliMeasurementReader(session)
            with pytest.raises(QueryRejectedError):
                await reader.read_samples(
                    seed_context.service_id("CLMJP", "claims-api"), sli_kind="availability", catalog_entry_key="custom", start=end - timedelta(hours=1), end=end, interval_minutes=5,
                    query_definition={"kql": "AppRequests | union SecurityEvent | count"},
                )

    async def test_a_stored_bad_query_fails_that_sli_without_stopping_collection(self, seed_context) -> None:
        application_id = seed_context.application_ids_by_code["PAYAU"]
        async with open_session() as session:
            sli = ServiceLevelIndicator(
                application_id=application_id, service_id=seed_context.service_id("PAYAU", next(key.split("/", 1)[1] for key in seed_context.service_ids_by_key if key.startswith("PAYAU/"))),
                catalog_entry_key="custom", sli_name="Pytest stored bad SLI", sli_kind="availability", data_source_kind="log_query",
                query_definition_json={"kql": "SecurityEvent | count"}, created_by_user_principal_name="pytest", updated_by_user_principal_name="pytest",
            )
            session.add(sli)
            await session.flush()
            result = await SloService(session).backfill_sli(sli.sli_id)
        assert result is not None and result["inserted"] == 0
        assert "may only read these tables" in result["rejected"]
        async with open_session() as session:
            result = await SloService(session).collect_due_measurements(application_id)
        assert result == {"inserted": result["inserted"]}


class WindowRecordingReader:
    """Stands in for the telemetry reader and remembers which time range each backfill asked for."""

    def __init__(self) -> None:
        self.requested_ranges: list[tuple[datetime, datetime]] = []

    async def read_samples(self, service_id: str, *, start: datetime, end: datetime, **_ignored: object) -> list:
        self.requested_ranges.append((start, end))
        return []


class TestBackfillWindowComesFromSettings:
    @pytest.mark.parametrize(("sli_kind", "setting_name"), [("availability", "slo_backfill_days"), ("supporting_signal", "slo_supporting_signal_backfill_days")])
    async def test_backfill_reads_as_many_days_as_the_setting_says(self, sli_kind: str, setting_name: str, seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
        from keigan.config.settings import get_settings

        monkeypatch.setattr(get_settings(), setting_name, 11)  # the shared settings object: clearing the cache would leave later tests with a different one
        application_id = seed_context.application_ids_by_code["CLMJP"]
        reader = WindowRecordingReader()
        async with open_session() as session:
            sli = ServiceLevelIndicator(
                application_id=application_id, service_id=seed_context.service_id("CLMJP", "claims-api"), catalog_entry_key="custom", sli_name=f"Pytest {sli_kind} window",
                sli_kind=sli_kind, data_source_kind="log_query", query_definition_json={"kql": GOOD_KQL}, created_by_user_principal_name="pytest", updated_by_user_principal_name="pytest",
            )
            session.add(sli)
            await session.flush()
            result = await SloService(session, reader=reader).backfill_sli(sli.sli_id)  # type: ignore[arg-type]
        (start, end), = reader.requested_ranges
        assert end - start == timedelta(days=11)
        assert result is not None and result["days"] == 11


class TestSliListLoadsInBulk:
    async def test_listing_slis_runs_a_constant_number_of_queries(self, client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
        application_id = seed_context.application_ids_by_code["CLMJP"]
        headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
        for number in range(4):
            created = await client.post(
                f"/api/applications/{application_id}/slis", headers=headers, json={**_sli_body(seed_context.service_id("CLMJP", "claims-api"), f"Pytest bulk SLI {number}", GOOD_KQL), "targetPercentage": 99.0}
            )
            assert created.status_code == 201, created.text
        statements: list[str] = []
        async with open_session() as session:
            engine = session.get_bind()
            sync_engine = engine.sync_engine if hasattr(engine, "sync_engine") else engine

            def record(connection, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
                statements.append(statement)

            event.listen(sync_engine, "before_cursor_execute", record)
            try:
                responses = await SloService(session).list_slis(application_id)
            finally:
                event.remove(sync_engine, "before_cursor_execute", record)
        assert len(responses) >= 4
        assert len(statements) <= 3, statements
        assert all(item.service_name for item in responses if item.service_id)
        assert sum(1 for item in responses if item.slo is not None) >= 4


class TestProposalFailureDoesNotShowInternalDetail:
    async def test_the_stored_error_message_is_generic_and_the_cause_is_logged(self, seed_context, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        from keigan.services.sli_proposal_service import SliProposalService

        async def fail(self: SliProposalService, service: object) -> dict:
            raise RuntimeError("connect failed to internal-host-9.corp.example")

        monkeypatch.setattr(SliProposalService, "_measure_service", fail)
        application_id = seed_context.application_ids_by_code["BENSA"]
        async with open_session() as session:
            with caplog.at_level("ERROR"):
                await SliProposalService(session).measure(application_id)
            proposals = await SliProposalService(session).get_proposals(application_id)
        assert proposals.measurement_status == "failed"
        assert "internal-host-9" not in (proposals.error_message or "")
        assert proposals.error_message
        assert "internal-host-9" in caplog.text


class TestFailedNotificationIsLoggedNotHidden:
    async def test_a_failed_burn_notification_is_a_warning_that_names_the_burn_alert(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from types import SimpleNamespace

        from keigan.services.notification_service import NotificationService

        async def refuse(self: NotificationService, burn_alert_id: str) -> None:
            raise RuntimeError("mail relay refused")

        monkeypatch.setattr(NotificationService, "notify_slo_burn_alert", refuse)
        async with open_session() as session:
            await SloService(session)._notify(SimpleNamespace(slo_burn_alert_id="burn-alert-7"))  # type: ignore[arg-type]
        assert any(record.levelno == logging.WARNING and "burn-alert-7" in record.getMessage() for record in caplog.records)
