import { useState } from "react";
import { CalendarClock, Check, EllipsisVertical, ExternalLink, Pencil, Trash2, Undo2, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useAcceptActionItem, useChangeActionItemStatus, useDiscardActionItem, useSendActionItemToServiceNow, useUpdateActionItem,
  type ActionItem, type ActionItemFields, type ActionItemPriority, type ActionItemStatus,
} from "@/api/actionItemsApi";
import { isApiError } from "@/api/httpClient";
import { Button } from "@/components/ui/Button";
import { DropdownMenu, type DropdownMenuEntry } from "@/components/ui/DropdownMenu";
import { IconButton } from "@/components/ui/IconButton";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { useToast } from "@/components/ui/Toast";
import { formatDate } from "@/utils/formatters";
import { ActionItemDialog } from "./ActionItemDialog";
import { ActionItemStatusDialog } from "./ActionItemStatusDialog";

const statusTones: Record<ActionItemStatus, StatusTone> = { proposed: "ai", open: "neutral", in_progress: "info", blocked: "warning", done: "success", wont_do: "neutral" };
const priorityTones: Record<ActionItemPriority, StatusTone> = { top: "danger", high: "warning", normal: "neutral", low: "neutral" };

/** A calendar date (YYYY-MM-DD) shown as a date: parsed at noon so no time zone can move it to the day before or after. */
function formatDueDate(dueOn: string): string {
  return formatDate(new Date(`${dueOn}T12:00:00`));
}

/** The items as rows with the actions the server says the caller may take; owns the edit, accept and status dialogs. */
export function ActionItemList({ items, showApplication = false }: { items: ActionItem[]; showApplication?: boolean }) {
  const { t } = useTranslation("actionItems");
  const { showToast } = useToast();
  const accept = useAcceptActionItem();
  const update = useUpdateActionItem();
  const changeStatus = useChangeActionItemStatus();
  const discard = useDiscardActionItem();
  const sendToServiceNow = useSendActionItemToServiceNow();
  const [editing, setEditing] = useState<{ item: ActionItem; mode: "edit" | "accept" } | null>(null);
  const [moving, setMoving] = useState<{ item: ActionItem; status: ActionItemStatus } | null>(null);
  const reportError = (failure: unknown) => showToast({ tone: "danger", title: t("errors.actionFailed"), description: isApiError(failure) ? failure.detail : undefined });

  const menuFor = (item: ActionItem): DropdownMenuEntry[] => {
    const entries: DropdownMenuEntry[] = [];
    if (item.itemStatus === "proposed") {
      if (item.canEdit) {
        entries.push({ key: "accept", label: t("row.accept"), icon: Check, onSelect: () => accept.mutate({ actionItemId: item.actionItemId }, { onError: reportError }) });
        entries.push({ key: "editAccept", label: t("row.editAndAccept"), icon: Pencil, onSelect: () => setEditing({ item, mode: "accept" }) });
        entries.push({ key: "discard", label: t("row.discard"), icon: Trash2, tone: "danger", onSelect: () => discard.mutate(item.actionItemId, { onError: reportError }) });
      }
      return entries;
    }
    for (const status of item.allowedStatuses) {
      entries.push({ key: status, label: t(`statusAction.${status}`), icon: status === "open" ? Undo2 : undefined, onSelect: () => setMoving({ item, status }) });
    }
    if (item.canSendExternal) {
      entries.push({
        key: "track", label: t("row.trackInServiceNow"), icon: ExternalLink,
        onSelect: () => sendToServiceNow.mutate(item.actionItemId, {
          onError: reportError,
          onSuccess: (sent) => { if (sent.external?.syncStatus === "failed") showToast({ tone: "warning", title: t("row.trackFailed") }); },
        }),
      });
    }
    if (item.canEdit || item.canChangeStatus) entries.push({ key: "edit", label: t("row.edit"), icon: Pencil, onSelect: () => setEditing({ item, mode: "edit" }) });
    return entries;
  };

  return (
    <>
      <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline bg-surface">
        {items.map((item) => {
          const entries = menuFor(item);
          return (
            <li key={item.actionItemId} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-default">{item.itemTitle}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <StatusChip tone={statusTones[item.itemStatus]} size="sm">{t(`status.${item.itemStatus}`)}</StatusChip>
                  <StatusChip tone={priorityTones[item.actionPriority]} size="sm" variant="outline">{t(`priority.${item.actionPriority}`)}</StatusChip>
                  <StatusChip tone="neutral" size="sm" variant="outline" icon={false}>{t(`type.${item.actionType}`)}</StatusChip>
                  {item.isOverdue ? <StatusChip tone="danger" size="sm">{t("row.overdueDays", { count: item.daysOverdue })}</StatusChip> : null}
                  {item.external?.syncStatus === "linked" ? (
                    <StatusChip tone="info" size="sm" variant="outline">
                      {item.external.url ? <a href={item.external.url} target="_blank" rel="noreferrer" className="underline">{t("row.trackedIn", { number: item.external.number ?? "", status: item.external.statusText ?? "" })}</a> : t("row.trackedIn", { number: item.external.number ?? "", status: item.external.statusText ?? "" })}
                    </StatusChip>
                  ) : null}
                  {item.external?.syncStatus === "failed" ? <StatusChip tone="warning" size="sm">{t("row.trackFailed")}</StatusChip> : null}
                </div>
                <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-body-sm text-muted">
                  <span className="inline-flex items-center gap-1.5"><UserRound size={14} aria-hidden />{item.owner ? item.owner.displayName : item.suggestedOwnerRoleText ? t("row.suggestedRole", { role: item.suggestedOwnerRoleText }) : t("row.unassigned")}</span>
                  <span className="inline-flex items-center gap-1.5"><CalendarClock size={14} aria-hidden />{item.dueOn ? t("row.due", { date: formatDueDate(item.dueOn) }) : t("row.noDueDate")}</span>
                  {item.dueOnChangeCount > 0 && item.originalDueOn ? <span>{t("row.moved", { count: item.dueOnChangeCount, date: formatDueDate(item.originalDueOn) })}</span> : null}
                  {showApplication ? <span>{item.applicationName}</span> : null}
                  {item.incidentReference ? <span>{t("row.incident", { reference: item.incidentReference })}</span> : null}
                  {item.runbookTitle ? <span>{t("row.runbook", { title: item.runbookTitle })}</span> : null}
                </p>
                {item.statusReasonText ? <p className="mt-1 text-body-sm text-muted">{t("row.reason", { text: item.statusReasonText })}</p> : null}
                {item.completionNoteText ? <p className="mt-1 text-body-sm text-muted">{t("row.completionNote", { text: item.completionNoteText })}</p> : null}
              </div>
              {item.itemStatus === "proposed" && item.canEdit ? (
                <Button size="sm" variant="secondary" leadingIcon={Check} isLoading={accept.isPending && accept.variables?.actionItemId === item.actionItemId} onClick={() => accept.mutate({ actionItemId: item.actionItemId }, { onError: reportError })}>{t("row.accept")}</Button>
              ) : null}
              {entries.length > 0 ? (
                <DropdownMenu entries={entries} trigger={<IconButton icon={EllipsisVertical} label={t("row.actionsFor", { title: item.itemTitle })} size="sm" variant="ghost" />} />
              ) : null}
            </li>
          );
        })}
      </ul>
      <ActionItemDialog
        open={editing !== null}
        onOpenChange={(open) => { if (!open) setEditing(null); }}
        mode={editing?.mode ?? "edit"}
        applicationId={editing?.item.applicationId ?? ""}
        item={editing?.item}
        detailsOnly={editing?.mode === "edit" && !editing.item.canEdit}
        onSubmit={async (fields: ActionItemFields) => {
          if (!editing) return;
          if (editing.mode === "accept") await accept.mutateAsync({ actionItemId: editing.item.actionItemId, body: fields });
          else await update.mutateAsync({ actionItemId: editing.item.actionItemId, body: editing.item.canEdit ? fields : { itemDetailsMarkdown: fields.itemDetailsMarkdown } });
        }}
      />
      <ActionItemStatusDialog
        item={moving?.item ?? null}
        targetStatus={moving?.status ?? null}
        onClose={() => setMoving(null)}
        onSubmit={async (body) => { if (moving) await changeStatus.mutateAsync({ actionItemId: moving.item.actionItemId, body }); }}
      />
    </>
  );
}
