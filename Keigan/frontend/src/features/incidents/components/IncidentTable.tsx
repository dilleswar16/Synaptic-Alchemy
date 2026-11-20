import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import type { IncidentSummary } from "@/api/incidentsApi";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { PriorityChip } from "@/components/ui/PriorityChip";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDuration } from "@/utils/formatters";
import { cn } from "@/utils/cn";
import { incidentStatusTone, isOpenIncident } from "./incidentPresentation";

interface IncidentTableProps {
  incidents: IncidentSummary[];
  isLoading: boolean;
  totalCount: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function incidentRoute(incident: IncidentSummary): string | null {
  return incident.latestInvestigationId ? `/investigations/${incident.latestInvestigationId}` : null;
}

export function IncidentPriority({ incident }: { incident: IncidentSummary }) {
  const { t } = useTranslation("incidents");
  const keiganPriority = incident.keiganPriority ?? incident.servicenowPriority;
  if (!keiganPriority) return <span className="text-muted">-</span>;
  return (
    <div className="flex flex-col items-start gap-1">
      <PriorityChip priority={keiganPriority} size="sm" />
      {incident.servicenowPriority && incident.servicenowPriority !== keiganPriority ? (
        <span className="text-micro text-muted">{t("servicenowPriority", { priority: incident.servicenowPriority })}</span>
      ) : null}
    </div>
  );
}

export function IncidentTable({ incidents, isLoading, totalCount, page, pageSize, onPageChange }: IncidentTableProps) {
  const { t } = useTranslation("incidents");
  const navigate = useNavigate();
  const columns: DataTableColumn<IncidentSummary>[] = [
    { key: "priority", header: t("columns.priority"), width: "5.5rem", cell: (incident) => <IncidentPriority incident={incident} />, sortValue: (incident) => incident.keiganPriority ?? "P9" },
    { key: "number", header: t("columns.number"), width: "8.5rem", cell: (incident) => <span className={cn("whitespace-nowrap font-mono text-body-sm", !isOpenIncident(incident.incidentStatus) && "text-muted")}>{incident.externalIncidentNumber ?? t("noNumber")}</span>, sortValue: (incident) => incident.externalIncidentNumber },
    {
      key: "title",
      header: t("columns.title"),
      cell: (incident) => (
        <div className="flex min-w-[11rem] max-w-[15.5rem] min-[1400px]:max-w-[19rem] flex-col">
          <span className={cn("line-clamp-2 break-words", isOpenIncident(incident.incidentStatus) ? "font-medium text-default" : "text-muted")} title={incident.incidentTitle}>{incident.incidentTitle}</span>
          <span className="truncate text-caption text-muted" title={[incident.application.applicationName, incident.assignmentGroupName].filter(Boolean).join(" · ")}>
            {incident.application.applicationName} · {incident.affectedServiceNames.slice(0, 3).join(", ") || t("noServices")}
          </span>
        </div>
      ),
      sortValue: (incident) => incident.incidentTitle,
    },
    {
      key: "status",
      header: t("columns.status"),
      width: "8rem",
      cell: (incident) => (
        <StatusChip tone={incidentStatusTone[incident.incidentStatus]} size="sm" pulse={incident.incidentStatus === "investigating"}>
          {t(`status.${incident.incidentStatus}`)}
        </StatusChip>
      ),
      sortValue: (incident) => incident.incidentStatus,
    },
    {
      key: "confidence",
      header: t("columns.confidence"),
      width: "10.5rem",
      cell: (incident) =>
        incident.keiganConfidence !== null ? <ConfidenceMeter percentage={Math.round(incident.keiganConfidence * 100)} size="sm" /> : <span className="text-caption text-muted">{incident.latestInvestigationStatus === "running" || incident.latestInvestigationStatus === "queued" ? t("analysing") : "-"}</span>,
      sortValue: (incident) => incident.keiganConfidence,
    },
    {
      key: "detected",
      header: t("columns.detected"),
      cell: (incident) => (
        <div className="flex max-w-[9rem] flex-col min-[1400px]:max-w-none">
          <RelativeTime value={incident.detectedByKeiganAt} className="block truncate text-body-sm" />
          <span className={isOpenIncident(incident.incidentStatus) ? "text-caption font-medium text-default" : "text-caption text-muted"} title={t("columns.duration")}>
            {t(isOpenIncident(incident.incidentStatus) ? "duration.open" : "duration.resolved", { duration: formatDuration(incident.durationMinutes * 60_000, { maximumUnits: 2, unitDisplay: "narrow" }) })}
          </span>
        </div>
      ),
      sortValue: (incident) => incident.detectedByKeiganAt,
    },
  ];
  return (
    <DataTable
      caption={t("tableCaption")}
      columns={columns}
      rows={incidents}
      getRowId={(incident) => incident.incidentId}
      isLoading={isLoading}
      density="dense"
      isManualSorting={false}
      onRowClick={(incident) => {
        const route = incidentRoute(incident);
        if (route) void navigate(route);
      }}
      serverPagination={{ page, pageSize, totalCount, onPageChange }}
      emptyState={<EmptyState title={t("empty.title")} description={t("empty.description")} size="sm" />}
    />
  );
}
