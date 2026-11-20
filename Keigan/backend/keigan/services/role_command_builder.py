"""Builds the read-only role-grant commands (Azure CLI, PowerShell, Terraform, Portal steps) with Keigan's real identity IDs."""

from __future__ import annotations

from keigan.config.settings import Settings
from keigan.dtos.onboarding_dtos import RoleCommandsResponse
from keigan.entities.application_entities import ApplicationComponent
from keigan.integrations.azure_identity_provider import KeiganIdentity

REQUIRED_ROLES = [
    {"roleName": "Reader", "purpose": "List resources, read diagnostic settings and the activity log"},
    {"roleName": "Monitoring Reader", "purpose": "Read metrics, metric definitions and alert rules"},
    {"roleName": "Log Analytics Reader", "purpose": "Run log queries on the workspace (grant on the workspace if it is in another subscription)"},
]


class RoleCommandBuilder:
    def __init__(self, settings: Settings, keigan_identity: KeiganIdentity):
        self.settings = settings
        self.keigan_identity = keigan_identity

    def build(self, component: ApplicationComponent) -> RoleCommandsResponse:
        subscription_id = component.azure_subscription_id or "<subscription-id>"
        resource_group_name = component.azure_resource_group_name or "<resource-group>"
        scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
        object_id = self.keigan_identity.object_id or "<keigan-object-id-not-configured>"
        role_names = [role["roleName"] for role in REQUIRED_ROLES]

        cli_lines = [f"az account set --subscription {subscription_id}"]
        cli_lines += [
            f'az role assignment create --assignee-object-id {object_id} --assignee-principal-type ServicePrincipal --role "{role_name}" --scope {scope}'
            for role_name in role_names
        ]
        powershell_lines = [f"Set-AzContext -SubscriptionId {subscription_id}"]
        powershell_lines += [
            f'New-AzRoleAssignment -ObjectId {object_id} -RoleDefinitionName "{role_name}" -Scope "{scope}"' for role_name in role_names
        ]
        terraform_blocks = [
            f'''resource "azurerm_role_assignment" "keigan_{role_name.lower().replace(" ", "_")}" {{
  scope                = "{scope}"
  role_definition_name = "{role_name}"
  principal_id         = "{object_id}"
}}'''
            for role_name in role_names
        ]
        portal_steps = [
            f"Open the Azure portal and go to the resource group {resource_group_name} in subscription {subscription_id}.",
            "Choose Access control (IAM), then Add, then Add role assignment.",
            f"Select the role (Reader, Monitoring Reader, Log Analytics Reader) and choose Next. Repeat for each of the three roles.",
            f"Under Members choose User, group, or service principal and search for {self.keigan_identity.display_name or 'the object ID'} (object ID {object_id}).",
            "Choose Review + assign. Azure can take a few minutes to apply a new role.",
        ]
        tenant_note = None
        if component.azure_tenant_id and component.azure_tenant_id.lower() != (self.keigan_identity.tenant_id or "").lower():
            multi_tenant_client_id = self.settings.keigan_multi_tenant_app_client_id or "<not configured>"
            tenant_note = (
                f"This resource group is in another tenant ({component.azure_tenant_id}). Keigan reads it through its multi-tenant app registration "
                f"(client ID {multi_tenant_client_id}): a global or application administrator of that tenant must consent to the app, "
                "or the tenant must delegate the resource group through Azure Lighthouse. Then run the commands above in that tenant."
            )
        return RoleCommandsResponse(
            cli="\n".join(cli_lines),
            powershell="\n".join(powershell_lines),
            terraform="\n\n".join(terraform_blocks),
            portal_steps=portal_steps,
            required_roles=REQUIRED_ROLES,
            tenant_note=tenant_note,
        )
