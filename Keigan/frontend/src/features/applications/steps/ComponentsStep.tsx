import { useState } from "react";
import { ChevronDown, ChevronUp, Cloud, Cpu, Network, Plus, RefreshCw, Server, ShieldCheck, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useComponentJob, useComponents, useDeleteComponent, type ApplicationComponent, type ComponentType } from "@/api/applicationsApi";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { AddComponentSheet } from "../components/AddComponentSheet";
import { ResourceExplorer, type ExplorerFilter } from "../components/ResourceExplorer";
import { RoleGrantPanel } from "../components/RoleGrantPanel";
import { StepFrame } from "../components/StepFrame";
import { VerificationChecklist } from "../components/VerificationChecklist";
import type { StepProps } from "../stepRegistry";

const typeIcons: Record<ComponentType, typeof Cloud> = { azure_resource_group: Cloud, hardware: Network, mainframe: Server, saas_platform: Cpu };
const statusTones: Record<ApplicationComponent["accessVerificationStatus"], StatusTone> = {
  not_checked: "neutral",
  checking: "info",
  verified: "success",
  missing_roles: "warning",
  failed: "danger",
  not_applicable: "neutral",
};

interface ComponentCardProps {
  applicationId: string;
  component: ApplicationComponent;
  canEdit: boolean;
  onChanged?: () => void;
}

function ComponentCard({ applicationId, component, canEdit, onChanged }: ComponentCardProps) {
  const { t } = useTranslation("onboarding");
  const verifyComponent = useComponentJob(applicationId, "verify");
  const discoverComponent = useComponentJob(applicationId, "discover");
  const deleteComponent = useDeleteComponent(applicationId);
  const [isConfirmingRemoval, setIsConfirmingRemoval] = useState(false);
  const [isAccessOpen, setIsAccessOpen] = useState(false);
  const [explorerFilter, setExplorerFilter] = useState<ExplorerFilter | null>(null);
  const Icon = typeIcons[component.componentType];
  const isAzure = component.componentType === "azure_resource_group";
  const summary = component.discoverySummary;
  const isVerified = component.accessVerificationStatus === "verified";
  const showAccess = isAzure && !isVerified;

  const countButton = (count: number, label: string, filter: ExplorerFilter) => (
    <button type="button" className="rounded px-1 font-semibold text-action underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-action" onClick={() => setExplorerFilter(filter)}>
      {count} <span className="font-normal">{label}</span>
    </button>
  );

  return (
    <Card className="flex flex-col gap-4 p-[var(--card-padding)]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-action"><Icon size={20} aria-hidden="true" /></span>
          <div className="min-w-0">
            <h3 className="truncate text-h3 font-semibold">{component.componentName}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusChip size="sm" icon={false} tone="neutral">{t(`environments.${component.environmentName}`)}</StatusChip>
              <StatusChip size="sm" tone={statusTones[component.accessVerificationStatus]} dot pulse={component.accessVerificationStatus === "checking"}>
                {t(`status.${component.accessVerificationStatus}`)}
              </StatusChip>
              {component.isSimulated && isAzure ? <StatusChip size="sm" tone="ai" icon={false}>{t("status.simulated")}</StatusChip> : null}
            </div>
          </div>
        </div>
        {canEdit ? (
          <div className="flex shrink-0 gap-1">
            {isAzure ? (
              <Button size="sm" variant="secondary" leadingIcon={ShieldCheck} isLoading={verifyComponent.isPending || component.accessVerificationStatus === "checking"} onClick={() => verifyComponent.mutate(component.componentId)}>
                {t("card.verify")}
              </Button>
            ) : null}
            {isVerified ? (
              <Button size="sm" variant="secondary" leadingIcon={RefreshCw} isLoading={discoverComponent.isPending} onClick={() => discoverComponent.mutate(component.componentId, { onSuccess: onChanged })}>
                {t("card.refresh")}
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" leadingIcon={Trash2} aria-label={t("card.remove")} onClick={() => setIsConfirmingRemoval(true)}>{t("card.remove")}</Button>
          </div>
        ) : null}
      </div>

      <p className="text-body-sm text-muted">
        {isAzure ? `${component.azureSubscriptionName ?? component.azureSubscriptionId} / ${component.azureResourceGroupName}` : t(`types.${component.componentType}.description`)}
        {component.lastVerifiedAt ? <> · {t("card.checked")} <RelativeTime value={component.lastVerifiedAt} /></> : null}
      </p>

      {summary ? (
        <p className="text-body-sm">
          {countButton(summary.resourcesFound, t("card.resourcesFound"), "all")} · {countButton(summary.monitoredServices, t("card.monitoredServices"), "monitored_service")} ·{" "}
          {countButton(summary.telemetrySources, t("card.telemetrySources"), "telemetry_source")}
        </p>
      ) : component.serviceCount > 0 ? (
        <p className="text-body-sm text-muted">{t("card.services", { count: component.serviceCount })}</p>
      ) : null}

      {showAccess ? (
        <div className="flex flex-col gap-3 border-t border-hairline pt-4">
          <VerificationChecklist component={component} />
          <Button variant="subtle" size="sm" className="self-start" trailingIcon={isAccessOpen ? ChevronUp : ChevronDown} onClick={() => setIsAccessOpen((previous) => !previous)}>
            {t("card.showCommands")}
          </Button>
          {isAccessOpen ? <RoleGrantPanel applicationId={applicationId} component={component} /> : null}
        </div>
      ) : null}

      {isAzure && explorerFilter !== null ? <ResourceExplorer applicationId={applicationId} component={component} open onOpenChange={() => setExplorerFilter(null)} initialFilter={explorerFilter} /> : null}
      <ConfirmDialog
        open={isConfirmingRemoval}
        onOpenChange={setIsConfirmingRemoval}
        tone="danger"
        title={t("card.removeTitle", { name: component.componentName })}
        description={t("card.removeDescription", { count: component.serviceCount })}
        confirmLabel={t("card.removeConfirm")}
        onConfirm={async () => { await deleteComponent.mutateAsync(component.componentId); onChanged?.(); }}
      />
    </Card>
  );
}

export function ComponentsStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("onboarding");
  const componentsQuery = useComponents(applicationId);
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  return (
    <StepFrame stepKey="components">
      {componentsQuery.isError ? (
        <ErrorState error={componentsQuery.error} onRetry={() => void componentsQuery.refetch()} />
      ) : componentsQuery.isLoading ? (
        <Skeleton className="h-40 rounded-lg" />
      ) : (
        <div className="flex flex-col gap-4">
          {componentsQuery.data?.length === 0 ? (
            <EmptyState icon={Cloud} title={t("empty.title")} description={t("empty.description")} />
          ) : null}
          {componentsQuery.data?.map((component) => (
            <ComponentCard key={component.componentId} applicationId={applicationId} component={component} canEdit={canEdit} onChanged={onStatusChange} />
          ))}
          {canEdit ? (
            <button
              type="button"
              onClick={() => setIsSheetOpen(true)}
              className="flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border-strong px-4 py-6 text-body font-medium text-action transition-colors hover:bg-brand-soft focus-visible:ring-2 focus-visible:ring-action"
            >
              <Plus size={18} aria-hidden="true" />
              {t("card.addComponent")}
            </button>
          ) : null}
        </div>
      )}
      <AddComponentSheet applicationId={applicationId} open={isSheetOpen} onOpenChange={(open) => { setIsSheetOpen(open); if (!open) onStatusChange?.(); }} />
    </StepFrame>
  );
}
