import { Link } from "react-router";
import { CircleCheckBig } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AttentionEntry, AttentionKind } from "@/api/actionItemsApi";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatNumber } from "@/utils/formatters";

/** The order the groups appear in: the most urgent first (the server already sorts the entries inside each group). */
const kindOrder: AttentionKind[] = ["overdue_item", "top_priority_unowned", "policy_breach_open", "postmortem_missing", "proposed_waiting"];

function incidentSearchPath(entry: AttentionEntry): string | null {
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
                    <div className="flex flex-wrap items-center gap-2"><EntryDetails entry={entry} /></div>
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
