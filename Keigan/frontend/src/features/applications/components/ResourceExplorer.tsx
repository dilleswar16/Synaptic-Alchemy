import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDiscoveredResources, type ApplicationComponent, type DiscoveredResource } from "@/api/applicationsApi";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { StatusChip } from "@/components/ui/StatusChip";

export type ExplorerFilter = "all" | DiscoveredResource["monitoringClassification"];

interface ResourceExplorerProps {
  applicationId: string;
  component: ApplicationComponent;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialFilter?: ExplorerFilter;
}

/** Every number on a component card opens this drawer (drill-down rule). Facts are shown neutrally, never as problems. */
export function ResourceExplorer({ applicationId, component, open, onOpenChange, initialFilter = "all" }: ResourceExplorerProps) {
  const { t } = useTranslation("onboarding");
  const [filter, setFilter] = useState<ExplorerFilter>(initialFilter);
  const resourcesQuery = useDiscoveredResources(applicationId, component.componentId, open);
  const rows = useMemo(
    () => (resourcesQuery.data ?? []).filter((resource) => filter === "all" || resource.monitoringClassification === filter),
    [resourcesQuery.data, filter],
  );

  const columns: DataTableColumn<DiscoveredResource>[] = [
    { key: "name", header: t("explorer.name"), isSticky: true, sortValue: (row) => row.resourceName, cell: (row) => <span className="font-medium">{row.resourceName}</span> },
    { key: "type", header: t("explorer.type"), sortValue: (row) => row.resourceTypeDisplayName, cell: (row) => row.resourceTypeDisplayName },
    {
      key: "classification",
      header: t("explorer.classification"),
      cell: (row) => (
        <StatusChip size="sm" icon={false} tone={row.monitoringClassification === "monitored_service" ? "success" : row.monitoringClassification === "telemetry_source" ? "info" : "neutral"}>
          {t(`explorer.classifications.${row.monitoringClassification}`)}
        </StatusChip>
      ),
    },
    {
      key: "diagnostics",
      header: t("explorer.diagnostics"),
      cell: (row) =>
        row.monitoringClassification !== "monitored_service" ? (
          "—"
        ) : (
          <StatusChip size="sm" icon={false} tone="neutral">
            {row.hasDiagnosticSetting ? t("explorer.diagnosticSettingOn") : t("explorer.noDiagnosticSetting")}
          </StatusChip>
        ),
    },
    {
      key: "state",
      header: t("explorer.state"),
      cell: (row) =>
        row.noLongerFoundAt ? (
          <StatusChip size="sm" icon={false} tone="neutral">{t("explorer.noLongerFound")}</StatusChip>
        ) : (
          <span className="text-muted">{t("explorer.present")}</span>
        ),
    },
  ];

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={t("explorer.title", { name: component.componentName })}
      description={t("explorer.description")}
      headerContent={
        <SegmentedControl
          aria-label={t("explorer.filter")}
          size="sm"
          value={filter}
          onValueChange={setFilter}
          options={[
            { value: "all", label: t("explorer.filters.all") },
            { value: "monitored_service", label: t("explorer.filters.monitored_service") },
            { value: "telemetry_source", label: t("explorer.filters.telemetry_source") },
            { value: "not_monitored_type", label: t("explorer.filters.not_monitored_type") },
          ]}
        />
      }
    >
      {resourcesQuery.isError ? (
        <ErrorState error={resourcesQuery.error} onRetry={() => void resourcesQuery.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowId={(row) => row.discoveredResourceId}
          caption={t("explorer.title", { name: component.componentName })}
          isLoading={resourcesQuery.isLoading}
          density="dense"
          isFlush
        />
      )}
    </Drawer>
  );
}
