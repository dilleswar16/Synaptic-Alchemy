import { useEffect, useMemo, useRef, useState } from "react";
import { MessageSquarePlus, MoreHorizontal, Pencil, Search, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router";
import { chatQueryKeys, sendChatMessage, useConversation, useConversations, useCreateConversation, useDeleteConversation, useRenameConversation, useSuggestedPrompts, type ChatMessage, type ClarificationOption } from "@/api/chatApi";
import { isApiError } from "@/api/httpClient";
import { useApplicationScope } from "@/auth/applicationScope";
import { ChatComposer, ChatMessageView } from "@/components/chat";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/utils/cn";

/** Keigan AI chat: conversation list on the left, the conversation on the right (doc 04 §6.8). */
export default function KeiganChatPage() {
  const { t } = useTranslation("chat");
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const scope = useApplicationScope();
  const conversations = useConversations();
  const conversation = useConversation(conversationId);
  const createConversation = useCreateConversation();
  const renameConversation = useRenameConversation();
  const deleteConversation = useDeleteConversation();
  const suggestedPrompts = useSuggestedPrompts(scope.applicationIds[0] ?? null);
  const [searchText, setSearchText] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const scrollReference = useRef<HTMLDivElement>(null);

  const messages: ChatMessage[] = conversation.data?.messages ?? [];
  useEffect(() => {
    scrollReference.current?.scrollTo({ top: scrollReference.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, pendingQuestion]);

  const visibleConversations = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    return (conversations.data ?? []).filter((item) => !needle || item.conversationTitle.toLowerCase().includes(needle));
  }, [conversations.data, searchText]);

  const applicationNames = useMemo(() => {
    const names = new Map(scope.availableApplications.map((application) => [application.applicationId, application.applicationName]));
    return (conversation.data?.applicationIds ?? []).map((identifier) => names.get(identifier) ?? identifier);
  }, [conversation.data?.applicationIds, scope.availableApplications]);

  const submit = async (messageText: string, clarificationValue?: string) => {
    if (pendingQuestion) return;
    setSendError(null);
    setPendingQuestion(messageText);
    try {
      let targetId = conversationId;
      if (!targetId) {
        targetId = (await createConversation.mutateAsync(scope.applicationIds)).conversationId;
      }
      await sendChatMessage(targetId, { messageText, clarificationResponse: clarificationValue });
      await Promise.all([queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversation(targetId) }), queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations })]);
      if (!conversationId) navigate(`/chat/${targetId}`, { replace: true });
    } catch (error) {
      setSendError(isApiError(error) ? (error.status === 429 ? t("errors.rateLimited") : (error.detail ?? error.title)) : t("errors.generic"));
      if (conversationId) await queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversation(conversationId) });
    } finally {
      setPendingQuestion(null);
    }
  };

  const location = useLocation();
  const hasAutoAsked = useRef(false);
  useEffect(() => {
    const homeQuestion = (location.state as { question?: string } | null)?.question;
    if (homeQuestion && !conversationId && !hasAutoAsked.current) {
      hasAutoAsked.current = true;
      void submit(homeQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the first render may auto-send the question from Home
  }, []);

  const startNewChat = () => navigate("/chat");
  const onClarificationSelect = (option: ClarificationOption) => void submit(option.label, option.value);
  const isEmptyConversation = !pendingQuestion && messages.length === 0;
  const lastMessageId = messages[messages.length - 1]?.messageId;

  return (
    <div className="flex h-[calc(100vh-7rem)] min-h-[32rem] flex-col gap-4">
      <PageHeader title={t("pageTitle")} description={t("pageDescription")} actions={<Button variant="secondary" leadingIcon={MessageSquarePlus} onClick={startNewChat}>{t("list.newChat")}</Button>} />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        <aside className="flex min-h-0 flex-col gap-3 rounded-lg border border-hairline bg-surface p-3" aria-label={t("list.title")}>
          <Input aria-label={t("list.search")} placeholder={t("list.search")} leadingIcon={Search} value={searchText} onChange={(event) => setSearchText(event.target.value)} size="sm" />
          <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
            {conversations.isLoading ? <><Skeleton className="h-12" /><Skeleton className="h-12" /><Skeleton className="h-12" /></> : null}
            {conversations.isError ? <ErrorState size="sm" error={conversations.error} onRetry={() => void conversations.refetch()} /> : null}
            {!conversations.isLoading && !conversations.isError && visibleConversations.length === 0 ? <p className="px-2 py-4 text-body-sm text-muted">{searchText ? t("list.noMatches") : t("list.empty")}</p> : null}
            {visibleConversations.map((item) => (
              <div key={item.conversationId} className={cn("group flex items-center gap-1 rounded-md pr-1 hover:bg-surface-hover", item.conversationId === conversationId && "bg-action-subtle")}>
                <button type="button" onClick={() => navigate(`/chat/${item.conversationId}`)} aria-current={item.conversationId === conversationId ? "page" : undefined} className="flex min-w-0 flex-1 flex-col items-start px-2.5 py-2 text-left">
                  <span className="w-full truncate text-body-sm font-medium text-default">{item.conversationTitle}</span>
                  <span className="text-caption text-muted"><RelativeTime value={item.updatedAt} /></span>
                </button>
                <DropdownMenu
                  trigger={<IconButton icon={MoreHorizontal} label={t("list.actions")} variant="ghost" size="sm" />}
                  entries={[
                    { key: "rename", label: t("list.rename"), icon: Pencil, onSelect: () => setRenameTarget({ id: item.conversationId, title: item.conversationTitle }) },
                    { key: "delete", label: t("list.delete"), icon: Trash2, tone: "danger", onSelect: () => setDeleteTargetId(item.conversationId) },
                  ]}
                />
              </div>
            ))}
          </div>
        </aside>

        <section className="flex min-h-0 flex-col rounded-lg border border-hairline bg-surface" aria-label={t("conversation.title")}>
          {conversationId && conversation.isError ? (
            <div className="p-6"><ErrorState error={conversation.error} onRetry={() => void conversation.refetch()} /></div>
          ) : (
            <>
              <header className="flex flex-wrap items-center gap-2 border-b border-hairline px-5 py-3">
                <h2 className="mr-2 truncate text-body font-semibold text-default">{conversation.data?.conversationTitle ?? t("conversation.newTitle")}</h2>
                <span className="text-caption text-muted">{t("conversation.scope")}</span>
                {(conversationId ? applicationNames : scope.availableApplications.filter((application) => scope.applicationIds.includes(application.applicationId)).map((application) => application.applicationName)).map((name) => <Badge key={name} tone="brand">{name}</Badge>)}
                {(conversationId ? applicationNames.length : scope.applicationIds.length) === 0 ? <Badge tone="neutral">{t("conversation.allApplications")}</Badge> : null}
              </header>
              <div ref={scrollReference} className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-5 py-5" role="log" aria-live="polite">
                {conversationId && conversation.isLoading ? <Spinner /> : null}
                {isEmptyConversation && !conversation.isLoading ? (
                  <div className="m-auto flex w-full max-w-3xl flex-col items-center gap-6 text-center">
                    <KeiganLogo variant="mark" size={56} />
                    <h2 className="text-h2 font-semibold text-default">{t("empty.title")}</h2>
                    <p className="text-body text-muted">{t("empty.description")}</p>
                    <ul className="grid w-full grid-cols-1 gap-3 text-left sm:grid-cols-2 lg:grid-cols-3">
                      {(suggestedPrompts.data ?? []).map((prompt) => (
                        <li key={prompt.promptText}>
                          <button type="button" onClick={() => void submit(prompt.promptText)} className="h-full w-full rounded-lg border border-hairline bg-surface p-3 text-body-sm text-default shadow-xs transition hover:-translate-y-px hover:bg-surface-hover hover:shadow-sm">
                            <span className="mb-1 block text-caption font-medium text-muted">{t(`empty.category.${prompt.category}`)}</span>
                            {prompt.promptText}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {messages.map((message) => (
                  <ChatMessageView
                    key={message.messageId} role={message.authorRole} text={message.messageText} payload={message.messagePayload}
                    onClarificationSelect={onClarificationSelect} isClarificationDisabled={Boolean(pendingQuestion) || message.messageId !== lastMessageId}
                  />
                ))}
                {pendingQuestion ? (
                  <>
                    <ChatMessageView role="user" text={pendingQuestion} />
                    <div className="flex items-center gap-2 text-body-sm text-muted"><Spinner size="sm" />{t("conversation.thinking")}</div>
                  </>
                ) : null}
                {sendError ? <div role="alert" className="rounded-lg border border-hairline bg-danger-soft px-3 py-2 text-body-sm text-danger">{sendError}</div> : null}
              </div>
              <div className="border-t border-hairline p-4">
                <ChatComposer onSend={(text) => void submit(text)} isSending={Boolean(pendingQuestion)} />
                <p className="mt-2 text-caption text-muted">{t("composer.hint")}</p>
              </div>
            </>
          )}
        </section>
      </div>

      <Dialog open={renameTarget !== null} onOpenChange={(open) => !open && setRenameTarget(null)} title={t("list.renameTitle")} footer={
        <Button onClick={async () => { if (renameTarget) { await renameConversation.mutateAsync({ conversationId: renameTarget.id, conversationTitle: renameTarget.title }); if (renameTarget.id === conversationId) void conversation.refetch(); setRenameTarget(null); } }} isLoading={renameConversation.isPending} disabled={!renameTarget?.title.trim()}>{t("list.save")}</Button>
      }>
        <Input label={t("list.nameLabel")} value={renameTarget?.title ?? ""} onChange={(event) => setRenameTarget((previous) => (previous ? { ...previous, title: event.target.value } : previous))} maxLength={120} />
      </Dialog>
      <ConfirmDialog
        open={deleteTargetId !== null} onOpenChange={(open) => !open && setDeleteTargetId(null)} title={t("list.deleteTitle")} description={t("list.deleteDescription")} confirmLabel={t("list.delete")} tone="danger"
        onConfirm={async () => { if (deleteTargetId) { await deleteConversation.mutateAsync(deleteTargetId); if (deleteTargetId === conversationId) navigate("/chat"); setDeleteTargetId(null); } }}
      />
    </div>
  );
}
