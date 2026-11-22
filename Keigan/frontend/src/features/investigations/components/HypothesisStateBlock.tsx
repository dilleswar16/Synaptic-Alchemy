import { useTranslation } from "react-i18next";
import type { Hypothesis } from "@/api/investigationsApi";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { StatusChip } from "@/components/ui/StatusChip";
import { hypothesisStateTone } from "./investigationPresentation";

/** The badge for a hypothesis's state (nothing for one stored before states were recorded). */
export function HypothesisStateBadge({ hypothesis }: { hypothesis: Hypothesis }) {
  const { t } = useTranslation("investigations");
  if (!hypothesis.state) return null;
  return <StatusChip tone={hypothesisStateTone[hypothesis.state]} size="sm">{t(`hypothesisState.${hypothesis.state}`)}</StatusChip>;
}

/** Why the hypothesis ended in its state, and which of Keigan's rules changed the AI's proposal, if one did. */
export function HypothesisStateReason({ hypothesis }: { hypothesis: Hypothesis }) {
  const { t } = useTranslation("investigations");
  if (!hypothesis.state || !hypothesis.stateReasonMarkdown) return null;
  const wasChanged = hypothesis.stateGuardCode !== null && hypothesis.proposedState !== null && hypothesis.proposedState !== hypothesis.state;
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-sunken p-3">
      <span className="text-caption font-semibold uppercase tracking-wide text-muted">{t("hypothesisState.why")}</span>
      <MarkdownView content={hypothesis.stateReasonMarkdown} />
      {wasChanged ? (
        <p className="text-caption text-muted">
          {t("hypothesisState.guardNote", {
            proposed: t(`hypothesisState.value.${hypothesis.proposedState}`), final: t(`hypothesisState.value.${hypothesis.state}`), reason: t(`hypothesisState.guard.${hypothesis.stateGuardCode}`),
          })}
        </p>
      ) : null}
    </div>
  );
}
