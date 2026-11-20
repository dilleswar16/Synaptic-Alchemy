import { useMemo, useState } from "react";
import { Siren, ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAlertFunnel, useAlertGroups, useGiveGroupFeedback, useNoisePolicy, type AlertGroupSummary } from "@/api/alertsApi";
import { useAccessControl } from "@/auth/accessControl";
import { useApplicationScope } from "@/auth/applicationScope";
import { FunnelChart } from "@/components/charts";
import { PageHeader } from "@/components/layout/PageHeader";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Tooltip } from "@/components/ui/Tooltip";
import { AlertGroupDrawer } from "../components/AlertGroupDrawer";
import { GroupStatusChip, ScoreBar, SeverityChip, useFunnelStepLabel, useOutcomeLabel } from "../components/AlertBadges";

type Period = "24h" | "7d" | "30d";
const periodHours: Record<Period, number> = { "24h": 24, "7d": 168, "30d": 720 };

/** Alerts: noise funnel for the selected period, alert groups with reasons, and the Observe-mode banner with its measured effect. */
export default function AlertsPage() {
  const { t } = useTranslation("alerts");
  const { applicationIds, availableApplications } = useApplicationScope();
  const accessControl = useAccessControl();
  const [period, setPeriod] = useState<Period>("7d");
  const [page, setPage] = useState(1);
  const [openGroupId, setOpenGroupId] = useState<string | null>(null);
  const periodStart = useMemo(() => {
    const start = new Date(Date.now() - periodHours[period] * 3_600_000);
    start.setMinutes(0, 0, 0);
    return start.toISOString();
  }, [period]);
  const singleApplicationId = applicationIds.length === 1 ? applicationIds[0]! : applicationIds.length === 0 && availableApplications.length === 1 ? availableApplications[0]!.applicationId : null;

  const funnelQuery = useAlertFunnel(applicationIds, periodStart);
  const groupsQuery = useAlertGroups({ applicationIds, periodStart, page, pageSize: 25 });
  const policyQuery = useNoisePolicy(singleApplicationId ?? "");
  const giveFeedback = useGiveGroupFeedback();
  const stepLabel = useFunnelStepLabel();
  const outcomeLabel = useOutcomeLabel();
  const canEditGroup = (group: AlertGroupSummary) => accessControl.canEdit(group.applicationId);

  const columns: DataTableColumn<AlertGroupSummary>[] = [
    {
      key: "group",
      header: t("groups.columns.group"),
      cell: (group) => (
        <div className="flex min-w-56 flex-col gap-0.5">
          <span className="font-semibold">{group.groupTitle}</span>
          <span className="text-caption text-muted">{group.applicationName} · {t("groups.occurrences", { count: group.totalOccurrenceCount })}</span>
        </div>
      ),
      sortValue: (group) => group.groupTitle,
    },
    { key: "services", header: t("groups.columns.services"), cell: (group) => <span className="text-body-sm">{group.services.map((service) => service.serviceName).join(", ") || t("groups.applicationLevel")}</span> },
    { key: "severity", header: t("groups.columns.severity"), cell: (group) => <SeverityChip level={group.highestSeverityLevel} />, sortValue: (group) => group.highestSeverityLevel },
    { key: "alerts", header: t("groups.columns.alerts"), align: "end", cell: (group) => group.memberAlertCount, sortValue: (group) => group.memberAlertCount },
    { key: "status", header: t("groups.columns.status"), cell: (group) => <GroupStatusChip status={group.groupStatus} />, sortValue: (group) => group.groupStatus },
    { key: "score", header: t("groups.columns.score"), cell: (group) => <ScoreBar score={group.priorityScore} />, sortValue: (group) => group.priorityScore },
    {
      key: "reason",
      header: t("groups.columns.reason"),
      cell: (group) => (
        <div className="flex max-w-80 flex-col gap-1">
          {group.decisionOutcome ? <StatusChip tone="neutral" variant="outline" size="sm" icon={false}>{outcomeLabel(group.decisionOutcome)}</StatusChip> : null}
          <span className="line-clamp-2 text-caption text-muted">{group.decisionReason}</span>
        </div>
      ),
    },
    { key: "activity", header: t("groups.columns.lastActivity"), cell: (group) => <RelativeTime value={group.lastActivityAt} />, sortValue: (group) => group.lastActivityAt },
    {
      key: "feedback",
      header: t("groups.columns.feedback"),
      cell: (group) => (
        <div className="flex gap-1" onClick={(event) => event.stopPropagation()}>
          <IconButton icon={ThumbsUp} label={t("verdict.useful")} size="sm" variant={group.userFeedbackVerdict === "useful" ? "primary" : "ghost"} isPressed={group.userFeedbackVerdict === "useful"}
            onClick={() => giveFeedback.mutate({ alertGroupId: group.alertGroupId, verdict: "useful" })} />
          <IconButton icon={ThumbsDown} label={t("verdict.noise")} size="sm" variant={group.userFeedbackVerdict === "noise" ? "primary" : "ghost"} isPressed={group.userFeedbackVerdict === "noise"}
            onClick={() => giveFeedback.mutate({ alertGroupId: group.alertGroupId, verdict: "noise" })} />
        </div>
      ),
    },
  ];

  const funnel = funnelQuery.data;
  const policy = policyQuery.data;
  const openGroup = groupsQuery.data?.items.find((group) => group.alertGroupId === openGroupId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pageTitle")}
        description={t("pageDescription")}
        actions={<SegmentedControl aria-label={t("filters.period")} value={period} onValueChange={(value) => { setPeriod(value); setPage(1); }}
          options={[{ value: "24h", label: t("filters.last24h") }, { value: "7d", label: t("filters.last7d") }, { value: "30d", label: t("filters.last30d") }]} />}
      />
      {policy?.policyMode === "observe" ? (
        <Banner tone="info" title={t("observe.title", { count: policy.observeModeDaysRemaining ?? 0 })}>
          <p>{t("observe.body")}</p>
          {policy.observedEffect ? <p className="mt-1 font-semibold">{t("observe.effect", { sentence: policy.observedEffect.summarySentence })}</p> : null}
        </Banner>
      ) : null}
      <Card>
        <CardHeader title={t("funnel.title")} description={funnel?.summarySentence || t("funnel.description")} />
        <CardBody>
          {funnelQuery.isLoading ? <Skeleton className="h-40 w-full" /> : null}
          {funnelQuery.isError ? <ErrorState size="sm" error={funnelQuery.error} onRetry={() => funnelQuery.refetch()} /> : null}
          {funnel && funnel.steps[0]?.count === 0 ? <EmptyState icon={Siren} size="sm" title={t("funnel.emptyTitle")} description={t("funnel.emptyDescription")} /> : null}
          {funnel && (funnel.steps[0]?.count ?? 0) > 0 ? (
            <div className="flex flex-col gap-3">
              <FunnelChart ariaLabel={t("funnel.title")} stages={funnel.steps.map((step) => ({ key: step.stepKey, label: stepLabel(step), count: step.count }))} />
              <div className="flex flex-wrap gap-2">
                {Object.entries(funnel.reasonCounts).filter(([, count]) => count > 0).map(([reason, count]) => (
                  <Tooltip key={reason} content={t(`funnel.reasonHelp.${reason}`)}><span><StatusChip tone="neutral" variant="outline" size="sm" icon={false}>{t(`funnel.reasons.${reason}`, { count })}</StatusChip></span></Tooltip>
                ))}
              </div>
            </div>
          ) : null}
        </CardBody>
      </Card>
      <section className="flex flex-col gap-3">
        <h2 className="text-h3 font-semibold">{t("groups.title")}</h2>
        {groupsQuery.isError ? <ErrorState error={groupsQuery.error} onRetry={() => groupsQuery.refetch()} /> : (
          <DataTable
            columns={columns}
            rows={groupsQuery.data?.items ?? []}
            getRowId={(group) => group.alertGroupId}
            caption={t("groups.title")}
            isLoading={groupsQuery.isLoading}
            onRowClick={(group) => setOpenGroupId(group.alertGroupId)}
            isManualSorting={false}
            serverPagination={{ page, pageSize: 25, totalCount: groupsQuery.data?.totalCount ?? 0, onPageChange: setPage }}
            emptyState={<EmptyState icon={Siren} title={t("groups.emptyTitle")} description={t("groups.emptyDescription")} />}
          />
        )}
      </section>
      <AlertGroupDrawer alertGroupId={openGroupId} canEdit={openGroup ? canEditGroup(openGroup) : false} onClose={() => setOpenGroupId(null)} />
    </div>
  );
}
