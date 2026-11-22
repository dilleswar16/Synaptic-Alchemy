import { useCallback, useMemo, type KeyboardEvent } from "react";
import { ArrowDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { chatQueryKeys, useConversation } from "@/api/chatApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/utils/cn";
import { toolsUnsupportedErrorCode } from "./answerFailure";
import { describeAnswerFailure, failureActionFor, failureActionLabelKeys } from "./answerFailureMessage";
import { chatPillClassName } from "./chatPill";
import { ChatComposer } from "./ChatComposer";
import { buildConversationTurns } from "./conversationTurns";
import { ConversationTurnView } from "./ConversationTurnView";
import { describeRunAnnouncement, LiveAnnouncer } from "./LiveAnnouncer";
import { ToolDetailsSwitch } from "./ToolDetailsSwitch";
import { transcriptActivityKey } from "./transcriptActivity";
import { useAnswerStream } from "./useAnswerStream";
import { useTranscriptScroll } from "./useTranscriptScroll";

/**
 * Every translation namespace the conversation and its cards use. A namespace loads the first time a component asks for it and the page is replaced by its
 * loading fallback meanwhile, which stops a stream in progress (the hook aborts it when it is hidden). Asking for all of them before the conversation mounts
 * keeps that from happening in the middle of an answer; a screen that mounts the conversation later should ask for them too, so the page does not flash.
 */
export const askKeiganTranslationNamespaces = ["chat", "onboarding"] as const;

export interface AskKeiganConversationProps {
  conversationId: string;
  /** Narrow container (the investigation panel): smaller type, no Keigan mark, stacked input lists. */
  isCompact?: boolean;
  /** Shown above the suggested prompts while the conversation is empty. */
  introText?: string;
  /** Questions offered as buttons while the conversation is empty. */
  suggestedPrompts?: readonly string[];
  composerPlaceholder?: string;
  /** An `[E#]` citation was chosen (investigation page): show that evidence. */
  onSelectEvidence?: (evidenceCode: string) => void;
  /** An `[R#]` citation was chosen (investigation page): show that runbook. */
  onSelectRunbook?: (runbookId: string) => void;
  className?: string;
}

/**
 * Ask Keigan (spec 23): the stored conversation, the answers asked in this session with their live trace, the Stop button and the
 * specific error messages. The one component both chat screens use; it fills its container, so the caller provides the frame and header.
 * It carries the "Show tool details" switch in a bar of its own on top.
 */
export function AskKeiganConversation({ conversationId, isCompact = false, introText, suggestedPrompts = [], composerPlaceholder, onSelectEvidence, onSelectRunbook, className }: AskKeiganConversationProps) {
  const { t } = useTranslation(askKeiganTranslationNamespaces);
  const queryClient = useQueryClient();
  const conversation = useConversation(conversationId);
  const { state, failure, isBusy, send, stop, performFailureAction } = useAnswerStream({
    conversationId,
    onSettled: () => queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversation(conversationId) }),
  });

  const turns = useMemo(() => buildConversationTurns(conversation.data?.messages ?? [], state.runs, state.pendingQuestion), [conversation.data?.messages, state.runs, state.pendingQuestion]);
  const activityKey = transcriptActivityKey(turns.length, state.pendingQuestion, state.runs);
  const { scrollReference, onScroll, hasNewActivity, scrollToBottom } = useTranscriptScroll(activityKey);

  const latestRun = state.runs.at(-1);
  const announcement = useMemo(() => (latestRun ? describeRunAnnouncement(latestRun.progress, t) : null), [latestRun, t]);

  // Stable, so the turns above the one being written are not redrawn for every event.
  const ask = useCallback(
    (messageText: string) => {
      scrollToBottom();
      void send(messageText);
    },
    [scrollToBottom, send],
  );
  const areToolsUnsupported = failure?.errorCode === toolsUnsupportedErrorCode;
  const failureAction = failure ? failureActionFor(failure) : null;

  // Esc anywhere in the conversation stops the answer that is running (and, being handled, does not also close a panel around it). Events that bubble up from a drawer are not ours.
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const isFromThisConversation = event.target instanceof Node && event.currentTarget.contains(event.target);
    if (event.key === "Escape" && !event.defaultPrevented && isFromThisConversation && isBusy) {
      event.preventDefault();
      void stop();
    }
  };

  return (
    <div onKeyDown={handleKeyDown} className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className={cn("flex justify-end border-b border-hairline", isCompact ? "px-4 py-2" : "px-5 py-2")}>
        <ToolDetailsSwitch />
      </div>
      <div className="relative flex min-h-0 flex-1 flex-col">
        {/* Streaming text must not be read token by token: the transcript is not live, the announcer below speaks the milestones. */}
        <div ref={scrollReference} onScroll={onScroll} role="log" aria-live="off" className={cn("flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto", isCompact ? "px-4 py-4" : "px-5 py-5")}>
          {conversation.isLoading ? <Spinner className="m-auto" /> : null}
          {conversation.isError ? <ErrorState size="sm" error={conversation.error} onRetry={() => void conversation.refetch()} isRetrying={conversation.isFetching} /> : null}
          {conversation.isSuccess && turns.length === 0 ? (
            <div className="flex flex-col gap-3">
              {introText ? <p className="text-body-sm text-muted">{introText}</p> : null}
              <div className="flex flex-col items-start gap-2">
                {suggestedPrompts.map((promptText) => (
                  <button key={promptText} type="button" onClick={() => ask(promptText)} className={chatPillClassName}>
                    {promptText}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {turns.map((turn, turnIndex) => (
            <ConversationTurnView key={turn.key} turn={turn} isCompact={isCompact} isLatest={turnIndex === turns.length - 1} isBusy={isBusy} onSelectEvidence={onSelectEvidence} onSelectRunbook={onSelectRunbook} onAsk={ask} />
          ))}
        </div>
        {hasNewActivity ? (
          <Button variant="secondary" size="sm" leadingIcon={ArrowDown} onClick={scrollToBottom} className="absolute bottom-3 left-1/2 -translate-x-1/2 shadow-md">
            {t("trace.newActivity")}
          </Button>
        ) : null}
      </div>

      <LiveAnnouncer announcement={announcement} />

      <div className={cn("flex flex-col gap-2 border-t border-hairline", isCompact ? "p-3" : "p-4")}>
        {failure ? (
          <Banner
            tone="danger"
            action={failureAction ? <Button variant="secondary" size="sm" onClick={() => void performFailureAction(failureAction)}>{t(failureActionLabelKeys[failureAction.kind])}</Button> : undefined}
          >
            {describeAnswerFailure(failure, t)}
            {failure.correlationId ? <span className="mt-1 block font-mono text-caption text-muted">{t("answer.reference", { correlationId: failure.correlationId })}</span> : null}
          </Banner>
        ) : null}
        <ChatComposer onSend={ask} isSending={isBusy} onStop={() => void stop()} isDisabled={areToolsUnsupported} placeholder={composerPlaceholder} />
        <p className="text-caption text-muted">{t("composer.hint")}</p>
      </div>
    </div>
  );
}
