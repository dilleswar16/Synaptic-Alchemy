import { Link } from "react-router";
import { Repeat2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { RepeatGroup, RepeatIncident, RepeatOutcome } from "@/api/actionItemsApi";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { formatDate } from "@/utils/formatters";

const outcomeTones: Record<RepeatOutcome, StatusTone> = { no_postmortem: "warning", no_prevent_item: "warning", repeated_while_open: "danger", repeated_after_done: "info" };

function RepeatRow({ incident }: { incident: RepeatIncident }) {
  const { t } = useTranslation("actionItems");
  const notDoneCount = incident.earlierPreventItems.filter((item) => item.statusAtRepeat !== "done").length;
  return (
    <li className="flex flex-col gap-2 border-l-2 border-hairline pl-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link to={`/incidents?search=${encodeURIComponent(incident.incidentReference)}`} className="font-semibold text-default hover:text-action">{incident.incidentReference}</Link>
        <span className="text-caption text-muted">{formatDate(incident.openedAt)}</span>
        {incident.outcome ? <StatusChip tone={outcomeTones[incident.outcome]} size="sm">{t(`repeats.outcome.${incident.outcome}`, { count: notDoneCount })}</StatusChip> : <span className="text-caption text-muted">{t("repeats.first")}</span>}
      </div>
      {incident.earlierPreventItems.length > 0 ? (
        <details className="text-body-sm">
          <summary className="cursor-pointer text-muted hover:text-default">{t("repeats.showItems", { count: incident.earlierPreventItems.length })}</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {incident.earlierPreventItems.map((item) => (
              <li key={item.actionItemId} className="flex flex-wrap items-center gap-2">
                <StatusChip tone={item.statusAtRepeat === "done" ? "success" : "warning"} size="sm" variant="outline">{t(`repeats.itemState.${item.statusAtRepeat}`)}</StatusChip>
                <span>{item.itemTitle}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </li>
  );
}

/** Incidents of the same kind on the same service, in time order, and what had happened to the follow-ups meant to prevent them. */
export function RepeatsPanel({ groups, showApplication }: { groups: RepeatGroup[]; showApplication: boolean }) {
  const { t } = useTranslation("actionItems");
  if (groups.length === 0) {
    return <EmptyState icon={Repeat2} title={t("repeats.empty.title")} description={t("repeats.empty.description")} isBordered />;
  }
  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => (
        <Card key={`${group.applicationId}-${group.recurrenceCategory}-${group.serviceId}`} dense>
          <h2 className="font-display text-h4 text-default">
            {t("repeats.groupTitle", { service: group.serviceName || t("repeats.unknownService"), category: group.recurrenceCategory.replace(/_/g, " ") })}
          </h2>
          {showApplication ? <p className="text-caption text-muted">{group.applicationName}</p> : null}
          <ol className="mt-4 flex flex-col gap-4">
            {group.incidents.map((incident) => <RepeatRow key={incident.incidentId} incident={incident} />)}
          </ol>
        </Card>
      ))}
    </div>
  );
}
