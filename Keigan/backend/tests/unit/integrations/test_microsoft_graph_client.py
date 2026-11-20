"""keigan/integrations/microsoft_graph_client.py: looking up an Entra group by display name (W2-3)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from keigan.exceptions.keigan_exceptions import AmbiguousGroupNameException
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
