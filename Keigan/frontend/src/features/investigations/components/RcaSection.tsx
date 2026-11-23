import { useEffect } from "react";
import { BookOpen, CircleHelp, Lightbulb, SearchX, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { EmptyState } from "@/components/ui/EmptyState";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/utils/cn";
import { CitationRow } from "./CitationRow";
import { CoverageGapsCard } from "./CoverageGapsCard";
import { OutcomeSummary } from "./OutcomeSummary";
import { RuledOutCard } from "./RuledOutCard";
import { FixStepCard } from "./FixStepCard";
import { runbookElementId } from "./investigationPresentation";

/** The RCA tab has to be on screen before the chosen runbook can be scrolled to: the tab switches in the same update that selects the runbook. */
const runbookScrollDelayMilliseconds = 120;

interface RcaSectionProps {
  detail: InvestigationDetail;
  onSelectEvidence: (evidenceCode: string) => void;
  /** The runbook an `[R#]` citation in the investigation chat pointed at: scrolled into view and outlined in the matched runbooks. */
  selectedRunbookId?: string | null;
}

/** Three RCA cards (what went wrong, why it happened, how to fix) with overall confidence and citations. */
export function RcaSection({ detail, onSelectEvidence, selectedRunbookId = null }: RcaSectionProps) {
  const { t } = useTranslation("investigations");
  const hasAnalysis = Boolean(detail.whatWentWrongMarkdown);
  const leadingHypothesis = detail.hypotheses.find((hypothesis) => hypothesis.isLeadingHypothesis);
  // The wording of "leading" and "confidence" is only as strong as the outcome: an unconfirmed cause is a lead, not a conclusion.
  const isCauseConfirmed = !detail.outcome || detail.outcome.code === "cause_identified" || detail.outcome.code === "not_recorded";
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    if (!selectedRunbookId) return;
    const timerId = window.setTimeout(
      () => document.getElementById(runbookElementId(selectedRunbookId))?.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "center" }),
      runbookScrollDelayMilliseconds,
    );
    return () => window.clearTimeout(timerId);
  }, [selectedRunbookId, prefersReducedMotion]);

  if (!hasAnalysis) {
    return (
      <div className="flex flex-col gap-4">
        {detail.isEvidenceOnly ? <Banner tone="warning" title={t("rca.evidenceOnlyTitle")}>{t("rca.evidenceOnlyDescription")}</Banner> : null}
        {detail.investigationStatus === "failed" ? <Banner tone="danger" title={t("rca.failedTitle")}>{detail.failureReason ?? t("rca.failedDescription")}</Banner> : null}
        <EmptyState icon={SearchX} title={t("rca.emptyTitle")} description={detail.isEvidenceOnly ? t("rca.emptyEvidenceOnly") : t("rca.emptyDescription")} isBordered />
        {detail.isEvidenceOnly ? <CoverageGapsCard gaps={detail.coverageGaps} /> : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <Card radius="lg" accent>
        <div className="flex flex-col gap-5 p-6 md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-h3 text-default">{t("rca.summaryTitle")}</h2>
              <AiGeneratedChip modelName={detail.modelNames.join(", ") || null} generatedAt={detail.completedAt} size="sm" />
            </div>
            <OutcomeSummary detail={detail} onSelectEvidence={onSelectEvidence} />
            <p className="text-body-lg text-default">{detail.executiveSummary}</p>
            {leadingHypothesis ? <p className="text-body-sm text-muted">{isCauseConfirmed ? t("rca.leading", { perspective: t(`perspective.${leadingHypothesis.analysisPerspective}`), title: leadingHypothesis.hypothesisTitle }) : t("outcome.strongestLead", { perspective: t(`perspective.${leadingHypothesis.analysisPerspective}`), title: leadingHypothesis.hypothesisTitle })}</p> : null}
            {isCauseConfirmed && detail.leadingPerspectiveReasonMarkdown ? (
              <details className="rounded-md border border-hairline px-3 py-2">
                <summary className="cursor-pointer text-body-sm font-semibold text-action">{t("outcome.whyThisLead")}</summary>
                <div className="mt-2"><MarkdownView content={detail.leadingPerspectiveReasonMarkdown} /></div>
              </details>
            ) : null}
          </div>
          {detail.overallConfidenceScore !== null && detail.outcome?.code !== "cause_not_visible" ? (
            <div className="flex shrink-0 flex-col gap-1.5 md:w-60">
              <span className="text-micro uppercase tracking-wide text-muted">{isCauseConfirmed ? t("rca.overallConfidence") : t("outcome.confidenceStrongestLead")}</span>
              <ConfidenceMeter percentage={Math.round(detail.overallConfidenceScore * 100)} />
            </div>
          ) : null}
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card>
          <CardHeader icon={SearchX} iconTone="danger" title={t("rca.whatWentWrong")} />
          <CardBody>
            <MarkdownView content={detail.whatWentWrongMarkdown ?? ""} />
            <CitationRow markdown={detail.whatWentWrongMarkdown} detail={detail} onSelectEvidence={onSelectEvidence} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader icon={Lightbulb} iconTone="warning" title={t("rca.whyItHappened")} />
          <CardBody>
            <MarkdownView content={detail.whyItHappenedMarkdown ?? ""} />
            <CitationRow markdown={detail.whyItHappenedMarkdown} detail={detail} onSelectEvidence={onSelectEvidence} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader icon={Wrench} iconTone="success" title={t("rca.howToFix")} description={t("rca.suggestOnly")} />
          <CardBody className="flex flex-col gap-4">
            {detail.fixPlan ? (
              <>
                <MarkdownView content={detail.fixPlan.overviewMarkdown} />
                <ol className="flex flex-col gap-3">
                  {detail.fixPlan.steps.map((step, position) => (
                    <FixStepCard key={step.stepId} step={step} number={position + 1} perspectiveLabel={step.perspective ? t(`perspective.${step.perspective}`) : undefined} />
                  ))}
                </ol>
              </>
            ) : (
              <MarkdownView content={detail.howToFixMarkdown ?? ""} />
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {detail.openQuestions.length > 0 ? (
          <Card>
            <CardHeader icon={CircleHelp} iconTone="info" title={t("rca.openQuestions")} description={t("rca.openQuestionsHelp")} />
            <CardBody>
              <ul className="list-disc space-y-1.5 pl-5 text-body">{detail.openQuestions.map((question) => <li key={question}>{question}</li>)}</ul>
            </CardBody>
          </Card>
        ) : null}
        <RuledOutCard detail={detail} />
        <CoverageGapsCard gaps={detail.coverageGaps} />
        {detail.matchedRunbooks.length > 0 ? (
          <Card>
            <CardHeader icon={BookOpen} iconTone="brand" title={t("rca.matchedRunbooks")} description={t("rca.matchedRunbooksHelp")} />
            <CardBody>
              <ul className="space-y-1.5 text-body">
                {detail.matchedRunbooks.map((runbook) => (
                  <li key={runbook.runbookId} id={runbookElementId(runbook.runbookId)} className={cn("scroll-mt-32 rounded-sm px-1.5 py-0.5 transition-shadow", runbook.runbookId === selectedRunbookId && "ring-2 ring-[var(--color-focus-ring-color)]")}>{runbook.runbookTitle}</li>
                ))}
              </ul>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
