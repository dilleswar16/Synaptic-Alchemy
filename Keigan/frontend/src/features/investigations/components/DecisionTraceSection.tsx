import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useInvestigationTrace, type InvestigationDetail } from "@/api/investigationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatNumber } from "@/utils/formatters";
import { outcomeTone } from "./investigationPresentation";
import { RawOutputDialog } from "./RawOutputDialog";
import { TraceStepRow } from "./TraceStepRow";

/** The decision trace tab (spec 28): what Keigan did in order and why. Anyone who can read the investigation sees it; raw AI answers are for application admins. */
export function DecisionTraceSection({ detail, isRunning, canSeeRawOutput }: { detail: InvestigationDetail; isRunning: boolean; canSeeRawOutput: boolean }) {
  const { t } = useTranslation("investigations");
  const trace = useInvestigationTrace(detail.investigationId, isRunning);
  const [expandedStepIds, setExpandedStepIds] = useState<ReadonlySet<string>>(new Set());
  const [rawStepId, setRawStepId] = useState<string | null>(null);
  if (trace.isPending) return <Skeleton className="h-64" />;
  if (trace.isError) return <ErrorState error={trace.error} onRetry={() => void trace.refetch()} />;
  const data = trace.data;
  const toggle = (traceStepId: string) => setExpandedStepIds((current) => { const next = new Set(current); if (!next.delete(traceStepId)) next.add(traceStepId); return next; });
  const outcomeCode = data.outcome?.code;
  return (
    <div className="flex flex-col gap-5">
      <p className="text-body-sm text-muted">{t("trace.description")}</p>
      {!data.isRecorded ? <Banner tone="info">{t("trace.notRecorded")}</Banner> : null}
      {data.isRecorded && !data.isComplete ? <Banner tone={isRunning ? "info" : "warning"}>{isRunning ? t("trace.running") : t("trace.incomplete")}</Banner> : null}
      <Card>
        <CardBody>
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
            <div><dt className="text-caption text-muted">{t("trace.summary.outcome")}</dt><dd>{outcomeCode && outcomeCode !== "not_recorded" ? <StatusChip tone={outcomeTone[outcomeCode]} size="sm">{t(`outcome.${outcomeCode}.title`)}</StatusChip> : <span className="text-body-sm text-muted">—</span>}</dd></div>
            <div><dt className="text-caption text-muted">{t("trace.summary.models")}</dt><dd className="text-body-sm">{data.models.map((model) => `${model.modelName} ×${model.callCount}`).join(", ") || "—"}</dd></div>
            <div><dt className="text-caption text-muted">{t("trace.summary.duration")}</dt><dd className="text-body-sm">{data.totals.durationMilliseconds !== null ? `${formatNumber(Math.round(data.totals.durationMilliseconds / 1000))} s` : "—"}</dd></div>
            <div>
              <dt className="text-caption text-muted">{t("trace.summary.tokens")}</dt>
              <dd className="text-body-sm">{formatNumber(data.totals.inputTokenCount)} / {formatNumber(data.totals.outputTokenCount)}{data.totals.tokenCountsEstimated ? ` (${t("trace.summary.estimated")})` : ""}</dd>
            </div>
            <div>
              <dt className="text-caption text-muted">{t("trace.summary.attempts")}</dt>
              <dd className="text-body-sm">{data.totals.attemptCount}{data.totals.failedAttemptCount > 0 ? ` · ${t("trace.summary.failedAttempts", { count: data.totals.failedAttemptCount })}` : ""}</dd>
            </div>
          </dl>
        </CardBody>
      </Card>
      {data.prompts.length > 0 ? (
        <Card>
          <CardHeader title={t("trace.prompts.title")} />
          <CardBody>
            <ul className="flex flex-col gap-1.5 text-body-sm">
              {data.prompts.map((prompt) => (
                <li key={prompt.promptKey} className="flex flex-wrap gap-x-4">
                  <span className="font-mono">{prompt.promptKey}</span><span className="text-muted">{t("trace.prompts.version")} {prompt.promptVersion}</span>
                  <span className="font-mono text-muted" title={prompt.promptTemplateSha256 ?? undefined}>{prompt.promptTemplateSha256?.slice(0, 12)}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
      {data.steps.length > 0 ? (
        <section aria-labelledby="trace-steps-heading" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 id="trace-steps-heading" className="text-h3 font-semibold text-default">{t("trace.steps.title")}</h3>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setExpandedStepIds(new Set(data.steps.map((step) => step.traceStepId)))}>{t("trace.steps.expandAll")}</Button>
              <Button variant="ghost" size="sm" onClick={() => setExpandedStepIds(new Set())}>{t("trace.steps.collapseAll")}</Button>
            </div>
          </div>
          <ol className="flex flex-col gap-2">
            {data.steps.map((step) => (
              <TraceStepRow key={step.traceStepId} step={step} isExpanded={expandedStepIds.has(step.traceStepId)} onToggle={() => toggle(step.traceStepId)} canSeeRawOutput={canSeeRawOutput} onShowRawOutput={setRawStepId} />
            ))}
          </ol>
        </section>
      ) : null}
      {data.callsWithoutStep.length > 0 ? (
        <Card>
          <CardHeader title={t("trace.callsWithoutStep.title")} description={t("trace.callsWithoutStep.description")} />
          <CardBody>
            <ul className="flex flex-col gap-1.5 text-body-sm">
              {data.callsWithoutStep.map((call, index) => (
                <li key={index} className="flex flex-wrap gap-x-4">
                  <span className="font-mono">{call.featureName}</span><span className="text-muted">{call.modelName}</span>
                  <span className="text-muted">{formatNumber(call.inputTokenCount)} / {formatNumber(call.outputTokenCount)}</span><span className="text-muted">{call.outcomeStatus}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
      <RawOutputDialog investigationId={detail.investigationId} traceStepId={rawStepId} onClose={() => setRawStepId(null)} />
    </div>
  );
}
