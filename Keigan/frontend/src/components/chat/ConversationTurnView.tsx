import { memo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { AssistantRun, StoredAssistantRun } from "./AssistantRun";
import { ChatMessageView } from "./ChatMessageView";
import { areConversationTurnsEqual, type ConversationTurn } from "./conversationTurns";

/** Delay between the three dots of the "starting" indicator, so they pulse in turn. */
const startingDotDelaysMilliseconds = [0, 150, 300] as const;

function StartingIndicator() {
  const { t } = useTranslation("chat");
  return (
    <div role="status" className="flex items-center gap-2 text-body-sm text-muted">
      <span aria-hidden="true" className="inline-flex gap-1">
        {startingDotDelaysMilliseconds.map((delay) => (
          <span key={delay} style={{ animationDelay: `${delay}ms` }} className="size-1.5 animate-typing-dot rounded-full bg-neutral-fill" />
        ))}
      </span>
      {t("trace.starting")}
    </div>
  );
}

export interface ConversationTurnViewProps {
  turn: ConversationTurn;
  isCompact: boolean;
  /** This turn's answer is the newest one: follow-up questions and "Try again" apply to it only. */
  isLatest: boolean;
  isBusy: boolean;
  onSelectEvidence?: (evidenceCode: string) => void;
  onSelectRunbook?: (runbookId: string) => void;
  onAsk: (messageText: string) => void;
}

/** Same turn, same flags, same callbacks: nothing to redraw. The turn itself is compared by content (see `areConversationTurnsEqual`). */
function areTurnViewPropsEqual(previous: ConversationTurnViewProps, next: ConversationTurnViewProps): boolean {
  return (
    areConversationTurnsEqual(previous.turn, next.turn) &&
    previous.isCompact === next.isCompact &&
    previous.isLatest === next.isLatest &&
    // Only the newest turn offers follow-ups and "Try again", so only it cares whether another answer is running.
    (!next.isLatest || previous.isBusy === next.isBusy) &&
    previous.onSelectEvidence === next.onSelectEvidence &&
    previous.onSelectRunbook === next.onSelectRunbook &&
    previous.onAsk === next.onAsk
  );
}

/**
 * One question with Keigan's side: the live run, the stored run, an answer from before runs existed, or the "starting" indicator. Memoised so a
 * stream event redraws only the turn it belongs to: the answers above it keep their parsed Markdown, their open cards and the focus on their chips.
 */
export const ConversationTurnView = memo(function ConversationTurnView({ turn, isCompact, isLatest, isBusy, onSelectEvidence, onSelectRunbook, onAsk }: ConversationTurnViewProps) {
  const { liveRun, storedAnswerRunId, earlierAnswer, isStarting, question } = turn;
  const questionText = question?.messageText;
  const retry = useCallback(() => {
    if (questionText !== undefined) {
      onAsk(questionText);
    }
  }, [onAsk, questionText]);
  const sharedProps = {
    isCompact,
    onSelectEvidence,
    onSelectRunbook,
    onAskFollowUp: onAsk,
    areFollowUpsDisabled: isBusy || !isLatest,
    onRetry: isLatest && questionText !== undefined ? retry : undefined,
  };
  return (
    <>
      {question ? <ChatMessageView role="user" text={question.messageText} /> : null}
      {liveRun ? (
        <AssistantRun progress={liveRun.progress} streamingText={liveRun.streamingText?.text ?? null} toolProgress={liveRun.toolProgress} connection={liveRun.connection} {...sharedProps} />
      ) : storedAnswerRunId ? (
        <StoredAssistantRun answerRunId={storedAnswerRunId} {...sharedProps} />
      ) : earlierAnswer ? (
        <ChatMessageView role="assistant" text={earlierAnswer.messageText} payload={earlierAnswer.messagePayload} isCompact={isCompact} />
      ) : isStarting ? (
        <StartingIndicator />
      ) : null}
    </>
  );
}, areTurnViewPropsEqual);
