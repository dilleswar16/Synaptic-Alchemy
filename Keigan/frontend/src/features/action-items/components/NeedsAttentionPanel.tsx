import { useState } from "react";
import { Link } from "react-router";
import { CircleCheckBig, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { type AttentionEntry, type AttentionKind, useCreateActionItem } from "@/api/actionItemsApi";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useAccessControl } from "@/auth/accessControl";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatNumber } from "@/utils/formatters";
import { ActionItemDialog } from "./ActionItemDialog";

/** The order the groups appear in: the most urgent first (the server already sorts the entries inside each group). */
const kindOrder: AttentionKind[] = ["overdue_item", "top_priority_unowned", "policy_breach_open", "postmortem_missing", "proposed_waiting"];

/** Where an entry leads: an entry about one action item opens that item; the others look the incident up by its number. */
function incidentSearchPath(entry: AttentionEntry): string | null {
  if (entry.recordKind === "action_item") return `/action-items?item=${encodeURIComponent(entry.recordId)}`;
  const reference = entry.parameters.incidentReference;
  return typeof reference === "string" && reference ? `/incidents?search=${encodeURIComponent(reference)}` : null;
}

function EntryDetails({ entry }: { entry: AttentionEntry }) {
  const { t } = useTranslation("actionItems");
  const parameters = entry.parameters;
  switch (entry.kind) {
    case "overdue_item":
      return (
        <>
          <StatusChip tone="danger" size="sm">{t("row.overdueDays", { count: Number(parameters.daysOverdue) })}</StatusChip>
          {typeof parameters.priority === "string" ? <StatusChip tone={parameters.priority === "top" ? "danger" : "neutral"} size="sm" variant="outline">{t(`priority.${parameters.priority}`)}</StatusChip> : null}
        </>
      );
    case "top_priority_unowned":
      return <StatusChip tone="warning" size="sm">{t("attention.noOwner")}</StatusChip>;
    case "policy_breach_open":
      return (
        <>
          <StatusChip tone="warning" size="sm">{t(`attention.breachKind.${String(parameters.breachKind)}`)}</StatusChip>
          {typeof parameters.sharePercent === "number" ? <span className="text-caption text-muted">{t("attention.breachShare", { share: formatNumber(parameters.sharePercent, { maximumFractionDigits: 1 }) })}</span> : null}
        </>
      );
    case "postmortem_missing":
      return (
        <>
          {typeof parameters.incidentPriority === "string" ? <StatusChip tone="danger" size="sm" variant="outline">{parameters.incidentPriority}</StatusChip> : null}
          <span className="text-caption text-muted">{t("attention.resolvedDaysAgo", { count: Number(parameters.daysWaiting) })}</span>
        </>
      );
    case "proposed_waiting":
      return <span className="text-caption text-muted">{t("attention.suggestionsWaiting", { count: Number(parameters.proposedCount), days: Number(parameters.daysWaiting) })}</span>;
  }
}

/** The error budget policy asks for a top-priority prevent item: this adds it, linked to the incident when the breach has one. Only people who may edit the application see it. */
function AddTopPriorityItem({ entry }: { entry: AttentionEntry }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const { canEdit } = useAccessControl();
  const create = useCreateActionItem();
  const [isAdding, setIsAdding] = useState(false);
  const incidentId = typeof entry.parameters.incidentId === "string" && entry.parameters.incidentId ? entry.parameters.incidentId : null;
  if (!canEdit(entry.applicationId)) return null;
  return (
    <>
      <Button size="sm" variant="secondary" leadingIcon={Plus} onClick={() => setIsAdding(true)}>{t("banner.addItem")}</Button>
      <ActionItemDialog
        open={isAdding}
        onOpenChange={setIsAdding}
        mode="create"
        applicationId={entry.applicationId}
        preset={{ actionType: "prevent", actionPriority: "top" }}
        onSubmit={async (fields) => { await create.mutateAsync({ applicationId: entry.applicationId, body: { ...fields, ...(incidentId ? { incidentId } : {}) } }); }}
      />
    </>
  );
}

/** What a team should look at now, grouped by kind. Names applications and records, never people. */
export function NeedsAttentionPanel({ entries, showApplication }: { entries: AttentionEntry[]; showApplication: boolean }) {
  const { t } = useTranslation("actionItems");
  if (entries.length === 0) {
    return <EmptyState icon={CircleCheckBig} title={t("attention.empty.title")} description={t("attention.empty.description")} isBordered />;
  }
  return (
    <div className="flex flex-col gap-6">
      {kindOrder.map((kind) => {
        const group = entries.filter((entry) => entry.kind === kind);
        if (group.length === 0) return null;
        return (
          <section key={kind} aria-labelledby={`attention-${kind}`} className="flex flex-col gap-2">
            <h2 id={`attention-${kind}`} className="font-display text-h4 text-default">{t(`attention.kind.${kind}`)}</h2>
            <p className="text-body-sm text-muted">{t(`attention.kindHelp.${kind}`)}</p>
            <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline bg-surface">
              {group.map((entry) => {
                const incidentPath = incidentSearchPath(entry);
                return (
                  <li key={`${entry.kind}-${entry.recordId}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      {incidentPath ? <Link to={incidentPath} className="font-semibold text-default hover:text-action">{entry.title}</Link> : <p className="font-semibold text-default">{entry.title}</p>}
                      {showApplication ? <p className="text-caption text-muted">{entry.applicationName}</p> : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-2"><EntryDetails entry={entry} />{entry.kind === "policy_breach_open" ? <AddTopPriorityItem entry={entry} /> : null}</div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
