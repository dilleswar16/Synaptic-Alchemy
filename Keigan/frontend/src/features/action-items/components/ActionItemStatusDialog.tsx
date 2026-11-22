import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ActionItem, ActionItemStatus, ActionItemStatusBody } from "@/api/actionItemsApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Textarea } from "@/components/ui/Textarea";

/** Statuses that need a written reason (the server enforces the minimum length). */
export const statusesNeedingAReason: ActionItemStatus[] = ["blocked", "wont_do"];

export interface ActionItemStatusDialogProps {
  item: ActionItem | null;
  targetStatus: ActionItemStatus | null;
  onClose: () => void;
  onSubmit: (body: ActionItemStatusBody) => Promise<void>;
}

/** Asks for the reason (blocked, won't do) or an optional completion note (done) before the status changes. */
export function ActionItemStatusDialog({ item, targetStatus, onClose, onSubmit }: ActionItemStatusDialogProps) {
  const { t } = useTranslation("actionItems");
  const [text, setText] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  useEffect(() => {
    setText("");
    setFailure(null);
  }, [item?.actionItemId, targetStatus]);

  if (!item || !targetStatus) return null;
  const needsReason = statusesNeedingAReason.includes(targetStatus);
  const asksForNote = targetStatus === "done";

  const confirm = async () => {
    setIsSaving(true);
    setFailure(null);
    try {
      await onSubmit({ status: targetStatus, ...(needsReason ? { reasonText: text } : asksForNote && text.trim() ? { completionNoteText: text } : {}) });
      onClose();
    } catch (error) {
      setFailure((isApiError(error) ? error.detail : undefined) ?? t("errors.actionFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => { if (!open) onClose(); }}
      title={t(`statusDialog.title.${targetStatus}`)}
      description={item.itemTitle}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t("dialog.cancel")}</Button>
          <Button isLoading={isSaving} disabled={needsReason && text.trim().length === 0} onClick={() => void confirm()}>{t(`statusDialog.confirm.${targetStatus}`)}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {failure ? <Banner tone="danger" title={t("errors.actionFailed")}>{failure}</Banner> : null}
        {needsReason || asksForNote ? (
          <Textarea
            label={needsReason ? t("statusDialog.reasonLabel") : t("statusDialog.noteLabel")}
            helperText={needsReason ? t("statusDialog.reasonHelp") : t("statusDialog.noteHelp")}
            isOptional={!needsReason}
            value={text}
            autoResize
            maximumRows={8}
            onChange={(event) => setText(event.target.value)}
          />
        ) : (
          <p className="text-body text-muted">{t(`statusDialog.plain.${targetStatus}`)}</p>
        )}
      </div>
    </Dialog>
  );
}
