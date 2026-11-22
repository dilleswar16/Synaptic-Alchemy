import { memo, useCallback, useMemo } from "react";
import { RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Citation } from "@/api/askKeiganApi";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { CopyButton } from "@/components/ui/CopyButton";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { formatTime } from "@/utils/formatters";
import { buildAnswerWithSources } from "./answerCopyText";
import type { AnswerRunProgress } from "./answerStreamReducer";
import { chatPillClassName } from "./chatPill";

export interface AnswerMessageProps {
  progress: AnswerRunProgress;
  /** Text of the model turn in progress, shown until the final answer replaces it. */
  streamingText: string | null;
  isCompact?: boolean;
  /** A `[T#]` citation was chosen: open that tool call in the trace. */
  onSelectStep: (runStepId: string) => void;
  /** An `[E#]` citation was chosen (investigation scope): show that evidence. Without it the chip is not clickable. */
  onSelectEvidence?: (evidenceCode: string) => void;
  /** An `[R#]` citation was chosen (investigation scope): show that runbook. Without it the chip is not clickable. */
  onSelectRunbook?: (runbookId: string) => void;
  onAskFollowUp: (question: string) => void;
  areFollowUpsDisabled: boolean;
  /** Sends the same question again; offered only when the server says the failure is retryable. */
  onRetry?: () => void;
  /** The failure of a run that ended while this screen was open is announced as an alert, once. A stored run (a conversation reopened) is not: its failure is already history. */
  shouldAnnounceFailure?: boolean;
}

interface CitationHandlers {
  onSelectStep: AnswerMessageProps["onSelectStep"];
  onSelectEvidence: AnswerMessageProps["onSelectEvidence"];
  onSelectRunbook: AnswerMessageProps["onSelectRunbook"];
}

/** What choosing a citation does, or undefined when the screen has no action for that kind of citation (the chip is then not a button). */
function citationAction({ runStepId, evidenceCode, runbookId }: Citation, { onSelectStep, onSelectEvidence, onSelectRunbook }: CitationHandlers): (() => void) | undefined {
  if (runStepId) {
    return () => onSelectStep(runStepId);
  }
  if (evidenceCode && onSelectEvidence) {
    return () => onSelectEvidence(evidenceCode);
  }
  return runbookId && onSelectRunbook ? () => onSelectRunbook(runbookId) : undefined;
}

/**
 * The answer of one run (spec 8.4): the failure banner, the "unverified" warning, the Markdown answer with its `[T#]` citations as chips, the
 * list of sources, "Copy answer with sources" and the follow-up questions. While the run goes on it shows the streamed text instead.
 * It is memoised so the answers above the one being written are not parsed and redrawn for every stream event, and so a chip that has focus keeps it.
 */
export const AnswerMessage = memo(function AnswerMessage({
  progress,
  streamingText,
  isCompact = false,
  onSelectStep,
  onSelectEvidence,
  onSelectRunbook,
  onAskFollowUp,
  areFollowUpsDisabled,
  onRetry,
  shouldAnnounceFailure = true,
}: AnswerMessageProps) {
  const { t } = useTranslation("chat");
  const { answer, error } = progress;
  const citationsByCode = useMemo(() => new Map(answer?.citations.map((citation) => [citation.code, citation])), [answer]);
  // A new function here would give the Markdown view new element types and remount every chip and link of the answer.
  const renderCitation = useCallback(
    (citationCode: string) => {
      const citation = citationsByCode.get(citationCode);
      return citation ? <EvidenceChip code={citationCode} title={citation.title} onSelect={citationAction(citation, { onSelectStep, onSelectEvidence, onSelectRunbook })} className="mx-0.5 align-baseline" /> : null;
    },
    [citationsByCode, onSelectStep, onSelectEvidence, onSelectRunbook],
  );

  return (
    <div className="flex flex-col gap-3">
      {error && progress.status === "failed" ? (
        <Banner
          tone="danger"
          role={shouldAnnounceFailure ? "alert" : "status"}
          title={error.title}
          action={error.isRetryable && onRetry ? <Button variant="secondary" size="sm" leadingIcon={RotateCw} onClick={onRetry}>{t("answer.tryAgain")}</Button> : undefined}
        >
          {error.detail}
          {error.correlationId ? <span className="mt-1 block font-mono text-caption text-muted">{t("answer.reference", { correlationId: error.correlationId })}</span> : null}
        </Banner>
      ) : null}

      {answer?.isUnverified && !answer.isRefusal ? <Banner tone="warning">{t("answer.unverified")}</Banner> : null}

      {answer ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-caption font-semibold text-muted">{t("answer.label")}</span>
            <AiGeneratedChip size="sm" />
            {progress.completedAt ? <span className="text-caption text-muted">{formatTime(progress.completedAt)}</span> : null}
            <CopyButton
              value={() => buildAnswerWithSources({ answer, steps: progress.steps, answeredAt: progress.completedAt, translate: t })}
              label={t("answer.copy")}
              showLabel={!isCompact}
              className="ml-auto"
            />
          </div>
          <MarkdownView content={answer.markdown} size={isCompact ? "default" : "large"} renderCitation={renderCitation} />
          {answer.citations.length > 0 ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <span className="text-caption text-muted">{t("answer.sourcesHeading")}</span>
              {answer.citations.map((citation) => (
                <span key={citation.code} className="inline-flex min-w-0 items-center gap-1.5">
                  <EvidenceChip code={citation.code} onSelect={citationAction(citation, { onSelectStep, onSelectEvidence, onSelectRunbook })} />
                  <span className="min-w-0 text-caption break-words text-muted">{citation.title}</span>
                </span>
              ))}
            </div>
          ) : null}
          {answer.followUps.length > 0 ? (
            <div role="group" aria-label={t("answer.askNext")} className="flex flex-wrap gap-2">
              {answer.followUps.map((followUp) => (
                <button key={followUp} type="button" disabled={areFollowUpsDisabled} onClick={() => onAskFollowUp(followUp)} className={chatPillClassName}>
                  {followUp}
                </button>
              ))}
            </div>
          ) : null}
        </>
      ) : streamingText ? (
        <MarkdownView content={streamingText} size={isCompact ? "default" : "large"} />
      ) : null}
    </div>
  );
});
