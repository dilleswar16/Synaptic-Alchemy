import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router";
import { isInvestigationRunning, useInvestigation, useInvestigationProgress } from "@/api/investigationsApi";
import { useAccessControl } from "@/auth/accessControl";
import { PageHeader } from "@/components/layout/PageHeader";
import { Banner } from "@/components/ui/Banner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { AlertsSection } from "../components/AlertsSection";
import { BlastRadiusSection } from "../components/BlastRadiusSection";
import { CommunicationsSection } from "../components/CommunicationsSection";
import { EvidenceSection } from "../components/EvidenceSection";
import { FeedbackDialog } from "../components/FeedbackDialog";
import { HypothesesSection } from "../components/HypothesesSection";
import { InvestigationChatPanel } from "../components/InvestigationChatPanel";
import { InvestigationHeader } from "../components/InvestigationHeader";
import { InvestigationProgress } from "../components/InvestigationProgress";
import { PostmortemSection } from "../components/PostmortemSection";
import { RcaSection } from "../components/RcaSection";
import { ResolveDialog } from "../components/ResolveDialog";
import { TeamsRoomPanel } from "../components/TeamsRoomPanel";
import { DecisionTraceSection } from "../components/DecisionTraceSection";
import { TimelineSection } from "../components/TimelineSection";

const tabKeys = ["rca", "hypotheses", "evidence", "blast", "timeline", "alerts", "communications", "postmortem", "trace", "teams"] as const;
type TabKey = (typeof tabKeys)[number];

/** Investigation page (spec 7.4): header, live progress, sticky section tabs and the floating investigation chat. */
export default function InvestigationPage() {
  const { t } = useTranslation("investigations");
  const { investigationId } = useParams<{ investigationId: string }>();
  const [searchParameters, setSearchParameters] = useSearchParams();
  const { canEdit } = useAccessControl();
  const investigationQuery = useInvestigation(investigationId);
  const detail = investigationQuery.data;
  const isRunning = isInvestigationRunning(detail?.investigationStatus);
  const progressQuery = useInvestigationProgress(investigationId, isRunning);
  const [selectedEvidenceCode, setSelectedEvidenceCode] = useState<string | null>(null);
  const [selectedRunbookId, setSelectedRunbookId] = useState<string | null>(null);
  const [isResolveOpen, setIsResolveOpen] = useState(false);
  const [isFeedbackOpen, setIsFeedbackOpen] = useState(false);

  const requestedTab = searchParameters.get("tab");
  const activeTab: TabKey = tabKeys.find((key) => key === requestedTab) ?? "rca";
  const setTab = (tab: string) => setSearchParameters((previous) => { const next = new URLSearchParams(previous); next.set("tab", tab); return next; }, { replace: true });

  if (investigationQuery.isLoading) {
    return (
      <>
        <PageHeader title={t("pageTitle")} description={t("pageDescription")} />
        <Skeleton className="mb-6 h-44 w-full" />
        <Skeleton className="h-72 w-full" />
      </>
    );
  }
  if (investigationQuery.isError || !detail) {
    return <ErrorState error={investigationQuery.error} onRetry={() => void investigationQuery.refetch()} isRetrying={investigationQuery.isFetching} />;
  }

  const canEditApplication = canEdit(detail.application.applicationId);
  const showTeams = Boolean(detail.incidentId);
  const selectEvidence = (code: string) => {
    setSelectedEvidenceCode(code);
    setTab("evidence");
  };

  const selectRunbook = (runbookId: string) => {
    setSelectedRunbookId(runbookId);
    setTab("rca");
  };

  return (
    <>
      <PageHeader
        title={t("pageTitle")}
        breadcrumbs={[{ label: t("breadcrumb.incidents"), to: "/incidents" }, { label: detail.incidentNumber ?? t("breadcrumb.manual") }]}
      />
      <InvestigationHeader detail={detail} canEdit={canEditApplication} onOpenTeamsRoom={() => setTab("teams")} onResolve={() => setIsResolveOpen(true)} onFeedback={() => setIsFeedbackOpen(true)} />
      {isRunning ? <InvestigationProgress progress={progressQuery.data} fallbackStage={detail.currentStageName} fallbackPercent={detail.progressPercent} fallbackMessages={detail.stageMessages} /> : null}
      {detail.investigationStatus === "failed" ? <Banner tone="danger" title={t("rca.failedTitle")} className="mb-6">{detail.failureReason ?? t("rca.failedDescription")}</Banner> : null}
      {detail.isEvidenceOnly ? <Banner tone="warning" title={t("rca.evidenceOnlyTitle")} className="mb-6">{t("rca.evidenceOnlyDescription")}</Banner> : null}

      <Tabs value={activeTab} onValueChange={setTab}>
        <div className="sticky top-0 z-20 -mx-1 mb-6 bg-canvas px-1 pt-1">
          <TabsList aria-label={t("tabs.label")}>
            <TabsTrigger value="rca">{t("tabs.rca")}</TabsTrigger>
            <TabsTrigger value="hypotheses" count={detail.hypotheses.length || undefined}>{t("tabs.hypotheses")}</TabsTrigger>
            <TabsTrigger value="evidence" count={detail.evidence.length || undefined}>{t("tabs.evidence")}</TabsTrigger>
            <TabsTrigger value="blast">{t("tabs.blast")}</TabsTrigger>
            <TabsTrigger value="timeline">{t("tabs.timeline")}</TabsTrigger>
            <TabsTrigger value="alerts" count={detail.alertGroup?.memberAlertCount}>{t("tabs.alerts")}</TabsTrigger>
            <TabsTrigger value="communications">{t("tabs.communications")}</TabsTrigger>
            <TabsTrigger value="postmortem">{t("tabs.postmortem")}</TabsTrigger>
            <TabsTrigger value="trace">{t("tabs.trace")}</TabsTrigger>
            {showTeams ? <TabsTrigger value="teams">{t("tabs.teams")}</TabsTrigger> : null}
          </TabsList>
        </div>
        <TabsContent value="rca"><RcaSection detail={detail} onSelectEvidence={selectEvidence} selectedRunbookId={selectedRunbookId} /></TabsContent>
        <TabsContent value="hypotheses"><HypothesesSection detail={detail} onSelectEvidence={selectEvidence} /></TabsContent>
        <TabsContent value="evidence"><EvidenceSection detail={detail} selectedEvidenceCode={selectedEvidenceCode} /></TabsContent>
        <TabsContent value="blast"><BlastRadiusSection detail={detail} /></TabsContent>
        <TabsContent value="timeline"><TimelineSection investigationId={detail.investigationId} isRunning={isRunning} /></TabsContent>
        <TabsContent value="alerts"><AlertsSection detail={detail} /></TabsContent>
        <TabsContent value="communications"><CommunicationsSection detail={detail} canEdit={canEditApplication} /></TabsContent>
        <TabsContent value="postmortem"><PostmortemSection detail={detail} canEdit={canEditApplication} /></TabsContent>
        <TabsContent value="trace"><DecisionTraceSection detail={detail} isRunning={isRunning} canSeeRawOutput={canEditApplication} /></TabsContent>
        {showTeams && detail.incidentId ? <TabsContent value="teams"><TeamsRoomPanel incidentId={detail.incidentId} /></TabsContent> : null}
      </Tabs>

      {detail.incidentId ? <ResolveDialog open={isResolveOpen} onOpenChange={setIsResolveOpen} incidentId={detail.incidentId} onResolved={() => setTab("postmortem")} analysisVerdict={detail.userFeedbackVerdict} /> : null}
      <FeedbackDialog open={isFeedbackOpen} onOpenChange={setIsFeedbackOpen} investigationId={detail.investigationId} currentVerdict={detail.userFeedbackVerdict} />
      <InvestigationChatPanel investigationId={detail.investigationId} onSelectEvidence={selectEvidence} onSelectRunbook={selectRunbook} />
    </>
  );
}
