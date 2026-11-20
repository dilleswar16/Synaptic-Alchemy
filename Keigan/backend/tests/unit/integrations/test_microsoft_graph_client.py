"""keigan/integrations/microsoft_graph_client.py: looking up an Entra group by display name (W2-3)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from keigan.exceptions.keigan_exceptions import AmbiguousGroupNameException, IntegrationException
from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient

FIRST_GROUP_ID = "11111111-1111-1111-1111-111111111111"
SECOND_GROUP_ID = "22222222-2222-2222-2222-222222222222"


def graph_client_answering(monkeypatch: pytest.MonkeyPatch, groups: list[dict[str, str]]) -> MicrosoftGraphClient:
    """A client whose Graph calls return ``groups`` as the result of any group search."""

    async def fake_request(_self: object, _method: str, _path: str, **_arguments: Any) -> httpx.Response:
        return httpx.Response(200, json={"value": groups})

    monkeypatch.setattr(MicrosoftGraphClient, "_request", fake_request)
    return MicrosoftGraphClient(credential_provider=None)  # type: ignore[arg-type]


async def test_group_found_by_name_is_returned_when_only_one_group_has_that_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = graph_client_answering(monkeypatch, [{"id": FIRST_GROUP_ID, "displayName": "CLAIMS_admin"}])
    assert await client.find_group("CLAIMS_admin", None) == {"id": FIRST_GROUP_ID, "displayName": "CLAIMS_admin"}


async def test_no_group_is_returned_when_no_group_has_that_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = graph_client_answering(monkeypatch, [])
    assert await client.find_group("CLAIMS_admin", None) is None


async def test_two_groups_with_the_same_name_are_never_guessed_between(monkeypatch: pytest.MonkeyPatch) -> None:
    client = graph_client_answering(monkeypatch, [{"id": FIRST_GROUP_ID, "displayName": "CLAIMS_admin"}, {"id": SECOND_GROUP_ID, "displayName": "CLAIMS_admin"}])
    with pytest.raises(AmbiguousGroupNameException) as ambiguity:
        await client.find_group("CLAIMS_admin", None)
    assert ambiguity.value.detail == (
        "Two or more Entra groups are named 'CLAIMS_admin'. An admin must link the right group by its object ID in 'Check in Entra'."
    )


GRAPH_RAW_BODY = {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation for jane.doe@example.com"}}


@pytest.mark.parametrize(
    ("status_code", "error_code", "expected_advice"),
    [(403, "graph_forbidden", "refused"), (404, "graph_not_found", "could not find"), (429, "graph_throttled", "busy"), (500, "graph_request_failed", "returned an error (500)")],
)
def test_graph_failure_has_a_plain_message_a_distinct_code_and_the_status(status_code: int, error_code: str, expected_advice: str, caplog: pytest.LogCaptureFixture) -> None:
    response = httpx.Response(status_code, json=GRAPH_RAW_BODY, request=httpx.Request("GET", "https://graph.microsoft.com/v1.0/users/jane.doe@example.com"))
    with caplog.at_level("WARNING", logger="keigan.integrations.microsoft_graph_client"), pytest.raises(IntegrationException) as raised:
        MicrosoftGraphClient._raise_for_status(response, "GET", "/users/jane.doe@example.com")
    assert (raised.value.error_code, raised.value.extra["upstreamStatus"]) == (error_code, status_code)
    assert expected_advice in raised.value.detail
    assert "Authorization_RequestDenied" not in raised.value.detail and "jane.doe" not in raised.value.detail
    assert any("Authorization_RequestDenied" in record.getMessage() for record in caplog.records)


def graph_client_failing_with(monkeypatch: pytest.MonkeyPatch, status_code: int) -> MicrosoftGraphClient:
    async def fake_request(_self: object, _method: str, _path: str, **_arguments: Any) -> httpx.Response:
        MicrosoftGraphClient._raise_for_status(httpx.Response(status_code, json=GRAPH_RAW_BODY), "GET", "/users/x")
        raise AssertionError("unreachable")

    monkeypatch.setattr(MicrosoftGraphClient, "_request", fake_request)
    return MicrosoftGraphClient(credential_provider=None)  # type: ignore[arg-type]


async def test_a_user_who_is_not_in_the_directory_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await graph_client_failing_with(monkeypatch, 404).get_user_by_principal_name("ghost@example.com") is None


@pytest.mark.parametrize("status_code", [403, 429, 500])
async def test_a_failed_user_lookup_is_an_error_not_a_missing_user(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    """None means "this person is not in Entra". A permission or outage problem must not look like that."""
    with pytest.raises(IntegrationException):
        await graph_client_failing_with(monkeypatch, status_code).get_user_by_principal_name("jane@example.com")


async def test_a_group_lookup_treats_only_not_found_as_no_group(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await graph_client_failing_with(monkeypatch, 404).find_group(None, FIRST_GROUP_ID) is None
    with pytest.raises(IntegrationException):
        await graph_client_failing_with(monkeypatch, 403).find_group(None, FIRST_GROUP_ID)
