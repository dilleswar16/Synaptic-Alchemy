import { useMemo, useState } from "react";
import { List, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router";
import { useConversation, useConversations, useCreateConversation } from "@/api/chatApi";
import { useApplicationScope } from "@/auth/applicationScope";
import { AskKeiganConversation, askKeiganTranslationNamespaces } from "@/components/chat";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { ChatEmptyState } from "../components/ChatEmptyState";
import { ConversationDialogs, type RenameTarget } from "../components/ConversationDialogs";
import { ConversationHeader } from "../components/ConversationHeader";
import { ConversationList } from "../components/ConversationList";
import { conversationKeyFor, type NewChatSession } from "../conversationKey";
import { useChatPrompts } from "../hooks/useChatPrompts";
import { readHomeQuestion } from "../homeQuestion";

/** From this width (Tailwind `lg`) the conversation list is a column beside the conversation; below it the list opens in a drawer from the header. */
const sideColumnMediaQuery = "(min-width: 75rem)";
/** The header buttons are 44 px high on a phone or any touch screen (spec 8.8). */
const touchTargetClassName = "max-sm:h-11 pointer-coarse:h-11";

/**
 * Keigan AI chat on Ask Keigan (spec 23, doc 04 §6.8): the conversation list, and the conversation with the live trace of each answer. A new chat has no
 * conversation until the first question: it is created with that question and the address changes to it, while the component that asked keeps its answer.
 */
export default function KeiganChatPage() {
  const { t } = useTranslation(askKeiganTranslationNamespaces); // the chat's namespaces load with the page, not in the middle of the first answer
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const scope = useApplicationScope();
  const conversations = useConversations();
  const conversation = useConversation(conversationId);
  const createConversation = useCreateConversation();
  const prompts = useChatPrompts();
  const hasSideColumn = useMediaQuery(sideColumnMediaQuery);
  const [isListOpen, setIsListOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<RenameTarget | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  // `serial` makes every "new chat" a fresh conversation component; the one that started `startedConversationId` keeps its live answer while the address changes to that conversation.
  const [newChat, setNewChat] = useState<NewChatSession>({ serial: 0, startedConversationId: null });

  const startNewChat = () => {
    setNewChat((previous) => ({ serial: previous.serial + 1, startedConversationId: null }));
    navigate("/chat");
  };
  const openConversation = (identifier: string) => {
    setIsListOpen(false);
    navigate(`/chat/${identifier}`);
  };
  const startConversation = async () => {
    const created = await createConversation.mutateAsync(scope.applicationIds);
    setNewChat((previous) => ({ ...previous, startedConversationId: created.conversationId }));
    navigate(`/chat/${created.conversationId}`, { replace: true });
    return created.conversationId;
  };

  const applicationIds = conversationId ? conversation.data?.applicationIds : scope.applicationIds;
  const applicationNames = useMemo(() => {
    const names = new Map(scope.availableApplications.map((application) => [application.applicationId, application.applicationName]));
    return applicationIds?.map((identifier) => names.get(identifier) ?? identifier) ?? null;
  }, [applicationIds, scope.availableApplications]);

  const renderList = (isTouch: boolean) => (
    <ConversationList
      isTouch={isTouch}
      conversations={conversations}
      activeConversationId={conversationId}
      onOpen={openConversation}
      onRename={(item) => { setIsListOpen(false); setRenameTarget({ id: item.conversationId, title: item.conversationTitle }); }}
      onDelete={(identifier) => { setIsListOpen(false); setDeleteTargetId(identifier); }}
    />
  );

  return (
    <div className="flex h-[calc(100vh-7rem)] min-h-[32rem] flex-col gap-4">
      <PageHeader
        title={t("pageTitle")} description={t("pageDescription")}
        actions={
          <>
            {hasSideColumn ? null : <Button variant="secondary" leadingIcon={List} onClick={() => setIsListOpen(true)} className={touchTargetClassName}>{t("list.title")}</Button>}
            <Button variant="secondary" leadingIcon={MessageSquarePlus} onClick={startNewChat} className={touchTargetClassName}>{t("list.newChat")}</Button>
          </>
        }
      />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        {hasSideColumn ? <aside className="flex min-h-0 flex-col gap-3 rounded-lg border border-hairline bg-surface p-3" aria-label={t("list.title")}>{renderList(false)}</aside> : null}

        <section className="flex min-h-0 flex-col rounded-lg border border-hairline bg-surface" aria-label={t("conversation.title")}>
          {conversationId && conversation.isError ? (
            <div className="p-6"><ErrorState error={conversation.error} onRetry={() => void conversation.refetch()} /></div>
          ) : (
            <>
              <ConversationHeader title={conversation.data?.conversationTitle ?? null} applicationNames={applicationNames} />
              <AskKeiganConversation
                key={conversationKeyFor(conversationId, newChat)}
                {...(conversationId === undefined ? { conversationId: null, startConversation } : { conversationId })}
                renderEmptyState={(ask) => <ChatEmptyState prompts={prompts} onAsk={ask} />}
                initialQuestion={conversationId === undefined ? readHomeQuestion(location.state) : undefined}
              />
            </>
          )}
        </section>
      </div>

      <Drawer open={isListOpen && !hasSideColumn} onOpenChange={setIsListOpen} title={t("list.title")} size="sm">
        <div className="flex h-full flex-col gap-3">{renderList(true)}</div>
      </Drawer>
      <ConversationDialogs
        renameTarget={renameTarget} onRenameTargetChange={setRenameTarget} deleteTargetId={deleteTargetId} onDeleteTargetChange={setDeleteTargetId}
        onRenamed={(identifier) => identifier === conversationId && void conversation.refetch()}
        onDeleted={(identifier) => identifier === conversationId && startNewChat()}
      />
    </div>
  );
}
