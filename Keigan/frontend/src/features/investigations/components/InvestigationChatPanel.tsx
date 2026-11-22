import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Maximize2, Minimize2, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useInvestigationConversation } from "@/api/chatApi";
import { AskKeiganConversation, askKeiganTranslationNamespaces } from "@/components/chat";
import { useFocusTrap } from "@/hooks/useFocusTrap";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { Spinner } from "@/components/ui/Spinner";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/utils/cn";

/** The panel's buttons are 32 px; on a phone or any touch screen they grow to 44 px (spec 8.8). */
const touchTargetClassName = "max-sm:size-11 pointer-coarse:size-11";
const suggestedPromptKeys = ["whyNotDatabase", "whatChanged", "executiveUpdate", "explainNewEngineer"] as const;
/** Below Tailwind's `sm` breakpoint (40rem) the panel is a full-screen sheet: a dialog that traps focus and hides the page behind it. */
const phoneMediaQuery = "(max-width: 39.99rem)";

export interface InvestigationChatPanelProps {
  investigationId: string;
  /** An `[E#]` citation in an answer was chosen: show that evidence on the page. */
  onSelectEvidence: (evidenceCode: string) => void;
  /** An `[R#]` citation in an answer was chosen: show that runbook on the page. */
  onSelectRunbook: (runbookId: string) => void;
}

/**
 * Floating investigation chat: 420 px, expandable to half the screen, full screen on a phone. Ask Keigan answers from this investigation's own tools.
 * Keyboard: opening moves focus into the panel and closing returns it to the launcher; Esc stops the answer while one runs (handled in the conversation)
 * and otherwise closes the panel. On a phone the panel is a modal dialog with Tab kept inside it, and choosing a citation closes it so the page it points to is seen.
 */
export function InvestigationChatPanel({ investigationId, onSelectEvidence, onSelectRunbook }: InvestigationChatPanelProps) {
  const { t } = useTranslation(["investigations", ...askKeiganTranslationNamespaces]); // the chat's namespaces load with the page, not in the middle of the first answer
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const conversation = useInvestigationConversation(investigationId, isOpen);
  const isPhone = useMediaQuery(phoneMediaQuery);
  const panelReference = useRef<HTMLDivElement>(null);
  const launcherReference = useRef<HTMLButtonElement>(null);
  const wasOpenReference = useRef(false);
  useFocusTrap(panelReference, isOpen && isPhone);

  useEffect(() => {
    if (isOpen) {
      panelReference.current?.focus();
    } else if (wasOpenReference.current) {
      launcherReference.current?.focus();
    }
    wasOpenReference.current = isOpen;
  }, [isOpen]);

  const closeOnEscape = (event: KeyboardEvent<HTMLElement>) => {
    // A key that bubbles up from a drawer opened inside the panel, or that the conversation already used to stop an answer, is not ours.
    const isFromThisPanel = event.target instanceof Node && event.currentTarget.contains(event.target);
    if (event.key === "Escape" && !event.defaultPrevented && isFromThisPanel) {
      event.preventDefault();
      setIsOpen(false);
    }
  };
  const showOnPage = (show: () => void) => {
    show();
    if (isPhone) {
      setIsOpen(false);
    }
  };

  if (!isOpen) {
    return (
      <div className="fixed right-6 bottom-6 z-40 print:hidden">
        <Button ref={launcherReference} variant="gradient-outline" size="lg" leadingIcon={Sparkles} onClick={() => setIsOpen(true)} className="rounded-full shadow-lg">{t("chat.open")}</Button>
      </div>
    );
  }
  return (
    <div
      ref={panelReference}
      role={isPhone ? "dialog" : "complementary"}
      aria-modal={isPhone ? true : undefined}
      aria-label={t("chat.title")}
      tabIndex={-1}
      onKeyDown={closeOnEscape}
      className={cn(
        "fixed inset-0 z-40 flex flex-col overflow-hidden border-hairline bg-surface-raised outline-none print:hidden",
        "sm:inset-auto sm:right-4 sm:bottom-4 sm:h-[min(42rem,calc(100vh-2rem))] sm:max-w-[calc(100vw-2rem)] sm:rounded-xl sm:border sm:shadow-xl",
        isExpanded ? "sm:w-[50vw] sm:min-w-[420px]" : "sm:w-[420px]",
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-hairline px-4 py-3">
        <div className="flex min-w-0 flex-col">
          <h2 className="text-body font-semibold text-default">{t("chat.title")}</h2>
          <p className="text-caption text-muted">{t("chat.subtitle")}</p>
        </div>
        <div className="flex items-center gap-1">
          <IconButton icon={isExpanded ? Minimize2 : Maximize2} label={isExpanded ? t("chat.shrink") : t("chat.expand")} variant="ghost" size="sm" onClick={() => setIsExpanded((value) => !value)} className={cn("max-sm:hidden", touchTargetClassName)} />
          <IconButton icon={X} label={t("chat.close")} variant="ghost" size="sm" onClick={() => setIsOpen(false)} className={touchTargetClassName} />
        </div>
      </header>
      {conversation.isLoading ? <Spinner className="m-auto" /> : null}
      {conversation.isError ? <div className="p-4"><ErrorState size="sm" error={conversation.error} onRetry={() => void conversation.refetch()} isRetrying={conversation.isFetching} /></div> : null}
      {conversation.data ? (
        <AskKeiganConversation
          conversationId={conversation.data.conversationId}
          isCompact
          introText={t("chat.intro")}
          suggestedPrompts={suggestedPromptKeys.map((promptKey) => t(`chat.prompts.${promptKey}`))}
          composerPlaceholder={t("chat.placeholder")}
          onSelectEvidence={(evidenceCode) => showOnPage(() => onSelectEvidence(evidenceCode))}
          onSelectRunbook={(runbookId) => showOnPage(() => onSelectRunbook(runbookId))}
        />
      ) : null}
    </div>
  );
}
