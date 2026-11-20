import { Boxes, Network, Code2, Server, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AnalysisPerspective, CodeChange, Hypothesis, InvestigationDetail } from "@/api/investigationsApi";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { perspectiveOrder } from "./investigationPresentation";

const perspectiveIcons: Record<AnalysisPerspective, LucideIcon> = { application: Code2, dependencies: Network, infrastructure: Server };

function CodeChangeView({ change }: { change: CodeChange }) {
  const { t } = useTranslation("investigations");
  return (
    <div className="flex flex-col gap-2 rounded-md border border-hairline bg-surface-sunken p-3">
      <div className="flex flex-wrap items-center gap-2 text-caption text-muted">
        {change.repositoryName ? <span className="font-mono">{change.repositoryName}</span> : null}
        <span className="font-mono text-default">{change.filePath}</span>
      </div>
      <p className="text-body-sm text-default">{change.changeDescription}</p>
      {change.beforeSnippet ? <CommandBlock title={t("hypotheses.before")} commands={change.beforeSnippet} /> : null}
      {change.afterSnippet ? <CommandBlock title={t("hypotheses.after")} commands={change.afterSnippet} /> : null}
    </div>
  );
}

function HypothesisCard({ hypothesis, detail, onSelectEvidence }: { hypothesis: Hypothesis; detail: InvestigationDetail; onSelectEvidence: (code: string) => void }) {
  const { t } = useTranslation("investigations");
  const Icon = perspectiveIcons[hypothesis.analysisPerspective] ?? Boxes;
  const fix = hypothesis.proposedFix;
  const titleFor = (code: string) => detail.evidence.find((item) => item.evidenceCode === code)?.evidenceTitle;
  return (
    <Card accent={hypothesis.isLeadingHypothesis} className="h-full">
      <CardHeader
        icon={Icon}
        iconTone={hypothesis.isLeadingHypothesis ? "ai" : "neutral"}
        title={t(`perspective.${hypothesis.analysisPerspective}`)}
        description={hypothesis.isLeadingHypothesis ? undefined : t("hypotheses.alternative")}
        actions={hypothesis.isLeadingHypothesis ? <Badge tone="ai" variant="solid">{t("hypotheses.leading")}</Badge> : undefined}
      />
      <CardBody className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <h4 className="text-h4 text-default">{hypothesis.hypothesisTitle}</h4>
          <ConfidenceMeter percentage={Math.round(hypothesis.confidenceScore * 100)} size="sm" />
        </div>
        <MarkdownView content={hypothesis.hypothesisStatementMarkdown ?? ""} />
        {hypothesis.reasoningMarkdown ? (
          <details className="group rounded-md border border-hairline px-3 py-2">
            <summary className="cursor-pointer text-body-sm font-semibold text-action">{t("hypotheses.reasoning")}</summary>
            <div className="mt-2"><MarkdownView content={hypothesis.reasoningMarkdown} /></div>
          </details>
        ) : null}
        {hypothesis.supportingEvidenceCodes.length + hypothesis.contradictingEvidenceCodes.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h5 className="text-caption font-semibold uppercase tracking-wide text-muted">{t("hypotheses.evidence")}</h5>
            <div className="flex flex-wrap gap-1.5">
              {hypothesis.supportingEvidenceCodes.map((code) => <EvidenceChip key={`s-${code}`} code={code} title={titleFor(code)} relation="supporting" onSelect={onSelectEvidence} />)}
              {hypothesis.contradictingEvidenceCodes.map((code) => <EvidenceChip key={`c-${code}`} code={code} title={titleFor(code)} relation="contradicting" onSelect={onSelectEvidence} />)}
            </div>
          </div>
        ) : null}
        {hypothesis.matchedRunbook ? <Badge tone="brand">{t("hypotheses.runbook", { title: hypothesis.matchedRunbook.runbookTitle })}</Badge> : null}

        {fix ? (
          <div className="flex flex-col gap-3 border-t border-hairline pt-4">
            <div className="flex items-center justify-between gap-2">
              <h5 className="text-body-sm font-semibold text-default">{t("hypotheses.proposedFix")}</h5>
              {hypothesis.fixRiskLevel === "high" ? <Badge tone="danger" variant="solid"><TriangleAlert aria-hidden="true" size={12} className="mr-1 inline" />{t("hypotheses.highRisk")}</Badge> : <Badge tone={hypothesis.fixRiskLevel === "medium" ? "warning" : "success"}>{t(`hypotheses.risk.${hypothesis.fixRiskLevel}`)}</Badge>}
            </div>
            <p className="text-body-sm text-muted">{fix.summary}</p>
            <ol className="flex flex-col gap-3">
              {fix.steps.map((step, stepIndex) => (
                <li key={stepIndex} className="flex flex-col gap-2">
                  <p className="text-body-sm text-default"><span className="mr-1.5 font-semibold text-muted">{stepIndex + 1}.</span>{step.description}</p>
                  {step.commandText ? <CommandBlock commands={step.commandText} riskLevel={step.commandRiskLevel ?? "low"} wrapLines /> : null}
                  {step.commandRiskLevel === "high" ? <p className="flex items-center gap-1.5 text-caption font-semibold text-danger"><TriangleAlert aria-hidden="true" size={13} />{t("hypotheses.highRiskCommand")}</p> : null}
                </li>
              ))}
            </ol>
            {fix.codeChanges.length > 0 ? (
              <div className="flex flex-col gap-2">
                <h5 className="text-caption font-semibold uppercase tracking-wide text-muted">{t("hypotheses.codeChanges")}</h5>
                {fix.codeChanges.map((change, changeIndex) => <CodeChangeView key={changeIndex} change={change} />)}
              </div>
            ) : null}
            {fix.verificationSteps.length > 0 ? (
              <div>
                <h5 className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted">{t("hypotheses.verify")}</h5>
                <ul className="list-disc space-y-1 pl-5 text-body-sm">{fix.verificationSteps.map((step) => <li key={step}>{step}</li>)}</ul>
              </div>
            ) : null}
            {fix.rollbackSteps.length > 0 ? (
              <div>
                <h5 className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted">{t("hypotheses.rollback")}</h5>
                <ul className="list-disc space-y-1 pl-5 text-body-sm">{fix.rollbackSteps.map((step) => <li key={step}>{step}</li>)}</ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

/** Three hypothesis columns (application, dependencies, infrastructure); the leading one is ribboned. */
export function HypothesesSection({ detail, onSelectEvidence }: { detail: InvestigationDetail; onSelectEvidence: (code: string) => void }) {
  const { t } = useTranslation("investigations");
  const ordered = [...detail.hypotheses].sort((first, second) => perspectiveOrder.indexOf(first.analysisPerspective) - perspectiveOrder.indexOf(second.analysisPerspective));
  return (
    <div className="flex flex-col gap-4">
      <p className="text-body-sm text-muted">{t("hypotheses.intro")}</p>
      <div className="grid items-start gap-5 xl:grid-cols-3">
        {ordered.map((hypothesis) => <HypothesisCard key={hypothesis.hypothesisId} hypothesis={hypothesis} detail={detail} onSelectEvidence={onSelectEvidence} />)}
      </div>
    </div>
  );
}
