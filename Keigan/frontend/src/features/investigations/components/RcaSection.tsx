import { BookOpen, CircleHelp, Lightbulb, SearchX, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { EmptyState } from "@/components/ui/EmptyState";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { extractCitationCodes } from "./investigationPresentation";

interface RcaSectionProps {
  detail: InvestigationDetail;
  onSelectEvidence: (evidenceCode: string) => void;
}

function CitationRow({ markdown, detail, onSelectEvidence }: { markdown: string | null; detail: InvestigationDetail; onSelectEvidence: (code: string) => void }) {
  const codes = extractCitationCodes(markdown);
  if (codes.length === 0) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-1.5 border-t border-hairline pt-3">
      {codes.map((code) => (
        <EvidenceChip key={code} code={code} title={detail.evidence.find((item) => item.evidenceCode === code)?.evidenceTitle} onSelect={onSelectEvidence} />
      ))}
    </div>
  );
}

/** Three RCA cards (what went wrong, why it happened, how to fix) with overall confidence and citations. */
export function RcaSection({ detail, onSelectEvidence }: RcaSectionProps) {
  const { t } = useTranslation("investigations");
  const hasAnalysis = Boolean(detail.whatWentWrongMarkdown);
  const leadingHypothesis = detail.hypotheses.find((hypothesis) => hypothesis.isLeadingHypothesis);

  if (!hasAnalysis) {
    return (
      <div className="flex flex-col gap-4">
        {detail.isEvidenceOnly ? <Banner tone="warning" title={t("rca.evidenceOnlyTitle")}>{t("rca.evidenceOnlyDescription")}</Banner> : null}
        {detail.investigationStatus === "failed" ? <Banner tone="danger" title={t("rca.failedTitle")}>{detail.failureReason ?? t("rca.failedDescription")}</Banner> : null}
        <EmptyState icon={SearchX} title={t("rca.emptyTitle")} description={detail.isEvidenceOnly ? t("rca.emptyEvidenceOnly") : t("rca.emptyDescription")} isBordered />
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
            <p className="text-body-lg text-default">{detail.executiveSummary}</p>
            {leadingHypothesis ? <p className="text-body-sm text-muted">{t("rca.leading", { perspective: t(`perspective.${leadingHypothesis.analysisPerspective}`), title: leadingHypothesis.hypothesisTitle })}</p> : null}
          </div>
          {detail.overallConfidenceScore !== null ? (
            <div className="flex shrink-0 flex-col gap-1.5 md:w-60">
              <span className="text-micro uppercase tracking-wide text-muted">{t("rca.overallConfidence")}</span>
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
          <CardBody>
            <MarkdownView content={detail.howToFixMarkdown ?? ""} />
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
        {detail.matchedRunbooks.length > 0 ? (
          <Card>
            <CardHeader icon={BookOpen} iconTone="brand" title={t("rca.matchedRunbooks")} description={t("rca.matchedRunbooksHelp")} />
            <CardBody>
              <ul className="space-y-1.5 text-body">{detail.matchedRunbooks.map((runbook) => <li key={runbook.runbookId}>{runbook.runbookTitle}</li>)}</ul>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
