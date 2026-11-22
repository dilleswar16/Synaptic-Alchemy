import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { actionItemPriorities, actionItemTypes, type ActionItem, type ActionItemFields, type ActionItemPriority, type ActionItemType } from "@/api/actionItemsApi";
import { isApiError } from "@/api/httpClient";
import { useStakeholders } from "@/api/notificationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";

const unassigned = "unassigned";

export interface ActionItemDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `create` has no item yet; `edit` changes a tracked item; `accept` edits a suggestion and accepts it in the same step. */
  mode: "create" | "edit" | "accept";
  applicationId: string;
  item?: ActionItem;
  /** Fields the owner (a reader of the application) may not change are locked. */
  detailsOnly?: boolean;
  onSubmit: (fields: ActionItemFields & { itemTitle: string; actionType: ActionItemType; dueOn: string }) => Promise<void>;
}

/** One form for creating, editing and accepting an action item. The owner list is the application's active team members who are people. */
export function ActionItemDialog({ open, onOpenChange, mode, applicationId, item, detailsOnly = false, onSubmit }: ActionItemDialogProps) {
  const { t } = useTranslation("actionItems");
  const { data: stakeholders } = useStakeholders(applicationId);
  const [itemTitle, setItemTitle] = useState("");
  const [details, setDetails] = useState("");
  const [actionType, setActionType] = useState<ActionItemType>("prevent");
  const [priority, setPriority] = useState<ActionItemPriority>("normal");
  const [ownerId, setOwnerId] = useState<string>(unassigned);
  const [dueOn, setDueOn] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setItemTitle(item?.itemTitle ?? "");
    setDetails(item?.itemDetailsMarkdown ?? "");
    setActionType(item?.actionType ?? "prevent");
    setPriority(item?.actionPriority ?? "normal");
    setOwnerId(item?.owner?.stakeholderId ?? unassigned);
    setDueOn(item?.dueOn ?? "");
    setFailure(null);
  }, [open, item]);

  const people = (stakeholders ?? []).filter((member) => member.recipientType === "person" && member.isActive !== false);
  const canSave = itemTitle.trim().length >= 2 && dueOn !== "";
  const titleKey = mode === "create" ? "dialog.createTitle" : mode === "accept" ? "dialog.acceptTitle" : "dialog.editTitle";
  const submitKey = mode === "create" ? "dialog.create" : mode === "accept" ? "dialog.accept" : "dialog.save";

  const save = async () => {
    setIsSaving(true);
    setFailure(null);
    try {
      await onSubmit({
        itemTitle: itemTitle.trim(),
        actionType,
        actionPriority: priority,
        ownerStakeholderId: ownerId === unassigned ? null : ownerId,
        dueOn,
        itemDetailsMarkdown: details.trim() === "" ? null : details,
      });
      onOpenChange(false);
    } catch (error) {
      setFailure((isApiError(error) ? error.detail : undefined) ?? t("errors.actionFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t(titleKey)}
      description={mode === "accept" ? t("dialog.acceptDescription") : undefined}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("dialog.cancel")}</Button>
          <Button isLoading={isSaving} disabled={!canSave && !detailsOnly} onClick={() => void save()}>{t(submitKey)}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {failure ? <Banner tone="danger" title={t("errors.actionFailed")}>{failure}</Banner> : null}
        <Input label={t("dialog.fieldTitle")} value={itemTitle} maxLength={300} disabled={detailsOnly} onChange={(event) => setItemTitle(event.target.value)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label={t("dialog.fieldType")} value={actionType} disabled={detailsOnly} onValueChange={setActionType} options={actionItemTypes.map((value) => ({ value, label: t(`type.${value}`), description: t(`typeHelp.${value}`) }))} />
          <Select label={t("dialog.fieldPriority")} value={priority} disabled={detailsOnly} onValueChange={setPriority} options={actionItemPriorities.map((value) => ({ value, label: t(`priority.${value}`) }))} />
          <Select
            label={t("dialog.fieldOwner")}
            value={ownerId}
            disabled={detailsOnly}
            helperText={item?.suggestedOwnerRoleText ? t("dialog.suggestedRole", { role: item.suggestedOwnerRoleText }) : undefined}
            onValueChange={setOwnerId}
            options={[{ value: unassigned, label: t("row.unassigned") }, ...people.map((member) => ({ value: member.stakeholderId, label: member.displayName, description: member.stakeholderRole }))]}
          />
          <Input label={t("dialog.fieldDue")} type="date" value={dueOn} disabled={detailsOnly} onChange={(event) => setDueOn(event.target.value)} />
        </div>
        <Textarea label={t("dialog.fieldDetails")} value={details} isOptional autoResize maximumRows={10} onChange={(event) => setDetails(event.target.value)} />
      </div>
    </Dialog>
  );
}
