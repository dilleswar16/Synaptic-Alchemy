import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import type { IncidentSummary } from "@/api/incidentsApi";
import { Card } from "@/components/ui/Card";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { incidentStatusOrder, incidentStatusTone } from "./incidentPresentation";
import { incidentRoute, IncidentPriority } from "./IncidentTable";

interface IncidentBoardProps {
  incidents: IncidentSummary[];
  isLoading: boolean;
}

/** Kanban-style board: one column per incident status. Closed incidents are shown with resolved ones. */
export function IncidentBoard({ incidents, isLoading }: IncidentBoardProps) {
  const { t } = useTranslation("incidents");
  const boardStatuses = incidentStatusOrder.filter((status) => status !== "closed");
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label={t("boardLabel")}>
      {boardStatuses.map((status) => {
        const columnIncidents = incidents.filter((incident) => incident.incidentStatus === status || (status === "resolved" && incident.incidentStatus === "closed"));
        return (
          <section key={status} className="flex min-w-0 flex-col gap-3 rounded-lg bg-surface-sunken p-3" aria-label={t(`status.${status}`)}>
            <header className="flex items-center justify-between px-1">
              <StatusChip tone={incidentStatusTone[status]} size="sm">{t(`status.${status}`)}</StatusChip>
              <span className="text-caption text-muted">{columnIncidents.length}</span>
            </header>
            {isLoading && incidents.length === 0 ? <Skeleton className="h-24 w-full" /> : null}
            {columnIncidents.map((incident) => {
              const route = incidentRoute(incident);
              const cardContent = (
                <Card dense interactive className="gap-2 p-[var(--card-padding)]">
                  <div className="flex items-start justify-between gap-2">
                    <IncidentPriority incident={incident} />
                    <span className="font-mono text-caption text-muted">{incident.externalIncidentNumber}</span>
                  </div>
                  <p className="line-clamp-2 text-body-sm font-medium text-default">{incident.incidentTitle}</p>
                  <p className="truncate text-caption text-muted">{incident.application.applicationName}</p>
                  <div className="flex items-center justify-between gap-2">
                    <RelativeTime value={incident.detectedByKeiganAt} className="text-caption text-muted" />
                    {incident.keiganConfidence !== null ? <ConfidenceMeter percentage={Math.round(incident.keiganConfidence * 100)} size="sm" showLabel={false} className="w-20" /> : null}
                  </div>
                </Card>
              );
              return route ? (
                <Link key={incident.incidentId} to={route} className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-focus-ring-color)]">
                  {cardContent}
                </Link>
              ) : (
                <div key={incident.incidentId}>{cardContent}</div>
              );
            })}
            {!isLoading && columnIncidents.length === 0 ? <p className="px-1 py-6 text-center text-caption text-subtle">{t("board.emptyColumn")}</p> : null}
          </section>
        );
      })}
    </div>
  );
}
