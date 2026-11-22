import { useTranslation } from "react-i18next";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { StatusChip } from "@/components/ui/StatusChip";
import { CitationRow } from "./CitationRow";
import { outcomeTone } from "./investigationPresentation";

/** How far the investigation got, said first: the outcome, why, and (when Keigan's rules changed the AI's conclusion) which rule did it. */
export function OutcomeSummary({ detail, onSelectEvidence }: { detail: InvestigationDetail; onSelectEvidence: (code: string) => void }) {
  const { t } = useTranslation("investigations");
  const outcome = detail.outcome;
  if (!outcome) return null;
  if (outcome.code === "not_recorded") return <p className="text-caption text-muted">{t("outcome.notRecorded")}</p>;
  const wasChanged = outcome.guardCode !== null && outcome.proposedCode !== null && outcome.proposedCode !== outcome.code;
  return (
    <div className="flex flex-col gap-2" aria-label={t("outcome.label")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <StatusChip tone={outcomeTone[outcome.code]}>{t(`outcome.${outcome.code}.title`)}</StatusChip>
        <span className="text-body-sm text-muted">{t(`outcome.${outcome.code}.description`)}</span>
      </div>
      {outcome.reasonMarkdown ? (
        <div>
          <MarkdownView content={outcome.reasonMarkdown} />
          <CitationRow markdown={outcome.reasonMarkdown} detail={detail} onSelectEvidence={onSelectEvidence} />
        </div>
      ) : null}
      {wasChanged ? (
        <p className="text-caption text-muted">
          {t("outcome.guardNote", { proposed: t(`outcome.value.${outcome.proposedCode}`), final: t(`outcome.value.${outcome.code}`), reason: t(`outcome.guard.${outcome.guardCode}`) })}
        </p>
      ) : null}
    </div>
  );
}
