import { BellRing } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusChip } from "@/components/ui/StatusChip";
import { useOutcomeLabel } from "@/features/alerts/components/AlertBadges";
import { formatDateTime } from "@/utils/formatters";

/** The alert group behind the investigation: member alerts and the noise-reduction decision trail. */
export function AlertsSection({ detail }: { detail: InvestigationDetail }) {
  const { t } = useTranslation("investigations");
  const { t: translateAlerts } = useTranslation("alerts");
  const outcomeLabel = useOutcomeLabel();
  const group = detail.alertGroup;
  if (!group) return <EmptyState icon={BellRing} title={t("alerts.emptyTitle")} description={t("alerts.emptyDescription")} isBordered />;
  const alertNameById = new Map(group.alerts.map((alert) => [alert.alertId, alert.ruleName]));
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader icon={BellRing} iconTone="alert" title={group.groupTitle} description={group.groupSummary ?? undefined} actions={<StatusChip tone={group.groupStatus === "open" ? "alert" : "neutral"} size="sm">{translateAlerts(`groupStatus.${group.groupStatus}`)}</StatusChip>} />
        <CardBody className="flex flex-wrap gap-x-8 gap-y-2 text-body-sm text-muted">
          <span>{t("alerts.memberCount", { count: group.memberAlertCount })}</span>
          <span>{t("alerts.startedAt", { time: formatDateTime(group.startedAt) })}</span>
          <span>{t("alerts.priorityScore", { score: Math.round(group.priorityScore) })}</span>
          {group.groupingReason ? <span>{group.groupingReason}</span> : null}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("alerts.membersTitle")} />
        <CardBody>
          <ul className="divide-y divide-[var(--color-border)]">
            {group.alerts.map((alert) => (
              <li key={alert.alertId} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <div className="flex min-w-0 flex-col">
                  <span className="text-body-sm font-medium text-default">{alert.ruleName}</span>
                  <span className="text-caption text-muted">{alert.alertSummary}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">{t("alerts.severity", { level: alert.severityLevel })}</Badge>
                  <span className="text-caption text-muted">{formatDateTime(alert.firstSeenAt)}</span>
                </div>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
      {group.decisions.length > 0 ? (
        <Card>
          <CardHeader title={t("alerts.decisionsTitle")} description={t("alerts.decisionsDescription")} />
          <CardBody>
            <ol className="flex flex-col gap-2">
              {group.decisions.map((decision, decisionIndex) => (
                <li key={decisionIndex} className="flex flex-wrap items-baseline gap-2 text-body-sm">
                  <Badge tone="info">{translateAlerts(`stage.${decision.pipelineStage}`)}</Badge>
                  <span className="font-medium text-default">{outcomeLabel(decision.decisionOutcome)}</span>
                  <span className="text-muted">{alertNameById.get(decision.alertId) ?? ""}: {decision.decisionReason}</span>
                </li>
              ))}
            </ol>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}
