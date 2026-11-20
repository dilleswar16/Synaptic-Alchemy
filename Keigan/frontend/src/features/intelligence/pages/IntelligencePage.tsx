import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Check, FileText, Lightbulb, Mail, Search, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useGenerateReport,
  useHealthScoreTrend,
  useIntelligenceReport,
  useIntelligenceReports,
  useInvestigateSignal,
  useSignals,
  useUpdateSignalStatus,
  type DetectorName,
  type IntelligenceReportSummary,
  type PredictiveSignal,
  type SignalSeverity,
} from "@/api/intelligenceApi";
import { isApiError } from "@/api/httpClient";
import { useAccessControl } from "@/auth/accessControl";
import { useApplicationScope } from "@/auth/applicationScope";
import { Sparkline } from "@/components/charts/Sparkline";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Checkbox";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { StatusChip } from "@/components/ui/StatusChip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime } from "@/utils/formatters";

const severityTone = { critical: "danger", warning: "warning", info: "info" } as const;
const detectorNames: DetectorName[] = ["seasonal_anomaly", "error_budget_exhaustion", "saturation_trend", "recurring_incident", "change_risk", "new_error_pattern"];
const allValue = "all";

/** Predictive intelligence: health-score trend, signals feed with actions, and the Keigan Intelligence Report archive. */
export default function IntelligencePage() {
  const { t } = useTranslation("intelligence");
  const { availableApplications, applicationIds } = useApplicationScope();
  const [chosenApplicationId, setChosenApplicationId] = useState<string | null>(null);
  const applicationId = chosenApplicationId ?? applicationIds[0] ?? availableApplications[0]?.applicationId ?? null;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader title={t("pageTitle")} description={t("pageDescription")} />
      <HealthSection
        applicationId={applicationId}
        onApplicationChange={setChosenApplicationId}
        options={availableApplications.map((application) => ({ value: application.applicationId, label: application.applicationName }))}
      />
      <Tabs defaultValue="signals">
        <TabsList>
          <TabsTrigger value="signals">{t("tabs.signals")}</TabsTrigger>
          <TabsTrigger value="reports">{t("tabs.reports")}</TabsTrigger>
        </TabsList>
        <TabsContent value="signals" className="pt-6"><SignalsSection applicationIds={applicationIds} /></TabsContent>
        <TabsContent value="reports" className="pt-6"><ReportsSection applicationId={applicationId} /></TabsContent>
      </Tabs>
    </div>
  );
}

function HealthSection({ applicationId, onApplicationChange, options }: { applicationId: string | null; onApplicationChange: (applicationId: string) => void; options: Array<{ value: string; label: string }> }) {
  const { t } = useTranslation("intelligence");
  const trendQuery = useHealthScoreTrend(applicationId, 30);
  const points = trendQuery.data?.points ?? [];
  const data = useMemo(() => points.map((point) => ({ time: point.day, healthScore: point.healthScore })), [points]);
  const score = trendQuery.data?.currentHealthScore ?? null;
  return (
    <Card>
      <CardHeader
        title={t("health.title")}
        description={t("health.description")}
        icon={Sparkles}
        actions={options.length > 0 ? <Select aria-label={t("health.chooseApplication")} size="sm" value={applicationId ?? undefined} onValueChange={onApplicationChange} options={options} /> : undefined}
      />
      <CardBody>
        {!applicationId ? <EmptyState size="sm" title={t("health.empty")} /> : null}
        {trendQuery.isLoading ? <Skeleton className="h-48 w-full" /> : null}
        {trendQuery.isError ? <ErrorState error={trendQuery.error} onRetry={() => trendQuery.refetch()} /> : null}
        {trendQuery.isSuccess ? (
          <div className="grid gap-6 lg:grid-cols-[200px_minmax(0,1fr)]">
            <StatTile icon={Sparkles} iconTone={score !== null && score < 60 ? "danger" : score !== null && score < 80 ? "warning" : "success"} label={t("health.current")} value={score ?? "-"} secondaryText="/ 100" />
            <TimeSeriesChart
              data={data}
              series={[{ key: "healthScore", label: t("health.series"), showArea: true }]}
              xKey="time"
              xFormatter={(value) => String(value).slice(5)}
              yDomain={[0, 100]}
              height={200}
              ariaLabel={t("health.ariaLabel")}
            />
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function SignalsSection({ applicationIds }: { applicationIds: string[] }) {
  const { t } = useTranslation("intelligence");
  const [severity, setSeverity] = useState<string>(allValue);
  const [detector, setDetector] = useState<string>(allValue);
  const [showClosed, setShowClosed] = useState(false);
  const signalsQuery = useSignals({
    applicationIds,
    severities: severity === allValue ? undefined : [severity as SignalSeverity],
    detectors: detector === allValue ? undefined : [detector as DetectorName],
    statuses: showClosed ? ["open", "acknowledged", "dismissed", "converted_to_incident", "expired"] : undefined,
  });
  const signals = signalsQuery.data ?? [];
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-48">
          <Select
            label={t("filters.severity")}
            value={severity}
            onValueChange={setSeverity}
            options={[{ value: allValue, label: t("filters.allSeverities") }, ...(["critical", "warning", "info"] as const).map((value) => ({ value, label: t(`severity.${value}`) }))]}
          />
        </div>
        <div className="min-w-56">
          <Select
            label={t("filters.detector")}
            value={detector}
            onValueChange={setDetector}
            options={[{ value: allValue, label: t("filters.allDetectors") }, ...detectorNames.map((value) => ({ value, label: t(`detectors.${value}`) }))]}
          />
        </div>
        <Checkbox label={t("signals.showAll")} checked={showClosed} onCheckedChange={(checked) => setShowClosed(checked === true)} />
      </div>
      {signalsQuery.isLoading ? <div className="grid gap-4 lg:grid-cols-2">{[0, 1].map((index) => <Skeleton key={index} className="h-56 w-full" />)}</div> : null}
      {signalsQuery.isError ? <ErrorState error={signalsQuery.error} onRetry={() => signalsQuery.refetch()} /> : null}
      {signalsQuery.isSuccess && signals.length === 0 ? <EmptyState isBordered icon={Lightbulb} title={t("signals.emptyTitle")} description={t("signals.emptyDescription")} /> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {signals.map((signal) => <SignalCard key={signal.predictiveSignalId} signal={signal} />)}
      </div>
    </section>
  );
}

function SignalCard({ signal }: { signal: PredictiveSignal }) {
  const { t } = useTranslation("intelligence");
  const { showToast } = useToast();
  const navigate = useNavigate();
  const { canEdit } = useAccessControl();
  const updateStatus = useUpdateSignalStatus();
  const investigate = useInvestigateSignal();
  const isEditable = canEdit(signal.applicationId);
  const isOpen = signal.signalStatus === "open" || signal.signalStatus === "acknowledged";
  const values = signal.evidenceSeries.map((point) => point.v);
  const fail = (title: string, error: unknown) => showToast({ tone: "danger", title, description: isApiError(error) ? error.detail ?? error.title : undefined });
  return (
    <Card dense accent={signal.signalSeverity === "critical"}>
      <CardHeader
        title={signal.signalTitle}
        description={[signal.applicationName, signal.serviceName].filter(Boolean).join(" · ")}
        icon={Lightbulb}
        iconTone={severityTone[signal.signalSeverity]}
        titleAs="h3"
      />
      <CardBody>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip size="sm" tone={severityTone[signal.signalSeverity]}>{t(`severity.${signal.signalSeverity}`)}</StatusChip>
            <StatusChip size="sm" tone="neutral" icon={false}>{t(`detectors.${signal.detectorName}`)}</StatusChip>
            {signal.signalStatus !== "open" ? <StatusChip size="sm" tone="info" icon={false}>{signal.signalStatus.replace(/_/g, " ")}</StatusChip> : null}
            <RelativeTime value={signal.detectedAt} className="text-caption text-muted" />
          </div>
          {signal.explanationMarkdown ? <MarkdownView content={signal.explanationMarkdown} /> : null}
          <div className="flex flex-wrap items-center gap-6 text-body-sm">
            {signal.observedValue !== null ? <span><span className="text-muted">{t("signals.observed")}: </span><strong>{signal.observedValue}</strong></span> : null}
            {signal.expectedValue !== null ? <span><span className="text-muted">{t("signals.expected")}: </span><strong>{signal.expectedValue}</strong></span> : null}
            {signal.forecastBreachAt ? <span className="text-muted">{t("signals.forecast", { when: formatDateTime(signal.forecastBreachAt) })}</span> : null}
          </div>
          <div className="flex items-center gap-4">
            {values.length > 1 ? <Sparkline values={values} width={220} height={44} showArea showEndDot /> : null}
            <ConfidenceMeter percentage={Math.round(signal.confidenceScore * 100)} size="sm" />
          </div>
          {isEditable && isOpen ? (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="primary"
                leadingIcon={Search}
                isLoading={investigate.isPending}
                onClick={() =>
                  investigate.mutate(signal.predictiveSignalId, {
                    onSuccess: (result) => {
                      showToast({ tone: "success", title: t("signals.investigateStarted") });
                      void navigate(`/investigations/${result.investigationId}`);
                    },
                    onError: (error) => fail(t("signals.investigateFailed"), error),
                  })
                }
              >
                {t("signals.investigate")}
              </Button>
              {signal.signalStatus === "open" ? (
                <Button size="sm" variant="secondary" leadingIcon={Check} onClick={() => updateStatus.mutate({ signalId: signal.predictiveSignalId, signalStatus: "acknowledged" }, { onError: (error) => fail(t("signals.statusFailed"), error) })}>
                  {t("signals.acknowledge")}
                </Button>
              ) : null}
              <Button size="sm" variant="ghost" leadingIcon={X} onClick={() => updateStatus.mutate({ signalId: signal.predictiveSignalId, signalStatus: "dismissed" }, { onError: (error) => fail(t("signals.statusFailed"), error) })}>
                {t("signals.dismiss")}
              </Button>
            </div>
          ) : null}
          {isEditable && signal.signalStatus === "dismissed" ? (
            <div>
              <Button size="sm" variant="ghost" onClick={() => updateStatus.mutate({ signalId: signal.predictiveSignalId, signalStatus: "open" })}>{t("signals.reopen")}</Button>
            </div>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

function ReportsSection({ applicationId }: { applicationId: string | null }) {
  const { t } = useTranslation("intelligence");
  const { showToast } = useToast();
  const { canEdit } = useAccessControl();
  const reportsQuery = useIntelligenceReports(applicationId);
  const generateReport = useGenerateReport(applicationId ?? "");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const reports = reportsQuery.data ?? [];
  useEffect(() => {
    if (!selectedReportId && reports.length > 0) setSelectedReportId(reports[0]?.intelligenceReportId ?? null);
  }, [reports, selectedReportId]);
  const reportQuery = useIntelligenceReport(selectedReportId);
  const generate = (sendToStakeholders: boolean) =>
    generateReport.mutate(
      { reportType: "weekly_digest", sendToStakeholders },
      {
        onSuccess: () => showToast({ tone: "success", title: t("reports.queued"), description: t("reports.queuedDescription") }),
        onError: (error) => showToast({ tone: "danger", title: t("reports.generateFailed"), description: isApiError(error) ? error.detail ?? error.title : undefined }),
      },
    );

  const columns: DataTableColumn<IntelligenceReportSummary>[] = [
    {
      key: "title",
      header: t("reports.reader"),
      cell: (row) => (
        <div className="flex flex-col">
          <span className="font-semibold">{row.applicationName}</span>
          <span className="text-caption text-muted">{formatDateTime(row.createdAt)}</span>
        </div>
      ),
    },
    { key: "type", header: "", cell: (row) => <StatusChip size="sm" tone={row.reportType === "proactive_alert" ? "alert" : "brand"} icon={false}>{t(`reports.${row.reportType}`)}</StatusChip> },
    { key: "health", header: "", align: "end", cell: (row) => (row.overallHealthScore !== null ? t("reports.healthScore", { score: row.overallHealthScore }) : "") },
  ];

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-h3 font-semibold">{t("reports.title")}</h2>
          <p className="text-body-sm text-muted">{t("reports.description")}</p>
        </div>
        {applicationId && canEdit(applicationId) ? (
          <div className="flex gap-2">
            <Button variant="secondary" leadingIcon={FileText} isLoading={generateReport.isPending} onClick={() => generate(false)}>{t("reports.generate")}</Button>
            <Button leadingIcon={Mail} isLoading={generateReport.isPending} onClick={() => generate(true)}>{t("reports.generateAndSend")}</Button>
          </div>
        ) : null}
      </div>
      {reportsQuery.isError ? <ErrorState error={reportsQuery.error} onRetry={() => reportsQuery.refetch()} /> : null}
      {reportsQuery.isSuccess && reports.length === 0 ? <EmptyState isBordered icon={FileText} title={t("reports.emptyTitle")} description={t("reports.emptyDescription")} /> : null}
      {reportsQuery.isLoading || reports.length > 0 ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <DataTable
            columns={columns}
            rows={reports}
            getRowId={(row) => row.intelligenceReportId}
            caption={t("reports.title")}
            isLoading={reportsQuery.isLoading}
            onRowClick={(row) => setSelectedReportId(row.intelligenceReportId)}
            rowClassName={(row) => (row.intelligenceReportId === selectedReportId ? "bg-action-soft" : undefined)}
          />
          <Card>
            <CardBody>
              {reportQuery.isLoading ? <Skeleton className="h-64 w-full" /> : null}
              {reportQuery.isError ? <ErrorState error={reportQuery.error} onRetry={() => reportQuery.refetch()} /> : null}
              {!selectedReportId ? <EmptyState size="sm" title={t("reports.readerEmpty")} /> : null}
              {reportQuery.data ? (
                <div className="flex flex-col gap-3">
                  <p className="text-caption text-muted">
                    {t("reports.period")}: {formatDateTime(reportQuery.data.reportPeriodStart)} - {formatDateTime(reportQuery.data.reportPeriodEnd)} ·{" "}
                    {reportQuery.data.sentAt ? t("reports.sentTo", { count: reportQuery.data.recipientCount }) : t("reports.notSent")}
                  </p>
                  <MarkdownView content={reportQuery.data.reportMarkdown ?? ""} />
                </div>
              ) : null}
            </CardBody>
          </Card>
        </div>
      ) : null}
    </section>
  );
}
