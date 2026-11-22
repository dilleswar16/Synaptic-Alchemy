import { useState } from "react";
import { Link } from "react-router";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAlertGroup, useCreateIncidentFromGroup, useGiveGroupFeedback } from "@/api/alertsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { SkeletonText } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { Timeline, type TimelineEvent } from "@/components/ui/Timeline";
import { useToast } from "@/components/ui/Toast";
import type { AlertMember } from "@/api/alertsApi";
import { GroupStatusChip, ScoreBar, SeverityChip, useOutcomeLabel } from "./AlertBadges";
import { GroupingReasonText } from "./GroupingReasonText";

/** Group detail: member alerts, the decision log as a timeline (every stage with its reason) and feedback. */
export function AlertGroupDrawer({ alertGroupId, canEdit, onClose }: { alertGroupId: string | null; canEdit: boolean; onClose: () => void }) {
  const { t } = useTranslation("alerts");
  const { showToast } = useToast();
  const groupQuery = useAlertGroup(alertGroupId);
  const giveFeedback = useGiveGroupFeedback();
  const createIncident = useCreateIncidentFromGroup();
  const outcomeLabel = useOutcomeLabel();
  const [noiseReason, setNoiseReason] = useState("");
  const group = groupQuery.data;

  const memberColumns: DataTableColumn<AlertMember>[] = [
    { key: "rule", header: t("drawer.rule"), cell: (member) => <span className="font-semibold">{member.ruleName}</span> },
    { key: "service", header: t("drawer.service"), cell: (member) => member.serviceName ?? t("drawer.applicationLevel") },
    { key: "severity", header: t("drawer.severity"), cell: (member) => <SeverityChip level={member.severityLevel} /> },
    {
      key: "state",
      header: t("drawer.state"),
      cell: (member) => (
        <span className="flex flex-wrap items-center gap-1.5">
          <StatusChip tone={member.alertStatus === "firing" ? "alert" : "success"} size="sm" dot>{t(`alertStatus.${member.alertStatus}`)}</StatusChip>
          {member.isFlapping ? <StatusChip tone="warning" size="sm" icon={false}>{t("drawer.flapping")}</StatusChip> : null}
        </span>
      ),
    },
    { key: "count", header: t("drawer.occurrences"), align: "end", cell: (member) => member.occurrenceCount },
    { key: "seen", header: t("drawer.lastSeen"), cell: (member) => <RelativeTime value={member.lastSeenAt} /> },
  ];

  const timelineEvents: TimelineEvent[] = (group?.decisions ?? []).map((decision) => ({
    key: decision.alertDecisionId,
    timestamp: decision.decidedAt,
    title: (
      <span className="flex flex-wrap items-center gap-2">
        {t(`stage.${decision.pipelineStage}`)}
        <StatusChip tone="neutral" size="sm" variant="outline" icon={false}>{outcomeLabel(decision.decisionOutcome)}</StatusChip>
      </span>
    ),
    description: decision.decisionReason,
    tone: decision.decisionOutcome.startsWith("suppressed") ? "warning" : decision.decisionOutcome.startsWith("investigation") ? "ai" : "neutral",
    meta: decision.wouldHaveOutcomeInActiveMode ? <span className="text-caption text-muted">{t("drawer.wouldHave", { outcome: outcomeLabel(decision.wouldHaveOutcomeInActiveMode) })}</span> : decision.ruleName ? <span className="text-caption text-muted">{decision.ruleName}</span> : undefined,
  }));

  const sendFeedback = (verdict: "useful" | "noise") =>
    alertGroupId && giveFeedback.mutate({ alertGroupId, verdict, reason: verdict === "noise" ? noiseReason || undefined : undefined }, { onSuccess: () => showToast({ tone: "success", title: t("drawer.feedbackSaved") }) });

  return (
    <Drawer
      open={alertGroupId !== null}
      onOpenChange={(isOpen) => (isOpen ? undefined : onClose())}
      size="lg"
      title={group?.groupTitle ?? t("drawer.loading")}
      description={group?.groupSummary ?? undefined}
      headerContent={group ? <div className="flex flex-wrap items-center gap-2"><GroupStatusChip status={group.groupStatus} /><SeverityChip level={group.highestSeverityLevel} /><ScoreBar score={group.priorityScore} /></div> : undefined}
    >
      {groupQuery.isLoading ? <SkeletonText lineCount={8} /> : null}
      {groupQuery.isError ? <ErrorState error={groupQuery.error} onRetry={() => groupQuery.refetch()} /> : null}
      {group ? (
        <div className="flex flex-col gap-6">
          {group.policyMode === "observe" ? <Banner tone="info" title={t("drawer.observeTitle")}>{t("drawer.observeBody")}</Banner> : null}
          <div className="flex flex-wrap items-center gap-3 text-body-sm">
            {group.investigationId ? <Button asChild variant="secondary" size="sm"><Link to={`/investigations/${group.investigationId}`}>{t("drawer.openInvestigation")}</Link></Button> : null}
            {group.incidentId ? <Button asChild variant="secondary" size="sm"><Link to="/incidents">{t("drawer.openIncident")}</Link></Button> : null}
            {!group.incidentId && canEdit ? (
              <Button variant={group.servicenowIncidentSuggested ? "primary" : "secondary"} size="sm" isLoading={createIncident.isPending}
                onClick={() => alertGroupId && createIncident.mutate(alertGroupId, { onSuccess: () => showToast({ tone: "success", title: t("drawer.incidentCreated") }), onError: (error) => showToast({ tone: "danger", title: t("drawer.incidentFailed"), description: error.message }) })}>
                {group.servicenowIncidentSuggested ? t("drawer.createIncidentSuggested") : t("drawer.createIncident")}
              </Button>
            ) : null}
          </div>
          <GroupingReasonText reason={group.groupingReason} className="text-body-sm" />
          <section className="flex flex-col gap-3">
            <SectionHeader level={3} title={t("drawer.members", { count: group.members.length })} />
            <DataTable columns={memberColumns} rows={group.members} getRowId={(member) => member.alertId} caption={t("drawer.members", { count: group.members.length })} density="dense" />
          </section>
          <section className="flex flex-col gap-3">
            <SectionHeader level={3} title={t("drawer.decisionLog")} description={t("drawer.decisionLogHelp")} />
            <Timeline events={timelineEvents} emptyMessage={t("drawer.noDecisions")} />
          </section>
          <section className="flex flex-col gap-3">
            <SectionHeader level={3} title={t("drawer.feedback")} description={group.userFeedbackVerdict ? t("drawer.feedbackCurrent", { verdict: t(`verdict.${group.userFeedbackVerdict}`) }) : t("drawer.feedbackHelp")} />
            <Textarea label={t("drawer.noiseReason")} isOptional value={noiseReason} onChange={(event) => setNoiseReason(event.target.value)} rows={2} />
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" leadingIcon={ThumbsUp} onClick={() => sendFeedback("useful")} isLoading={giveFeedback.isPending}>{t("verdict.useful")}</Button>
              <Button variant="secondary" size="sm" leadingIcon={ThumbsDown} onClick={() => sendFeedback("noise")} isLoading={giveFeedback.isPending}>{t("verdict.noise")}</Button>
            </div>
          </section>
        </div>
      ) : null}
    </Drawer>
  );
}
