import { useMemo, useState } from "react";
import { MoreHorizontal, Pencil, Search, Trash2 } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { Conversation } from "@/api/chatApi";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/utils/cn";

/** A phone's buttons are 44 px (spec 8.8); the list's 32 px menu button grows to match. */
const touchTargetClassName = "size-11";

export interface ConversationListProps {
  conversations: UseQueryResult<Conversation[]>;
  activeConversationId: string | undefined;
  onOpen: (conversationId: string) => void;
  onRename: (conversation: Conversation) => void;
  onDelete: (conversationId: string) => void;
  /** Touch-sized targets (44 px): the list is in the phone drawer. */
  isTouch?: boolean;
}

/** The person's conversations with a search box, newest first as the server sends them; each has a rename and a delete action. Used in the page's side column and in its phone drawer. */
export function ConversationList({ conversations, activeConversationId, onOpen, onRename, onDelete, isTouch = false }: ConversationListProps) {
  const { t } = useTranslation("chat");
  const [searchText, setSearchText] = useState("");
  const visibleConversations = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    return (conversations.data ?? []).filter((item) => !needle || item.conversationTitle.toLowerCase().includes(needle));
  }, [conversations.data, searchText]);

  return (
    <>
      <Input aria-label={t("list.search")} placeholder={t("list.search")} leadingIcon={Search} value={searchText} onChange={(event) => setSearchText(event.target.value)} size={isTouch ? "md" : "sm"} />
      <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {conversations.isLoading ? <><Skeleton className="h-12" /><Skeleton className="h-12" /><Skeleton className="h-12" /></> : null}
        {conversations.isError ? <ErrorState size="sm" error={conversations.error} onRetry={() => void conversations.refetch()} /> : null}
        {!conversations.isLoading && !conversations.isError && visibleConversations.length === 0 ? <p className="px-2 py-4 text-body-sm text-muted">{searchText ? t("list.noMatches") : t("list.empty")}</p> : null}
        {visibleConversations.map((item) => (
          <div key={item.conversationId} className={cn("group flex items-center gap-1 rounded-md pr-1 hover:bg-surface-hover", item.conversationId === activeConversationId && "bg-action-subtle")}>
            <button type="button" onClick={() => onOpen(item.conversationId)} aria-current={item.conversationId === activeConversationId ? "page" : undefined} className="flex min-w-0 flex-1 flex-col items-start px-2.5 py-2 text-left">
              <span className="w-full truncate text-body-sm font-medium text-default">{item.conversationTitle}</span>
              <span className="text-caption text-muted"><RelativeTime value={item.updatedAt} /></span>
            </button>
            <DropdownMenu
              trigger={<IconButton icon={MoreHorizontal} label={t("list.actions")} variant="ghost" size="sm" className={isTouch ? touchTargetClassName : undefined} />}
              entries={[
                { key: "rename", label: t("list.rename"), icon: Pencil, onSelect: () => onRename(item) },
                { key: "delete", label: t("list.delete"), icon: Trash2, tone: "danger", onSelect: () => onDelete(item.conversationId) },
              ]}
            />
          </div>
        ))}
      </div>
    </>
  );
}
