import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Evidence, InvestigationDetail, LogPattern, MetricSeriesSummary, SignalStrength } from "@/api/investigationsApi";
import { TimeSeriesChart } from "@/components/charts";
import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDateTime, formatNumber, formatTime } from "@/utils/formatters";
import { cn } from "@/utils/cn";
import { evidenceElementId, signalStrengthTone } from "./investigationPresentation";

function PatternRow({ pattern }: { pattern: LogPattern }) {
  const { t } = useTranslation("investigations");
  const isChange = pattern.level === "change";
  return (
    <li className="flex flex-col gap-1.5 rounded-md border border-hairline bg-surface-sunken px-3 py-2.5">
      <div className="flex flex-wrap items-start gap-2">
        <p className="min-w-0 flex-1 break-words font-mono text-code text-default">{pattern.template}</p>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {isChange ? <Badge tone="warning">{t(`evidence.changeKind.${pattern.changeKind ?? "other"}`, { defaultValue: t("evidence.change") })}</Badge> : <span className="text-caption font-semibold text-default">{t("evidence.occurrences", { count: pattern.count })}</span>}
          {pattern.isNewPattern && !isChange ? <Badge tone="danger" variant="solid">{t("evidence.new")}</Badge> : null}
          {pattern.changeRatio ? <Badge tone="warning">{t("evidence.timesBaseline", { ratio: pattern.changeRatio })}</Badge> : null}
        </div>
      </div>
      {pattern.firstSeenAt ? (
        <p className="text-caption text-muted">
          {isChange ? formatDateTime(pattern.firstSeenAt) : t("evidence.seenBetween", { first: formatTime(pattern.firstSeenAt), last: formatTime(pattern.lastSeenAt) })}
          {isChange && pattern.caller ? ` · ${pattern.caller}` : ""}
        </p>
      ) : null}
      {pattern.sampleLinesMasked.length > 0 ? (
        <details>
          <summary className="cursor-pointer text-caption font-semibold text-action">{t("evidence.samples")}</summary>
          <ul className="mt-1 space-y-1">{pattern.sampleLinesMasked.map((line, lineIndex) => <li key={lineIndex} className="break-words font-mono text-caption text-muted">{line}</li>)}</ul>
        </details>
      ) : null}
    </li>
  );
}

function MetricView({ series }: { series: MetricSeriesSummary }) {
  const { t } = useTranslation("investigations");
  const data = series.points.map((point) => ({ time: point.t, value: point.v }));
  return (
    <div className="rounded-md border border-hairline p-3">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-body-sm text-default">{series.metricName}</span>
        <span className="text-caption text-muted">{t("evidence.metricPeak", { peak: formatNumber(series.windowPeak), baseline: formatNumber(series.baselineMedian), unit: series.unit })}</span>
      </div>
      <TimeSeriesChart
        data={data}
        series={[{ key: "value", label: series.metricName, color: series.signalStrength === "low" ? undefined : "var(--color-danger-fill)", showArea: true }]}
        xKey="time"
        height={120}
        targetValue={series.baselineMedian}
        targetLabel={t("evidence.baselineLabel")}
        ariaLabel={t("evidence.metricChartLabel", { metric: series.metricName })}
      />
    </div>
  );
}

function EvidenceCard({ evidence, isSelected }: { evidence: Evidence; isSelected: boolean }) {
  const { t } = useTranslation("investigations");
  return (
    <Card id={evidenceElementId(evidence.evidenceCode)} dense className={cn("scroll-mt-32 transition-shadow", isSelected && "ring-2 ring-[var(--color-focus-ring-color)]")}>
      <CardBody className="flex flex-col gap-3 !p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-sm bg-action-subtle px-1.5 py-0.5 font-mono text-caption font-semibold text-action-subtle-text">{evidence.evidenceCode}</span>
              <StatusChip tone={signalStrengthTone[evidence.signalStrength as SignalStrength]} size="sm">{t(`evidence.strength.${evidence.signalStrength}`)}</StatusChip>
              <Badge tone="neutral">{t(`evidence.category.${evidence.evidenceCategory}`, { defaultValue: evidence.evidenceCategory })}</Badge>
              {evidence.maskedValueCount > 0 ? <Badge tone="info">{t("evidence.masked", { count: evidence.maskedValueCount })}</Badge> : null}
            </div>
            <h4 className="text-body font-semibold text-default">{evidence.evidenceTitle}</h4>
          </div>
          {evidence.deepLinkUrl ? (
            <Button asChild variant="ghost" size="sm" trailingIcon={ExternalLink}>
              <a href={evidence.deepLinkUrl} target="_blank" rel="noreferrer">{t("evidence.openInPortal")}</a>
            </Button>
          ) : null}
        </div>
        {evidence.possiblePromptInjection ? (
          <Banner tone="warning" icon={ShieldAlert} title={t("evidence.injectionTitle")}>{t("evidence.injectionDescription")}</Banner>
        ) : null}
        {evidence.evidenceSummary ? <p className="text-body-sm text-default">{evidence.evidenceSummary}</p> : null}
        {evidence.condensedPatterns.length > 0 ? <ul className="flex flex-col gap-2">{evidence.condensedPatterns.slice(0, 6).map((pattern, patternIndex) => <PatternRow key={patternIndex} pattern={pattern} />)}</ul> : null}
        {evidence.metricSeries.length > 0 ? <div className="grid gap-3 lg:grid-cols-2">{evidence.metricSeries.map((series) => <MetricView key={series.metricName} series={series} />)}</div> : null}
        {evidence.queryText && evidence.queryLanguage !== "none" ? (
          <details>
            <summary className="cursor-pointer text-caption font-semibold text-action">{t("evidence.query", { language: evidence.queryLanguage.toUpperCase() })}</summary>
            <div className="mt-2">
              <CommandBlock commands={evidence.queryText} riskLevel="low" title={t("evidence.queryTitle", { count: evidence.matchedRecordCount })} />
              {evidence.queryTimeRangeStart ? <p className="mt-1 text-caption text-muted">{t("evidence.window", { start: formatDateTime(evidence.queryTimeRangeStart), end: formatDateTime(evidence.queryTimeRangeEnd) })}</p> : null}
            </div>
          </details>
        ) : null}
      </CardBody>
    </Card>
  );
}

type StrengthFilter = "relevant" | "strong" | "all";
const allServices = "__all__";

interface EvidenceSectionProps {
  detail: InvestigationDetail;
  selectedEvidenceCode: string | null;
}

/** Evidence grouped by service: strong and medium signals first, weak or ruled-out items behind "Show N more"; the E-number anchors still open the item they point to. */
export function EvidenceSection({ detail, selectedEvidenceCode }: EvidenceSectionProps) {
  const { t } = useTranslation("investigations");
  const [strengthFilter, setStrengthFilter] = useState<StrengthFilter>("relevant");
  const [serviceFilter, setServiceFilter] = useState(allServices);
  const [expandedGroups, setExpandedGroups] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    if (!selectedEvidenceCode) return;
    setStrengthFilter("all");
    setServiceFilter(allServices);
    const timerId = window.setTimeout(() => document.getElementById(evidenceElementId(selectedEvidenceCode))?.scrollIntoView({ behavior: "smooth", block: "center" }), 120);
    return () => window.clearTimeout(timerId);
  }, [selectedEvidenceCode]);

  const serviceNames = useMemo(() => [...new Set(detail.evidence.map((item) => item.serviceName ?? t("evidence.platform")))], [detail.evidence, t]);
  const groups = useMemo(() => {
    const grouped = new Map<string, { shown: Evidence[]; hidden: Evidence[] }>();
    for (const item of detail.evidence) {
      const service = item.serviceName ?? t("evidence.platform");
      if (serviceFilter !== allServices && service !== serviceFilter) continue;
      if (strengthFilter === "strong" && item.signalStrength !== "high") continue;
      const group = grouped.get(service) ?? { shown: [], hidden: [] };
      (strengthFilter === "relevant" && item.signalStrength === "low" ? group.hidden : group.shown).push(item);
      grouped.set(service, group);
    }
    return [...grouped.entries()];
  }, [detail.evidence, strengthFilter, serviceFilter, t]);

  if (detail.evidence.length === 0) return <EmptyState title={t("evidence.emptyTitle")} description={t("evidence.emptyDescription")} isBordered />;
  const strongCount = detail.evidence.filter((item) => item.signalStrength === "high").length;
  const relevantCount = detail.evidence.filter((item) => item.signalStrength !== "low").length;
  const toggleGroup = (service: string) => setExpandedGroups((previous) => { const next = new Set(previous); if (!next.delete(service)) next.add(service); return next; });
  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-3xl text-body-sm text-muted">{t("evidence.intro", { window: `${formatDateTime(detail.investigationWindowStart)} - ${formatDateTime(detail.investigationWindowEnd)}` })}</p>
      <div className="flex flex-wrap items-center gap-3" role="group" aria-label={t("evidence.filterBar")}>
        <SegmentedControl<StrengthFilter>
          aria-label={t("evidence.filterLabel")}
          value={strengthFilter}
          onValueChange={setStrengthFilter}
          options={[
            { value: "relevant", label: t("evidence.filterRelevant", { count: relevantCount }) },
            { value: "strong", label: t("evidence.filterStrong", { count: strongCount }) },
            { value: "all", label: t("evidence.filterAll", { count: detail.evidence.length }) },
          ]}
        />
        {serviceNames.length > 1 ? (
          <Select
            size="sm"
            aria-label={t("evidence.serviceFilter")}
            value={serviceFilter}
            onValueChange={setServiceFilter}
            options={[{ value: allServices, label: t("evidence.allServices") }, ...serviceNames.map((name) => ({ value: name, label: name }))]}
            className="w-56"
          />
        ) : null}
      </div>
      {groups.length === 0 ? <p className="text-body-sm text-muted">{t("evidence.noMatches")}</p> : null}
      {groups.map(([serviceName, { shown, hidden }]) => {
        const isExpanded = expandedGroups.has(serviceName);
        return (
          <section key={serviceName} aria-label={serviceName} className="flex flex-col gap-3">
            <h3 className="text-h4 text-default">{serviceName}</h3>
            {shown.map((item) => <EvidenceCard key={item.evidenceId} evidence={item} isSelected={selectedEvidenceCode === item.evidenceCode} />)}
            {isExpanded ? hidden.map((item) => <EvidenceCard key={item.evidenceId} evidence={item} isSelected={selectedEvidenceCode === item.evidenceCode} />) : null}
            {hidden.length > 0 ? (
              <Button variant="secondary" size="sm" className="self-start" leadingIcon={isExpanded ? ChevronUp : ChevronDown} aria-expanded={isExpanded} onClick={() => toggleGroup(serviceName)}>
                {isExpanded ? t("evidence.showFewer") : t("evidence.showMore", { count: hidden.length })}
              </Button>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
