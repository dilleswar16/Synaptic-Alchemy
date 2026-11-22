import { useTranslation } from "react-i18next";
import { useDeleteConversation, useRenameConversation } from "@/api/chatApi";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";

export interface RenameTarget {
  id: string;
  title: string;
}

export interface ConversationDialogsProps {
  renameTarget: RenameTarget | null;
  onRenameTargetChange: (target: RenameTarget | null) => void;
  deleteTargetId: string | null;
  onDeleteTargetChange: (conversationId: string | null) => void;
  /** The conversation that was renamed or deleted is shown on the page: it reads itself again, or the page leaves it. */
  onRenamed: (conversationId: string) => void;
  onDeleted: (conversationId: string) => void;
}

/** The rename dialog and the delete confirmation of a conversation of the list. */
export function ConversationDialogs({ renameTarget, onRenameTargetChange, deleteTargetId, onDeleteTargetChange, onRenamed, onDeleted }: ConversationDialogsProps) {
  const { t } = useTranslation("chat");
  const renameConversation = useRenameConversation();
  const deleteConversation = useDeleteConversation();
  const saveRename = async () => {
    if (!renameTarget) return;
    await renameConversation.mutateAsync({ conversationId: renameTarget.id, conversationTitle: renameTarget.title });
    onRenamed(renameTarget.id);
    onRenameTargetChange(null);
  };
  const confirmDelete = async () => {
    if (!deleteTargetId) return;
    await deleteConversation.mutateAsync(deleteTargetId);
    onDeleted(deleteTargetId);
    onDeleteTargetChange(null);
  };
  return (
    <>
      <Dialog
        open={renameTarget !== null} onOpenChange={(open) => !open && onRenameTargetChange(null)} title={t("list.renameTitle")}
        footer={<Button onClick={saveRename} isLoading={renameConversation.isPending} disabled={!renameTarget?.title.trim()}>{t("list.save")}</Button>}
      >
        <Input label={t("list.nameLabel")} value={renameTarget?.title ?? ""} onChange={(event) => onRenameTargetChange(renameTarget ? { ...renameTarget, title: event.target.value } : renameTarget)} maxLength={120} />
      </Dialog>
      <ConfirmDialog
        open={deleteTargetId !== null} onOpenChange={(open) => !open && onDeleteTargetChange(null)} title={t("list.deleteTitle")} description={t("list.deleteDescription")}
        confirmLabel={t("list.delete")} tone="danger" onConfirm={confirmDelete}
      />
    </>
  );
}
