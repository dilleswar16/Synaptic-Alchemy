import { useState, type ReactNode } from "react";
import { Ban, ChartColumn, Clock, CircleCheck, Coins, Cpu, EyeOff, History, Hourglass, Send, Siren, ThumbsUp, Timer, Zap, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMetricsOverview, type ApplicationMetrics, type MetricStat, type MetricsOverview, type MetricsSummary, type WeeklyPoint } from "@/api/metricsApi";
import { useApplicationScope } from "@/auth/applicationScope";
import { BarChart } from "@/components/charts/BarChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDate, formatNumber, formatPercentage } from "@/utils/formatters";
import { formatCount, formatMilliseconds, formatSeconds, MetricLabel, StatCell, StatDetail } from "../components/MetricParts";

const periodDays = ["7", "30", "90"] as const;
const allApplications = "all";
const secondsPerHour = 3600;
const secondsPerMinute = 60;
const statusTones = { completed: "success", completed_evidence_only: "info", failed: "danger", running: "brand", queued: "neutral", cancelled: "neutral" } as const;
const statusOrder = ["completed", "completed_evidence_only", "running", "queued", "failed", "cancelled"] as const;

/** Reliability metrics: incident and AI numbers with honest definitions. Every figure shows median, p90 and the number of cases it is based on. */
export default function ReliabilityMetricsPage() {
  const { t } = useTranslation("metrics");
  const { availableApplications } = useApplicationScope();
  const [days, setDays] = useState<(typeof periodDays)[number]>("30");
  const [chosenApplication, setChosenApplication] = useState<string>(allApplications);
  const query = useMetricsOverview({ applicationId: chosenApplication === allApplications ? null : chosenApplication, days: Number(days) });
  const overview = query.data;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader title={t("pageTitle")} description={t("pageDescription")}>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            aria-label={t("filters.application")}
            size="sm"
            value={chosenApplication}
            onValueChange={setChosenApplication}
            options={[{ value: allApplications, label: t("filters.allApplications") }, ...availableApplications.map((application) => ({ value: application.applicationId, label: application.applicationName }))]}
          />
          <SegmentedControl
            aria-label={t("filters.period")}
            size="sm"
            value={days}
            onValueChange={setDays}
            options={periodDays.map((value) => ({ value, label: t("filters.days", { count: Number(value) }) }))}
          />
        </div>
        {overview ? (
          <p className="max-w-3xl text-body-sm text-muted">
            {t("filters.range", { from: formatDate(overview.periodStart), to: formatDate(overview.periodEnd) })} {t("percentilesNote")}
          </p>
        ) : null}
      </PageHeader>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? <ErrorState error={query.error} onRetry={() => query.refetch()} /> : null}
      {overview && isEmpty(overview.summary) ? <EmptyState isBordered icon={ChartColumn} title={t("empty.title")} description={t("empty.description")} /> : null}
      {overview && !isEmpty(overview.summary) ? <Content overview={overview} /> : null}
    </div>
  );
}

function isEmpty(summary: MetricsSummary): boolean {
  return summary.incidentsOpenedCount === 0 && summary.incidentsResolvedCount === 0 && summary.investigationCount === 0 && summary.aiUsage.callCount === 0;
}

function LoadingState() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
      {Array.from({ length: 8 }, (_, index) => (
        <Skeleton key={index} className="h-28 w-full" />
      ))}
    </div>
  );
}

function Content({ overview }: { overview: MetricsOverview }) {
  return (
    <>
      <IncidentSection overview={overview} />
      <InvestigationSection summary={overview.summary} />
      <MemorySection summary={overview.summary} />
      <KeiganHelpSection summary={overview.summary} />
      <AiUsageSection summary={overview.summary} />
      <TrendSection overview={overview} />
      <ApplicationSection applications={overview.applications} />
      <DefinitionsSection overview={overview} />
    </>
  );
}

function IncidentSection({ overview }: { overview: MetricsOverview }) {
  const { t } = useTranslation("metrics");
  const { summary } = overview;
  const priorityText = (pick: "openedCount" | "resolvedCount") =>
    summary.byPriority
      .filter((row) => row[pick] > 0)
      .map((row) => `${row.priority === "unassigned" ? t("priority.unassigned") : row.priority} ${formatCount(row[pick])}`)
      .join(" · ") || t("priority.none");
  return (
    <section aria-labelledby="metrics-incidents" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-incidents" title={t("sections.incidents.title")} description={t("sections.incidents.description")} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={Siren} iconTone="danger" label={<MetricLabel metricKey="incidentsOpened" />} value={formatCount(summary.incidentsOpenedCount)} secondaryText={priorityText("openedCount")} />
        <StatTile icon={CircleCheck} iconTone="success" label={<MetricLabel metricKey="incidentsResolved" />} value={formatCount(summary.incidentsResolvedCount)} secondaryText={priorityText("resolvedCount")} />
        <DurationTile icon={Clock} metricKey="timeToDetect" stat={summary.timeToDetect} excludedReasonKey="timeToDetect" />
        <DurationTile icon={Send} metricKey="timeToFirstUpdate" stat={summary.timeToFirstUpdate} excludedReasonKey="outOfOrder" />
        <DurationTile icon={Timer} metricKey="timeToResolve" stat={summary.timeToResolve} excludedReasonKey="outOfOrder" />
        <DurationTile icon={Hourglass} metricKey="timeToConclusion" stat={summary.timeToConclusion} excludedReasonKey="outOfOrder" />
        {overview.notAvailable.map((item) => (
          <StatTile
            key={item.metric}
            icon={Ban}
            iconTone="neutral"
            label={<MetricLabel metricKey={item.metric} />}
            value={t("figure.none")}
            secondaryText={
              <>
                <span className="block font-medium text-default">{t("notAvailable.label")}</span>
                <span className="block">{t(`notAvailable.reasons.${item.reason}`, { defaultValue: t("notAvailable.reasons.unknown") })}</span>
              </>
            }
          />
        ))}
      </div>
    </section>
  );
}

function DurationTile({ icon, metricKey, stat, excludedReasonKey }: { icon: LucideIcon; metricKey: string; stat: MetricStat; excludedReasonKey: string }) {
  const { t } = useTranslation("metrics");
  return (
    <StatTile
      icon={icon}
      iconTone="brand"
      label={<MetricLabel metricKey={metricKey} />}
      value={stat.sampleCount > 0 ? formatSeconds(stat.median) : t("figure.none")}
      secondaryText={<StatDetail stat={stat} format={formatSeconds} excludedReasonKey={excludedReasonKey} />}
    />
  );
}

function InvestigationSection({ summary }: { summary: MetricsSummary }) {
  const { t } = useTranslation("metrics");
  const { ratings } = summary;
  const counts = new Map(summary.investigationsByStatus.map((row) => [row.status, row.count]));
  return (
    <section aria-labelledby="metrics-investigations" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-investigations" title={t("sections.investigations.title")} description={t("sections.investigations.description")} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card dense>
          <CardHeader title={<MetricLabel metricKey="investigationStatuses" />} description={t("investigations.total", { count: summary.investigationCount })} />
          <CardBody>
            <ul className="flex flex-wrap gap-2">
              {statusOrder.map((status) => (
                <li key={status}>
                  <StatusChip tone={statusTones[status]}>{t("investigations.statusCount", { status: t(`statuses.${status}`), count: counts.get(status) ?? 0 })}</StatusChip>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <StatTile
          icon={ThumbsUp}
          iconTone="success"
          label={<MetricLabel metricKey="ratings" />}
          value={ratings.shareCorrect !== null ? formatPercentage(ratings.shareCorrect) : t("figure.none")}
          secondaryText={
            <>
              {ratings.shareCorrect === null ? <span className="block font-medium text-default">{t("ratings.notEnough", { count: ratings.ratedCount, minimum: ratings.minimumSample })}</span> : null}
              <span className="block">
                {t("ratings.detail", { rated: ratings.ratedCount, total: summary.investigationCount, correct: ratings.correctCount, partial: ratings.partiallyCorrectCount, incorrect: ratings.incorrectCount })}
              </span>
            </>
          }
        />
      </div>
    </section>
  );
}

function MemorySection({ summary }: { summary: MetricsSummary }) {
  const { t } = useTranslation("metrics");
  const { memory } = summary;
  if (memory.completedInvestigationCount === 0 && memory.relevanceAnswerCount === 0 && memory.hiddenEntryCount === 0) return null;
  return (
    <section aria-labelledby="metrics-memory" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-memory" title={t("sections.memory.title")} description={t("sections.memory.description")} />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          icon={History}
          iconTone="info"
          label={t("memory.givenLabel")}
          value={t("memory.givenValue", { given: memory.investigationsGivenAHintCount, total: memory.completedInvestigationCount })}
          secondaryText={t("memory.givenDetail")}
        />
        <StatTile
          icon={ThumbsUp}
          iconTone="success"
          label={t("memory.relevantLabel")}
          value={memory.shareRelevant !== null ? formatPercentage(memory.shareRelevant) : t("figure.none")}
          secondaryText={
            memory.shareRelevant === null
              ? t("memory.notEnough", { count: memory.relevanceAnswerCount, minimum: memory.minimumSample })
              : t("memory.relevantDetail", { relevant: memory.relevantCount, answered: memory.relevanceAnswerCount })
          }
        />
        <StatTile icon={EyeOff} iconTone="warning" label={t("memory.hiddenLabel")} value={formatCount(memory.hiddenEntryCount)} secondaryText={t("memory.hiddenDetail")} />
      </div>
    </section>
  );
}

function KeiganHelpSection({ summary }: { summary: MetricsSummary }) {
  const { t } = useTranslation("metrics");
  const { keiganHelp } = summary;
  if (keiganHelp.answeredCount === 0) return null;
  const found = keiganHelp.answers.find((row) => row.answer === "found_cause")?.count ?? 0;
  return (
    <section aria-labelledby="metrics-keigan-help" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-keigan-help" title={t("sections.keiganHelp.title")} description={t("sections.keiganHelp.description")} />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          icon={ThumbsUp}
          iconTone="success"
          label={t("keiganHelp.foundLabel")}
          value={keiganHelp.shareFoundCause !== null ? formatPercentage(keiganHelp.shareFoundCause) : t("figure.none")}
          secondaryText={
            keiganHelp.shareFoundCause === null
              ? t("keiganHelp.notEnough", { count: keiganHelp.answeredCount, minimum: keiganHelp.minimumSample })
              : t("keiganHelp.foundDetail", { found, answered: keiganHelp.answeredCount, resolved: keiganHelp.resolvedCount })
          }
        />
        <StatTile
          icon={Timer}
          iconTone="brand"
          label={t("keiganHelp.withLabel")}
          value={keiganHelp.timeToResolveWithHelp.sampleCount > 0 ? formatSeconds(keiganHelp.timeToResolveWithHelp.median) : t("figure.none")}
          secondaryText={t("keiganHelp.withDetail", { count: keiganHelp.timeToResolveWithHelp.sampleCount })}
        />
        <StatTile
          icon={Timer}
          iconTone="neutral"
          label={t("keiganHelp.withoutLabel")}
          value={keiganHelp.timeToResolveWithoutHelp.sampleCount > 0 ? formatSeconds(keiganHelp.timeToResolveWithoutHelp.median) : t("figure.none")}
          secondaryText={t("keiganHelp.withoutDetail", { count: keiganHelp.timeToResolveWithoutHelp.sampleCount })}
        />
      </div>
      <p className="text-body-sm text-muted">{keiganHelp.answers.map((row) => `${t(`keiganHelp.answer.${row.answer}`)} ${formatCount(row.count)}`).join(" · ")}</p>
    </section>
  );
}

function AiUsageSection({ summary }: { summary: MetricsSummary }) {
  const { t } = useTranslation("metrics");
  const { aiUsage: usage } = summary;
  const money = (value: number | null) => (value === null ? "" : formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 4 }));
  return (
    <section aria-labelledby="metrics-ai" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-ai" title={t("sections.ai.title")} description={t("sections.ai.description")} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <TokenTile label={t("ai.inputTokens")} stat={usage.inputTokens} />
        <TokenTile label={t("ai.outputTokens")} stat={usage.outputTokens} />
        <StatTile
          icon={Zap}
          iconTone="ai"
          label={<MetricLabel metricKey="aiLatency" />}
          value={usage.latencyMilliseconds.sampleCount > 0 ? formatMilliseconds(usage.latencyMilliseconds.median) : t("figure.none")}
          secondaryText={<StatDetail stat={usage.latencyMilliseconds} format={formatMilliseconds} />}
        />
        <StatTile
          icon={Cpu}
          iconTone="ai"
          label={<MetricLabel metricKey="aiCalls" />}
          value={formatCount(usage.callCount)}
          secondaryText={t("ai.callsDetail", { failed: usage.failedCallCount, count: usage.investigationCount })}
          secondaryTone={usage.failedCallCount > 0 ? "negative" : "default"}
        />
        {usage.cost.isConfigured ? (
          <StatTile
            icon={Coins}
            iconTone="ai"
            label={<MetricLabel metricKey="aiCost" label={t("ai.costPerInvestigation")} />}
            value={usage.cost.perInvestigation.sampleCount > 0 ? money(usage.cost.perInvestigation.median) : t("figure.none")}
            secondaryText={
              <>
                {usage.cost.perInvestigation.sampleCount === 0 && usage.cost.unpricedInvestigationCount > 0 ? (
                  <span className="block">{t("ai.noPricedInvestigations")}</span>
                ) : (
                  <StatDetail stat={usage.cost.perInvestigation} format={money} />
                )}
                {usage.cost.totalEstimatedCost !== null && usage.cost.unpricedModels.length === 0 ? <span className="block">{t("ai.costTotal", { total: money(usage.cost.totalEstimatedCost) })}</span> : null}
              </>
            }
          />
        ) : null}
      </div>
      {!usage.cost.isConfigured ? (
        <Banner tone="neutral" title={t("ai.noPricesTitle")}>
          {t("ai.noPricesText")}
        </Banner>
      ) : null}
      {usage.cost.isConfigured && usage.cost.unpricedModels.length > 0 ? (
        <Banner tone="warning" title={t("ai.unpricedTitle")}>
          {t("ai.unpricedText", { models: usage.cost.unpricedModels.join(", "), count: usage.cost.unpricedInvestigationCount })}
        </Banner>
      ) : null}
    </section>
  );
}

function TokenTile({ label, stat }: { label: string; stat: MetricStat }) {
  const { t } = useTranslation("metrics");
  return (
    <StatTile
      icon={Cpu}
      iconTone="ai"
      label={<MetricLabel metricKey="aiTokens" label={label} />}
      value={stat.sampleCount > 0 ? formatCount(stat.median) : t("figure.none")}
      secondaryText={<StatDetail stat={stat} format={formatCount} />}
    />
  );
}

type TrendDatum = Record<string, unknown>;

function TrendSection({ overview }: { overview: MetricsOverview }) {
  const { t } = useTranslation("metrics");
  const points = overview.weeklyTrend;
  const median = (stat: MetricStat, divisor = 1) => (stat.sampleCount > 0 && stat.median !== null ? stat.median / divisor : null);
  const data = (pick: (point: WeeklyPoint) => TrendDatum): TrendDatum[] => points.map((point) => ({ category: formatDate(point.weekStart, { month: "short", day: "numeric" }), ...pick(point) }));
  const incidentData = data((point) => ({ opened: point.incidentsOpenedCount, resolved: point.incidentsResolvedCount }));
  const resolveData = data((point) => ({ value: median(point.timeToResolve, secondsPerHour) }));
  const conclusionData = data((point) => ({ value: median(point.timeToConclusion, secondsPerMinute) }));
  const tokenData = data((point) => ({ value: median(point.tokensPerInvestigation) }));
  const oneDecimal = (value: number) => formatNumber(value, { maximumFractionDigits: 1 });
  const samples = (pick: (point: WeeklyPoint) => number) => t("trend.samples", { counts: points.map((point) => formatNumber(pick(point))).join(", ") });
  return (
    <section aria-labelledby="metrics-trend" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-trend" title={t("sections.trend.title")} description={t("sections.trend.description")} />
      <div className="grid gap-4 lg:grid-cols-2">
        <TrendCard title={t("trend.incidents")} note={samples((point) => point.incidentsOpenedCount + point.incidentsResolvedCount)}>
          <BarChart data={incidentData} series={[{ key: "opened", label: t("trend.opened") }, { key: "resolved", label: t("trend.resolved") }]} height={220} ariaLabel={t("trend.incidents")} valueFormatter={(value) => formatNumber(value)} />
        </TrendCard>
        <TrendCard title={t("trend.resolve")} note={samples((point) => point.timeToResolve.sampleCount)}>
          <BarChart data={resolveData} series={[{ key: "value", label: t("trend.resolveSeries") }]} height={220} ariaLabel={t("trend.resolve")} valueFormatter={oneDecimal} />
        </TrendCard>
        <TrendCard title={t("trend.conclusion")} note={samples((point) => point.timeToConclusion.sampleCount)}>
          <BarChart data={conclusionData} series={[{ key: "value", label: t("trend.conclusionSeries") }]} height={220} ariaLabel={t("trend.conclusion")} valueFormatter={oneDecimal} />
        </TrendCard>
        <TrendCard title={t("trend.tokens")} note={samples((point) => point.tokensPerInvestigation.sampleCount)}>
          <BarChart data={tokenData} series={[{ key: "value", label: t("trend.tokensSeries") }]} height={220} ariaLabel={t("trend.tokens")} valueFormatter={(value) => formatNumber(value, { maximumFractionDigits: 0 })} />
        </TrendCard>
      </div>
      <p className="text-caption text-muted">{t("trend.note")}</p>
    </section>
  );
}

function TrendCard({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <Card dense>
      <CardHeader title={title} />
      <CardBody>
        {children}
        <p className="mt-2 text-caption text-muted">{note}</p>
      </CardBody>
    </Card>
  );
}

function ApplicationSection({ applications }: { applications: ApplicationMetrics[] }) {
  const { t } = useTranslation("metrics");
  const statColumn = (key: string, header: string, pick: (row: ApplicationMetrics) => MetricStat, format: (value: number | null) => string): DataTableColumn<ApplicationMetrics> => ({
    key,
    header,
    align: "end",
    sortValue: (row) => pick(row).median,
    cell: (row) => <StatCell stat={pick(row)} format={format} className="items-end" />,
  });
  const columns: DataTableColumn<ApplicationMetrics>[] = [
    {
      key: "application",
      header: t("table.application"),
      isSticky: true,
      sortValue: (row) => row.applicationName,
      cell: (row) => (
        <span className="flex flex-col">
          <span className="font-medium text-default">{row.applicationName}</span>
          <span className="text-caption text-muted">{row.applicationCode}</span>
        </span>
      ),
    },
    {
      key: "incidents",
      header: t("table.incidents"),
      align: "end",
      sortValue: (row) => row.incidentsOpenedCount,
      cell: (row) => <span className="tabular-numbers">{t("table.openedResolved", { opened: formatCount(row.incidentsOpenedCount), resolved: formatCount(row.incidentsResolvedCount) })}</span>,
    },
    statColumn("detect", t("table.detect"), (row) => row.timeToDetect, formatSeconds),
    statColumn("firstUpdate", t("table.firstUpdate"), (row) => row.timeToFirstUpdate, formatSeconds),
    statColumn("resolve", t("table.resolve"), (row) => row.timeToResolve, formatSeconds),
    statColumn("conclusion", t("table.conclusion"), (row) => row.timeToConclusion, formatSeconds),
    {
      key: "correct",
      header: t("table.correct"),
      align: "end",
      sortValue: (row) => row.ratings.shareCorrect,
      cell: (row) => (
        <span className="flex flex-col items-end tabular-numbers">
          <span className={row.ratings.shareCorrect === null ? "font-medium text-muted" : "font-medium text-default"}>{row.ratings.shareCorrect === null ? t("figure.none") : formatPercentage(row.ratings.shareCorrect)}</span>
          <span className="text-caption text-muted">
            {row.ratings.shareCorrect === null ? t("table.notEnoughRatings", { count: row.ratings.ratedCount, minimum: row.ratings.minimumSample }) : t("table.ratedCount", { count: row.ratings.ratedCount })}
          </span>
        </span>
      ),
    },
    statColumn("tokens", t("table.tokens"), (row) => row.aiUsage.inputTokens, formatCount),
  ];
  return (
    <section aria-labelledby="metrics-applications" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-applications" title={t("sections.applications.title")} description={t("sections.applications.description")} />
      <DataTable columns={columns} rows={applications} getRowId={(row) => row.applicationId} caption={t("table.caption")} pageSize={25} />
    </section>
  );
}

function DefinitionsSection({ overview }: { overview: MetricsOverview }) {
  const { t } = useTranslation("metrics");
  const keys = [...overview.definitionKeys, ...overview.notAvailable.map((item) => item.metric)];
  return (
    <section aria-labelledby="metrics-definitions" className="flex flex-col gap-4">
      <SectionHeader level={3} id="metrics-definitions" title={t("sections.definitions.title")} description={t("sections.definitions.description")} />
      <dl className="grid gap-x-8 gap-y-4 md:grid-cols-2">
        {keys.map((key) => (
          <div key={key}>
            <dt className="text-body-sm font-semibold text-default">{t(`definitions.${key}.title`)}</dt>
            <dd className="mt-0.5 text-body-sm text-muted">{t(`definitions.${key}.text`)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
