import { memo, useCallback, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { runUnavailableReason, useAnswerRun } from "@/api/askKeiganApi";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/utils/cn";
import { AnswerMessage } from "./AnswerMessage";
import { AnswerRunTrace, type TraceFocusRequest } from "./AnswerRunTrace";
import type { AnswerRunProgress, StreamConnection, ToolProgress } from "./answerStreamReducer";

export interface AssistantRunProps {
  progress: AnswerRunProgress;
  streamingText?: string | null;
  toolProgress?: Readonly<Record<string, ToolProgress>>;
  connection?: StreamConnection;
  isCompact?: boolean;
  onSelectEvidence?: (evidenceCode: string) => void;
  onSelectRunbook?: (runbookId: string) => void;
  onAskFollowUp: (question: string) => void;
  areFollowUpsDisabled: boolean;
  onRetry?: () => void;
  /** The run was read back from the server: its failure is history and is not announced again. */
  isStored?: boolean;
}

/** The frame of Keigan's side of one question: the mark, and the rule beside the content. */
function AssistantRunFrame({ isBusy = false, isCompact, children }: { isBusy?: boolean; isCompact: boolean; children: ReactNode }) {
  return (
    <article aria-busy={isBusy} className="flex max-w-full items-start gap-3 self-start">
      {isCompact ? null : <KeiganLogo variant="mark" size={26} className="mt-0.5 shrink-0" />}
      <div className={cn("flex min-w-0 flex-1 flex-col gap-3", !isCompact && "border-l-2 border-hairline pl-4")}>{children}</div>
    </article>
  );
}

/**
 * Keigan's side of one question: the steps, then the answer. The same component draws a run that is streaming and a stored one. Memoised, with
 * stable callbacks below it, so only the run that receives an event is redrawn.
 */
export const AssistantRun = memo(function AssistantRun({
  progress,
  streamingText = null,
  toolProgress,
  connection = "closed",
  isCompact = false,
  onSelectEvidence,
  onSelectRunbook,
  onAskFollowUp,
  areFollowUpsDisabled,
  onRetry,
  isStored = false,
}: AssistantRunProps) {
  const { t } = useTranslation("chat");
  const [focusRequest, setFocusRequest] = useState<TraceFocusRequest | null>(null);
  const selectStep = useCallback((runStepId: string) => setFocusRequest((previous) => ({ runStepId, token: (previous?.token ?? 0) + 1 })), []);
  return (
    <AssistantRunFrame isBusy={progress.status === "running"} isCompact={isCompact}>
      <AnswerRunTrace progress={progress} toolProgress={toolProgress} isCompact={isCompact} focusRequest={focusRequest} />
      {connection === "reconnecting" ? <p className="text-caption text-muted">{t("trace.connectionLost")}</p> : null}
      <AnswerMessage
        progress={progress}
        streamingText={streamingText}
        isCompact={isCompact}
        onSelectStep={selectStep}
        onSelectEvidence={onSelectEvidence}
        onSelectRunbook={onSelectRunbook}
        onAskFollowUp={onAskFollowUp}
        areFollowUpsDisabled={areFollowUpsDisabled}
        onRetry={onRetry}
        shouldAnnounceFailure={!isStored}
      />
    </AssistantRunFrame>
  );
});

/** A run read back from the server (conversation history): loads the snapshot, and keeps polling while the run is still going. */
export const StoredAssistantRun = memo(function StoredAssistantRun({ answerRunId, ...assistantRunProps }: Omit<AssistantRunProps, "progress" | "isStored"> & { answerRunId: string }) {
  const { t } = useTranslation("chat");
  const answerRun = useAnswerRun(answerRunId);
  if (answerRun.isError) {
    // A run the server will not show (access removed, trace no longer kept) is a calm caption, not an error: the question above still stands.
    const unavailableReason = runUnavailableReason(answerRun.error);
    return unavailableReason ? (
      <AssistantRunFrame isCompact={assistantRunProps.isCompact ?? false}>
        <p className="text-caption text-muted">{t(`trace.${unavailableReason}`)}</p>
      </AssistantRunFrame>
    ) : (
      <ErrorState size="sm" error={answerRun.error} onRetry={() => void answerRun.refetch()} isRetrying={answerRun.isFetching} />
    );
  }
  if (!answerRun.data) {
    return <Skeleton className="h-16 w-full" />;
  }
  return <AssistantRun progress={answerRun.data} isStored {...assistantRunProps} />;
});
