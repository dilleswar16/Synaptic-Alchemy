import { useEffect, useRef, useState, type FormEvent } from "react";
import { Maximize2, Minimize2, SendHorizontal, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { apiPost, isApiError } from "@/api/httpClient";
import { ChatMessageView } from "@/components/chat";
import type { ChatMessagePayload } from "@/api/chatApi";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Spinner } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import { cn } from "@/utils/cn";

interface ConversationResponse {
  conversationId?: string;
  id?: string;
}

interface AssistantMessageResponse {
  messageText: string;
  messagePayload?: unknown;
}

interface ChatEntry {
  key: number;
  role: "user" | "assistant" | "error";
  text: string;
  payload?: ChatMessagePayload | null;
}

const suggestedPromptKeys = ["whyNotDatabase", "whatChanged", "executiveUpdate", "explainNewEngineer"] as const;

/** Floating investigation chat: 420 px, expandable to half the screen. Grounded in this investigation by the chat backend. */
export function InvestigationChatPanel({ investigationId }: { investigationId: string }) {
  const { t } = useTranslation("investigations");
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const conversationIdReference = useRef<string | null>(null);
  const entryCounter = useRef(0);
  const scrollReference = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollReference.current?.scrollTo({ top: scrollReference.current.scrollHeight, behavior: "smooth" });
  }, [entries, isSending]);

  const append = (role: ChatEntry["role"], text: string, payload?: ChatMessagePayload | null) => {
    entryCounter.current += 1;
    setEntries((previous) => [...previous, { key: entryCounter.current, role, text, payload }]);
  };

  const sendMessage = async (messageText: string) => {
    const trimmed = messageText.trim();
    if (!trimmed || isSending) return;
    append("user", trimmed);
    setDraft("");
    setIsSending(true);
    try {
      if (!conversationIdReference.current) {
        const conversation = await apiPost<ConversationResponse, { conversationScope: string; investigationId: string }>("/chat/conversations", { conversationScope: "investigation", investigationId });
        conversationIdReference.current = conversation.conversationId ?? conversation.id ?? null;
      }
      const reply = await apiPost<AssistantMessageResponse, { messageText: string }>(`/chat/conversations/${conversationIdReference.current}/messages`, { messageText: trimmed });
      append("assistant", reply.messageText, reply.messagePayload as ChatMessagePayload | null | undefined);
    } catch (error) {
      append("error", isApiError(error) && error.status !== 404 ? (error.detail ?? error.title) : t("chat.unavailable"));
    } finally {
      setIsSending(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void sendMessage(draft);
  };

  if (!isOpen) {
    return (
      <div className="fixed right-6 bottom-6 z-40 print:hidden">
        <Button variant="gradient-outline" size="lg" leadingIcon={Sparkles} onClick={() => setIsOpen(true)} className="rounded-full shadow-lg">{t("chat.open")}</Button>
      </div>
    );
  }
  return (
    <aside
      aria-label={t("chat.title")}
      className={cn("fixed right-4 bottom-4 z-40 flex h-[min(42rem,calc(100vh-2rem))] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-hairline bg-surface-raised shadow-xl print:hidden", isExpanded ? "w-[50vw] min-w-[420px]" : "w-[420px]")}
    >
      <header className="flex items-center justify-between gap-2 border-b border-hairline px-4 py-3">
        <div className="flex min-w-0 flex-col">
          <h2 className="text-body font-semibold text-default">{t("chat.title")}</h2>
          <p className="text-caption text-muted">{t("chat.subtitle")}</p>
        </div>
        <div className="flex items-center gap-1">
          <IconButton icon={isExpanded ? Minimize2 : Maximize2} label={isExpanded ? t("chat.shrink") : t("chat.expand")} variant="ghost" size="sm" onClick={() => setIsExpanded((value) => !value)} />
          <IconButton icon={X} label={t("chat.close")} variant="ghost" size="sm" onClick={() => setIsOpen(false)} />
        </div>
      </header>
      <div ref={scrollReference} className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4" role="log" aria-live="polite">
        {entries.length === 0 ? (
          <div className="flex flex-col gap-3">
            <p className="text-body-sm text-muted">{t("chat.intro")}</p>
            <div className="flex flex-col items-start gap-2">
              {suggestedPromptKeys.map((promptKey) => (
                <button key={promptKey} type="button" onClick={() => void sendMessage(t(`chat.prompts.${promptKey}`))} className="rounded-full border border-strong bg-surface px-3 py-1.5 text-left text-body-sm text-default hover:bg-surface-hover">
                  {t(`chat.prompts.${promptKey}`)}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {entries.map((entry) =>
          entry.role === "user" ? (
            <div key={entry.key} className="ml-8 self-end rounded-lg rounded-br-xs bg-action-subtle px-3 py-2 text-body-sm text-action-subtle-text">{entry.text}</div>
          ) : entry.role === "error" ? (
            <div key={entry.key} className="rounded-lg border border-hairline bg-danger-soft px-3 py-2 text-body-sm text-danger" role="alert">{entry.text}</div>
          ) : (
            <ChatMessageView key={entry.key} role="assistant" text={entry.text} payload={entry.payload} isCompact className="mr-4" />
          ),
        )}
        {isSending ? <div className="flex items-center gap-2 text-body-sm text-muted"><Spinner size="sm" />{t("chat.thinking")}</div> : null}
      </div>
      <form onSubmit={onSubmit} className="flex items-end gap-2 border-t border-hairline p-3">
        <Textarea
          aria-label={t("chat.inputLabel")}
          placeholder={t("chat.placeholder")}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { // Enter that confirms an IME conversion (Japanese, Chinese) must not send
              event.preventDefault();
              void sendMessage(draft);
            }
          }}
          rows={1}
          autoResize
          maximumRows={5}
          containerClassName="flex-1"
        />
        <IconButton icon={SendHorizontal} label={t("chat.send")} variant="primary" type="submit" disabled={!draft.trim() || isSending} />
      </form>
    </aside>
  );
}
