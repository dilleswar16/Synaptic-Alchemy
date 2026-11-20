import { useTranslation } from "react-i18next";
import { usePlatformIdentity, useRoleCommands, type ApplicationComponent } from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { CopyButton } from "@/components/ui/CopyButton";
import { ErrorState } from "@/components/ui/ErrorState";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { Skeleton } from "@/components/ui/Skeleton";

/** Spec 6.3 sub-step 2: Keigan identity with copy buttons, the three read-only roles and generated commands with real IDs. */
export function RoleGrantPanel({ applicationId, component }: { applicationId: string; component: ApplicationComponent }) {
  const { t } = useTranslation("onboarding");
  const identityQuery = usePlatformIdentity();
  const commandsQuery = useRoleCommands(applicationId, component.componentId, true);
  const commands = commandsQuery.data;
  const identity = identityQuery.data;

  if (commandsQuery.isError) return <ErrorState size="sm" error={commandsQuery.error} onRetry={() => void commandsQuery.refetch()} />;
  if (!commands || !identity) return <Skeleton className="h-48 rounded-lg" />;

  const everything = [commands.cli, "", commands.powershell].join("\n");
  const shareableText = `${t("roleGrant.shareIntro", { resourceGroup: component.azureResourceGroupName })}\n${window.location.origin}/applications/${applicationId}/components\n\n${everything}`;

  const notConfigured = t("roleGrant.notConfigured");
  return (
    <div className="flex flex-col gap-4">
      {identity.isComplete ? null : (
        <Banner tone="warning" title={t("roleGrant.identityIncompleteTitle")}>
          {t("roleGrant.identityIncompleteBody", { values: identity.missingValues.join(", ") })}
        </Banner>
      )}
      <KeyValueList
        dense
        isDivided
        items={[
          { key: "tenant", label: t("roleGrant.tenantId"), value: identity.tenantId ?? notConfigured, copyValue: identity.tenantId ?? undefined, isMonospace: Boolean(identity.tenantId) },
          { key: "client", label: t("roleGrant.clientId"), value: identity.clientId ?? notConfigured, copyValue: identity.clientId ?? undefined, isMonospace: Boolean(identity.clientId) },
          { key: "object", label: t("roleGrant.objectId"), value: identity.objectId ?? notConfigured, copyValue: identity.objectId ?? undefined, isMonospace: Boolean(identity.objectId) },
          { key: "name", label: t("roleGrant.displayName"), value: identity.displayName ?? t("roleGrant.displayNameUnknown"), copyValue: identity.displayName ?? undefined },
        ]}
      />
      {identity.identitySource === "discovered" ? <p className="text-caption text-muted">{t("roleGrant.identityDiscovered")}</p> : null}
      <div>
        <div className="mb-2 text-body-sm font-semibold">{t("roleGrant.rolesTitle")}</div>
        <ul className="flex flex-col gap-1.5 text-body-sm">
          {commands.requiredRoles.map((role) => (
            <li key={role.roleName} className="flex gap-2">
              <span className="font-mono font-medium">{role.roleName}</span>
              <span className="text-muted">{role.purpose}</span>
            </li>
          ))}
        </ul>
      </div>
      {commands.tenantNote ? <Banner tone="info">{commands.tenantNote}</Banner> : null}
      <CommandBlock
        riskLevel="low"
        commands={[
          { key: "cli", label: t("roleGrant.tabs.cli"), content: commands.cli },
          { key: "powershell", label: t("roleGrant.tabs.powershell"), content: commands.powershell },
          { key: "terraform", label: t("roleGrant.tabs.terraform"), content: commands.terraform },
          { key: "portal", label: t("roleGrant.tabs.portal"), content: commands.portalSteps.map((step, index) => `${index + 1}. ${step}`).join("\n") },
        ]}
        wrapLines
      />
      <div className="flex flex-wrap gap-2">
        <CopyButton showLabel variant="secondary" size="md" label={t("roleGrant.copyAll")} value={everything} />
        <CopyButton showLabel variant="secondary" size="md" label={t("roleGrant.sendToSomeone")} value={shareableText} />
      </div>
    </div>
  );
}
