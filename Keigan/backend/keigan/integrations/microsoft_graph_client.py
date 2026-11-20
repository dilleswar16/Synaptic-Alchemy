"""Microsoft Graph calls used by notifications: group chats, app installation, chat messages, mail and people search.

Only used when ``TEAMS_MODE=graph`` / ``EMAIL_MODE=graph``; simulated modes never construct requests. Keigan's own Azure identity
(managed identity in AKS) obtains the application permission token for ``https://graph.microsoft.com/.default``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from keigan.config.settings import get_settings
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.azure_identity_provider import AzureCredentialProvider

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
USER_SELECT_FIELDS = "id,displayName,mail,userPrincipalName,jobTitle"


class MicrosoftGraphClient:
    def __init__(self, credential_provider: AzureCredentialProvider):
        self.credential_provider = credential_provider
        self.settings = get_settings()

    async def _request(self, method: str, path: str, *, json_body: Any = None, params: dict[str, Any] | None = None, extra_headers: dict[str, str] | None = None) -> httpx.Response:
        request_url = f"{GRAPH_BASE_URL}{path}"
        access_token = await self.credential_provider.get_access_token(GRAPH_SCOPE, self.settings.azure_tenant_id)
        request_headers = {"Authorization": f"Bearer {access_token}", **(extra_headers or {})}
        response = httpx.Response(500)
        async with httpx.AsyncClient(timeout=30) as http_client:
            for attempt_index in range(4):
                response = await http_client.request(method, request_url, headers=request_headers, json=json_body, params=params)
                if response.status_code not in (429, 503, 504) or attempt_index == 3:
                    break
                await asyncio.sleep(min(float(response.headers.get("Retry-After", 2 ** (attempt_index + 1))), 30))
        if response.status_code >= 400:
            try:
                error_body = response.json().get("error", {})
                error_message = f"{error_body.get('code', '')}: {error_body.get('message', '')}"
            except ValueError:
                error_message = response.text[:300]
            raise IntegrationException(f"Microsoft Graph returned {response.status_code} for {method} {path[:120]}: {error_message[:400]}", error_code="graph_request_failed")
        return response

    # ── Groups (application access) ────────────────────────────────────────────
    async def find_group(self, display_name: str | None, object_id: str | None) -> dict[str, Any] | None:
        """The Entra group by object ID when known, otherwise by exact display name. Needs GroupMember.Read.All (or Group.Read.All)."""
        try:
            if object_id:
                return (await self._request("GET", f"/groups/{object_id}", params={"$select": "id,displayName"})).json()
            escaped_name = (display_name or "").replace("'", "''")
            matching_groups = (await self._request("GET", "/groups", params={"$filter": f"displayName eq '{escaped_name}'", "$select": "id,displayName", "$top": 2})).json().get("value", [])
        except IntegrationException as lookup_error:
            if "returned 404" in lookup_error.detail:
                return None
            raise
        return matching_groups[0] if matching_groups else None

    async def describe_group_members(self, group_id: str, maximum_names: int = 5) -> tuple[int, list[str]]:
        """Transitive user count and a few display names (nested groups count, as they do for sign-in)."""
        response = await self._request(
            "GET", f"/groups/{group_id}/transitiveMembers/microsoft.graph.user",
            params={"$count": "true", "$select": "displayName", "$top": maximum_names}, extra_headers={"ConsistencyLevel": "eventual"},
        )
        body = response.json()
        member_names = [member.get("displayName", "") for member in body.get("value", []) if member.get("displayName")]
        return int(body.get("@odata.count", len(member_names))), member_names

    # ── Directory ──────────────────────────────────────────────────────────────
    async def search_people(self, query_text: str, maximum_results: int = 10) -> list[dict[str, Any]]:
        escaped_query = query_text.replace('"', "")
        response = await self._request(
            "GET", "/users", params={"$search": f'"displayName:{escaped_query}" OR "mail:{escaped_query}"', "$top": maximum_results, "$select": USER_SELECT_FIELDS},
            extra_headers={"ConsistencyLevel": "eventual"},
        )
        return response.json().get("value", [])

    async def get_user_by_principal_name(self, user_principal_name: str) -> dict[str, Any] | None:
        try:
            response = await self._request("GET", f"/users/{user_principal_name}", params={"$select": USER_SELECT_FIELDS})
        except IntegrationException:
            return None
        return response.json()

    # ── Teams chats ────────────────────────────────────────────────────────────
    async def create_group_chat(self, topic: str, member_entra_object_ids: list[str]) -> dict[str, Any]:
        members = [
            {"@odata.type": "#microsoft.graph.aadUserConversationMember", "roles": ["owner"], "user@odata.bind": f"{GRAPH_BASE_URL}/users('{object_id}')"}
            for object_id in member_entra_object_ids
        ]
        response = await self._request("POST", "/chats", json_body={"chatType": "group", "topic": topic, "members": members})
        return response.json()

    async def install_app_in_chat(self, chat_id: str, teams_app_catalog_id: str) -> None:
        await self._request("POST", f"/chats/{chat_id}/installedApps", json_body={"teamsApp@odata.bind": f"{GRAPH_BASE_URL}/appCatalogs/teamsApps/{teams_app_catalog_id}"})

    async def list_chat_messages_since(self, chat_id: str, since: datetime | None) -> list[dict[str, Any]]:
        """Messages modified after ``since`` (oldest first). Requires the RSC permission ChatMessage.Read.Chat granted to the installed app."""
        parameters: dict[str, Any] = {"$top": 50, "$orderby": "lastModifiedDateTime desc"}
        if since is not None:
            parameters["$filter"] = f"lastModifiedDateTime gt {since.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
        response = await self._request("GET", f"/chats/{chat_id}/messages", params=parameters)
        return list(reversed(response.json().get("value", [])))

    # ── Mail ───────────────────────────────────────────────────────────────────
    async def send_mail(self, recipient_address: str, subject_line: str, body_html: str) -> None:
        message = {
            "message": {"subject": subject_line, "body": {"contentType": "HTML", "content": body_html}, "toRecipients": [{"emailAddress": {"address": recipient_address}}]},
            "saveToSentItems": False,
        }
        await self._request("POST", f"/users/{self.settings.graph_sender_mailbox}/sendMail", json_body=message)
