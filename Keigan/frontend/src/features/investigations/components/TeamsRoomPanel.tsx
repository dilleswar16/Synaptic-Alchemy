import { useEffect, useRef, useState } from "react";
import { ExternalLink, MessagesSquare, Send, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePostTeamsChatMessage, useTeamsChat, type TeamsChatMessage } from "@/api/notificationsApi";
import { isApiError } from "@/api/httpClient";
import { Avatar } from "@/components/ui/Avatar";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/utils/cn";

interface CardBlock {
  type?: string;
  text?: string;
  facts?: Array<{ title: string; value: string }>;
}
interface CardAction {
  title?: string;
  url?: string;
}

/** Minimal Adaptive Card renderer for the cards Keigan posts (TextBlock, FactSet and OpenUrl actions). */
function AdaptiveCardView({ card }: { card: Record<string, unknown> }) {
  const blocks = (card.body as CardBlock[] | undefined) ?? [];
  const actions = (card.actions as CardAction[] | undefined) ?? [];
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-md border border-border bg-surface p-3">
      {blocks.map((block, index) =>
        block.type === "FactSet" ? (
          <dl key={index} className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body-sm">
            {(block.facts ?? []).map((fact) => (
              <div key={fact.title} className="contents">
                <dt className="text-muted">{fact.title}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p key={index} className={cn("text-body-sm", index === 0 ? "font-semibold text-brand" : "")}>{block.text}</p>
        ),
      )}
      {actions.length > 0 ? (
        <div className="flex gap-2">
          {actions.map((action) =>
            action.url ? (
              <a key={action.url} href={action.url} className="text-body-sm font-semibold text-action underline" target="_blank" rel="noreferrer">{action.title}</a>
            ) : null,
          )}
        </div>
      ) : null}
    </div>
  );
}

function MessageRow({ message }: { message: TeamsChatMessage }) {
  const { t } = useTranslation("notifications");
  const isBot = message.authorRole === "assistant";
  const name = isBot ? t("room.bot") : message.authorDisplayName ?? "?";
  return (
    <li className={cn("flex gap-3", isBot ? "rounded-md border-l-2 border-ai bg-ai-soft/40 p-3" : "px-1")}>
      {isBot ? (
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-ai-fill text-white" aria-hidden="true"><Sparkles className="size-4" /></span>
      ) : (
        <Avatar name={name} />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-body-sm font-semibold">{name}</span>
          {isBot ? <StatusChip size="sm" tone="ai" icon={false}>{t("room.botBadge")}</StatusChip> : null}
          <RelativeTime value={message.createdAt} className="text-caption text-muted" />
        </div>
        {message.adaptiveCard ? <AdaptiveCardView card={message.adaptiveCard} /> : <MarkdownView content={message.messageText} />}
      </div>
    </li>
  );
}

/** Teams-like mirror of the incident chat: participants, Keigan bot messages and cards, captured chat facts and (simulated mode only) a composer. */
export function TeamsRoomPanel({ incidentId }: { incidentId: string }) {
  const { t } = useTranslation("notifications");
  const { showToast } = useToast();
  const chatQuery = useTeamsChat(incidentId);
  const postMessage = usePostTeamsChatMessage(incidentId);
  const [draft, setDraft] = useState("");
  const endReference = useRef<HTMLDivElement>(null);
  const messageCount = chatQuery.data?.messages.length ?? 0;

  useEffect(() => {
    endReference.current?.scrollIntoView({ block: "end" });
  }, [messageCount]);

  if (chatQuery.isLoading) return <Skeleton className="h-72 w-full" />;
  if (chatQuery.isError) return <ErrorState error={chatQuery.error} onRetry={() => chatQuery.refetch()} />;
  const chat = chatQuery.data;
  if (!chat || !chat.chatExists) return <EmptyState isBordered icon={MessagesSquare} title={t("room.title")} description={t("room.empty")} />;

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    postMessage.mutate(text, {
      onSuccess: () => setDraft(""),
      onError: (error) => showToast({ tone: "danger", title: t("room.sendFailed"), description: isApiError(error) ? error.detail ?? error.title : undefined }),
    });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col gap-4">
        <Banner tone={chat.isSimulated ? "info" : "success"} action={chat.chatWebUrl ? <Button asChild variant="ghost" size="sm" trailingIcon={ExternalLink}><a href={chat.chatWebUrl} target="_blank" rel="noreferrer">{t("room.openInTeams")}</a></Button> : undefined}>
          {chat.isSimulated ? t("room.simulatedBanner") : t("room.liveBanner")}
        </Banner>
        <Card>
          <CardHeader title={chat.chatTopic ?? t("room.title")} icon={MessagesSquare} actions={chat.chatStatus === "closed" ? <StatusChip size="sm" tone="neutral" icon={false}>{t("room.closed")}</StatusChip> : undefined} />
          <CardBody>
            <ul className="flex max-h-[28rem] flex-col gap-4 overflow-y-auto" aria-live="polite">
              {chat.messages.map((message) => <MessageRow key={message.messageId} message={message} />)}
              <div ref={endReference} />
            </ul>
            {chat.canPost ? (
              <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4">
                <Textarea
                  aria-label={t("room.composerLabel")}
                  placeholder={t("room.composerPlaceholder")}
                  value={draft}
                  rows={2}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      send();
                    }
                  }}
                />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-caption text-muted">
                    <span>{t("room.hintsTitle")}</span>
                    {[t("room.hintAsk"), t("room.hintFinish")].map((hint) => (
                      <button key={hint} type="button" className="rounded-full bg-neutral-soft px-2 py-0.5 hover:bg-ai-soft" onClick={() => setDraft(hint)}>{hint}</button>
                    ))}
                  </div>
                  <Button leadingIcon={Send} isLoading={postMessage.isPending} disabled={!draft.trim()} onClick={send}>{t("room.send")}</Button>
                </div>
              </div>
            ) : null}
          </CardBody>
        </Card>
      </div>
      <aside className="flex flex-col gap-4">
        <Card dense>
          <CardHeader title={t("room.participants")} />
          <CardBody>
            <ul className="flex flex-col gap-2">
              {chat.participants.map((participant) => (
                <li key={`${participant.role}-${participant.userPrincipalName ?? participant.displayName}`} className="flex items-center gap-2 text-body-sm">
                  <Avatar name={participant.displayName} size="sm" />
                  <span className="truncate">{participant.displayName}</span>
                  {participant.role === "bot" ? <StatusChip size="sm" tone="ai" icon={false}>{t("room.botBadge")}</StatusChip> : null}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card dense>
          <CardHeader title={t("room.facts")} />
          <CardBody>
            {chat.facts.length === 0 ? (
              <p className="text-body-sm text-muted">{t("room.noFacts")}</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {chat.facts.map((fact) => (
                  <li key={fact.timelineEventId} className="text-body-sm">
                    <p>{fact.eventTitle}</p>
                    <RelativeTime value={fact.eventOccurredAt} className="text-caption text-muted" />
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </aside>
    </div>
  );
}

export default TeamsRoomPanel;
