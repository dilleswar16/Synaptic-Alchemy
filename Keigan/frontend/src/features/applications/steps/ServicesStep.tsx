import { useMemo, useState } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useAddService,
  useBulkUpdateServices,
  useComponents,
  useServices,
  useUpdateService,
  type CriticalityTier,
  type EnvironmentName,
  type MonitoredServiceRow,
  type ServiceBulkChanges,
} from "@/api/applicationsApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { CountWithInfo } from "@/components/ui/CountWithInfo";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import { Switch } from "@/components/ui/Switch";
import { LogSourceForm } from "../components/LogSourceEditor";
import { ServiceDrawer } from "../components/ServiceDrawer";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

const environments: EnvironmentName[] = ["dev", "test", "uat", "prod"];
const tiers: CriticalityTier[] = ["tier_1", "tier_2", "tier_3"];
const serviceTypes = ["aks", "function_app", "app_service", "logic_app", "api_management", "data_factory", "sql_database", "network_appliance", "mainframe_subsystem", "batch_job_stream", "saas_service"];

function AddServiceDialog({ applicationId, open, onOpenChange }: { applicationId: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation("onboarding");
  const addService = useAddService(applicationId);
  const componentsQuery = useComponents(applicationId);
  const [form, setForm] = useState({ serviceName: "", serviceType: "app_service", componentId: "", environmentName: "prod" as EnvironmentName, criticalityTier: "tier_2" as CriticalityTier });
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("services.addTitle")}
      description={t("services.addDescription")}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>{t("add.cancel")}</Button>
          <Button
            disabled={!form.serviceName.trim()}
            isLoading={addService.isPending}
            onClick={() => addService.mutate({ ...form, componentId: form.componentId || null }, { onSuccess: () => { onOpenChange(false); setForm({ ...form, serviceName: "" }); } })}
          >
            {t("services.addService")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Input label={t("services.name")} value={form.serviceName} onChange={(event) => setForm({ ...form, serviceName: event.target.value })} />
        <Select label={t("services.type")} value={form.serviceType} options={serviceTypes.map((type) => ({ value: type, label: t(`serviceTypes.${type}`) }))} onValueChange={(serviceType) => setForm({ ...form, serviceType })} />
        <Select
          label={t("services.component")}
          isOptional
          value={form.componentId || undefined}
          placeholder={t("add.choose")}
          options={(componentsQuery.data ?? []).map((component) => ({ value: component.componentId, label: component.componentName }))}
          onValueChange={(componentId) => setForm({ ...form, componentId })}
        />
        <div className="grid grid-cols-2 gap-4">
          <Select label={t("services.environment")} value={form.environmentName} options={environments.map((environment) => ({ value: environment, label: t(`environments.${environment}`) }))} onValueChange={(environmentName) => setForm({ ...form, environmentName })} />
          <Select label={t("services.criticality")} value={form.criticalityTier} options={tiers.map((tier) => ({ value: tier, label: t(`tiers.${tier}`) }))} onValueChange={(criticalityTier) => setForm({ ...form, criticalityTier })} />
        </div>
        {addService.isError ? <Banner tone="danger">{isApiError(addService.error) ? addService.error.detail : t("add.failed")}</Banner> : null}
      </div>
    </Dialog>
  );
}

/** Spec 6.4: one editable full-width table for every service (Azure, hardware, mainframe, SaaS), bulk actions, drawer for the details. */
export function ServicesStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("onboarding");
  const servicesQuery = useServices(applicationId);
  const updateService = useUpdateService(applicationId);
  const bulkUpdate = useBulkUpdateServices(applicationId);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [drawerServiceId, setDrawerServiceId] = useState<string | null>(null);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isLogSourceDialogOpen, setIsLogSourceDialogOpen] = useState(false);
  const services = useMemo(() => servicesQuery.data ?? [], [servicesQuery.data]);
  const nameById = useMemo(() => new Map(services.map((service) => [service.serviceId, service.serviceName])), [services]);

  const patch = (service: MonitoredServiceRow, body: Parameters<typeof updateService.mutate>[0]["body"]) => updateService.mutate({ serviceId: service.serviceId, body }, { onSuccess: onStatusChange });
  const bulk = (changes: ServiceBulkChanges) =>
    bulkUpdate.mutate({ serviceIds: [...selectedIds], changes }, { onSuccess: () => { onStatusChange?.(); setIsLogSourceDialogOpen(false); } });

  const columns: DataTableColumn<MonitoredServiceRow>[] = [
    {
      key: "monitor",
      header: t("services.columns.monitor"),
      width: "90px",
      cell: (row) => <Switch size="sm" aria-label={t("services.columns.monitor")} checked={row.isMonitoringEnabled} disabled={!canEdit} onCheckedChange={(checked) => patch(row, { isMonitoringEnabled: checked })} />,
    },
    {
      key: "service",
      header: t("services.columns.service"),
      isSticky: true,
      sortValue: (row) => row.serviceName,
      cell: (row) => (
        <div className="min-w-0">
          <button type="button" className="block max-w-[260px] truncate text-left font-semibold text-action hover:underline" onClick={() => setDrawerServiceId(row.serviceId)}>{row.serviceName}</button>
          <div className="truncate text-caption text-muted">{t(`serviceTypes.${row.serviceType}`, { defaultValue: row.serviceType })}{row.componentName ? ` · ${row.componentName}` : ""}</div>
          {row.noLongerFoundAt ? <StatusChip size="sm" icon={false} tone="neutral">{t("services.noLongerFound")}</StatusChip> : null}
        </div>
      ),
    },
    {
      key: "environment",
      header: t("services.columns.environment"),
      width: "120px",
      cell: (row) => <Select size="sm" aria-label={t("services.columns.environment")} disabled={!canEdit} value={row.environmentName} options={environments.map((environment) => ({ value: environment, label: t(`environments.${environment}`) }))} onValueChange={(environmentName) => patch(row, { environmentName })} />,
    },
    {
      key: "criticality",
      header: t("services.columns.criticality"),
      width: "120px",
      cell: (row) => <Select size="sm" aria-label={t("services.columns.criticality")} disabled={!canEdit} value={row.criticalityTier} options={tiers.map((tier) => ({ value: tier, label: t(`tiers.${tier}`) }))} onValueChange={(criticalityTier) => patch(row, { criticalityTier })} />,
    },
    {
      key: "logs",
      header: t("services.columns.logs"),
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.logSources.filter((source) => source.sourceKind !== "azure_monitor_metrics").map((source) => (
            <StatusChip key={source.serviceLogSourceId} size="sm" icon={false} tone={source.lastReadTestStatus === "failed" ? "warning" : "info"}>
              {source.logToolConnectionName ?? t(`logSource.chips.${source.sourceKind}`)}
            </StatusChip>
          ))}
          {row.hasDiagnosticSetting === false ? <StatusChip size="sm" icon={false} tone="neutral">{t("services.noDiagnosticSetting")}</StatusChip> : null}
          {row.logSources.length === 0 && row.hasDiagnosticSetting !== false ? <span className="text-muted">—</span> : null}
        </div>
      ),
    },
    {
      key: "metrics",
      header: t("services.columns.metrics"),
      cell: (row) =>
        row.availableMetricCount ? (
          <CountWithInfo count={row.availableMetricCount} label={t("services.available")} title={t("services.metricsTitle")} items={(row.availableMetrics ?? []).map((metric) => ({ key: metric.name, label: metric.displayName, secondary: metric.unit }))} maximumItems={8} onViewAll={() => setDrawerServiceId(row.serviceId)} />
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "dependsOn",
      header: t("services.columns.dependsOn"),
      cell: (row) =>
        row.dependsOnServiceIds.length ? (
          <CountWithInfo count={row.dependsOnServiceIds.length} title={t("services.dependsOnTitle")} items={row.dependsOnServiceIds.map((serviceId) => ({ key: serviceId, label: nameById.get(serviceId) ?? serviceId }))} onViewAll={() => setDrawerServiceId(row.serviceId)} />
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "repository",
      header: t("services.columns.repository"),
      cell: (row) => (row.repositoryUrl ? <a className="block max-w-[160px] truncate text-action hover:underline" href={row.repositoryUrl} target="_blank" rel="noopener noreferrer">{row.repositoryUrl.replace(/^https?:\/\//, "")}</a> : <span className="text-muted">—</span>),
    },
    { key: "actions", header: <span className="sr-only">{t("services.columns.actions")}</span>, width: "56px", cell: (row) => <IconButton icon={MoreHorizontal} label={t("services.openDetails")} variant="ghost" size="sm" onClick={() => setDrawerServiceId(row.serviceId)} /> },
  ];

  return (
    <StepFrame stepKey="services" actions={canEdit ? <Button variant="secondary" leadingIcon={Plus} onClick={() => setIsAddOpen(true)}>{t("services.addService")}</Button> : undefined}>
      {servicesQuery.isError ? (
        <ErrorState error={servicesQuery.error} onRetry={() => void servicesQuery.refetch()} />
      ) : (
        <>
          {selectedIds.size > 0 && canEdit ? (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-hairline bg-brand-soft px-4 py-2">
              <span className="text-body-sm font-semibold">{t("services.selected", { count: selectedIds.size })}</span>
              <Select size="sm" aria-label={t("services.bulk.setEnvironment")} placeholder={t("services.bulk.setEnvironment")} options={environments.map((environment) => ({ value: environment, label: t(`environments.${environment}`) }))} onValueChange={(environmentName) => bulk({ environmentName })} />
              <Select size="sm" aria-label={t("services.bulk.setCriticality")} placeholder={t("services.bulk.setCriticality")} options={tiers.map((tier) => ({ value: tier, label: t(`tiers.${tier}`) }))} onValueChange={(criticalityTier) => bulk({ criticalityTier })} />
              <Button size="sm" variant="secondary" onClick={() => setIsLogSourceDialogOpen(true)}>{t("services.bulk.addLogSource")}</Button>
              <Button size="sm" variant="secondary" onClick={() => bulk({ isMonitoringEnabled: false })}>{t("services.bulk.monitoringOff")}</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>{t("services.bulk.clear")}</Button>
            </div>
          ) : null}
          <DataTable
            columns={columns}
            rows={services}
            getRowId={(row) => row.serviceId}
            caption={t("services.caption")}
            isLoading={servicesQuery.isLoading}
            selectedRowIds={selectedIds}
            onSelectedRowIdsChange={canEdit ? setSelectedIds : undefined}
            emptyState={<EmptyState title={t("services.emptyTitle")} description={t("services.emptyDescription")} />}
            defaultSort={{ columnKey: "service", direction: "ascending" }}
          />
        </>
      )}
      <ServiceDrawer applicationId={applicationId} serviceId={drawerServiceId} canEdit={canEdit} onOpenChange={(open) => { if (!open) { setDrawerServiceId(null); onStatusChange?.(); } }} />
      <AddServiceDialog applicationId={applicationId} open={isAddOpen} onOpenChange={setIsAddOpen} />
      <Dialog open={isLogSourceDialogOpen} onOpenChange={setIsLogSourceDialogOpen} title={t("services.bulk.addLogSourceTitle", { count: selectedIds.size })}>
        <LogSourceForm applicationId={applicationId} isSubmitting={bulkUpdate.isPending} onSubmit={(addLogSource) => bulk({ addLogSource })} />
      </Dialog>
    </StepFrame>
  );
}
