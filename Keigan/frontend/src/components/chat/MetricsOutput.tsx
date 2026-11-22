import { Flame, Gauge, Hash, Hourglass, Target, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { StatTile } from "@/components/ui/StatTile";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { formatList, formatNumber, formatPercentage } from "@/utils/formatters";
import { readMetricGroups, type MetricGroup, type MetricValue } from "./toolOutputModels";
import { fieldLabel, formatEnumToken } from "./toolValues";

/** Digits after the decimal point for a share and for a rate: an SLO of 99.62 % must not round to 100 %. */
const percentageFractionDigits = 2;
const numberFractionDigits = 2;

/** Tone of an SLO status; a status this view does not know is neutral (its word is still shown). */
const statusTones: Readonly<Record<string, StatusTone>> = { healthy: "success", at_risk: "warning", breached: "danger", no_data: "neutral" };

const metricIcons: Readonly<Record<string, LucideIcon>> = {
  compliance_percentage: Gauge,
  target_percentage: Target,
  error_budget_remaining_percentage: Hourglass,
  burn_rate_one_hour: Flame,
  burn_rate_six_hours: Flame,
};

/** The text of a metric value: a share as a percentage, a count or a rate as a number, the "no value" mark when the tool has none. */
function formatMetricValue({ kind, value }: Pick<MetricValue, "kind" | "value">, noValueText: string): string {
  if (value === null) {
    return noValueText;
  }
  return kind === "percentage" ? formatPercentage(value, { maximumFractionDigits: percentageFractionDigits }) : formatNumber(value, { maximumFractionDigits: numberFractionDigits });
}

function MetricGroupView({ group }: { group: MetricGroup }) {
  const { t } = useTranslation("chat");
  const context = formatList([group.applicationName, group.windowDays === null ? null : t("tool.metrics.windowDays", { count: group.windowDays })].filter((part): part is string => Boolean(part)));
  const title = formatList(group.titleParts);
  return (
    <section className="flex flex-col gap-2 rounded-md border border-hairline bg-surface-sunken p-3">
      {title || group.status ? (
        <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          {title ? <h5 className="min-w-0 text-body-sm font-semibold break-words text-default">{title}</h5> : null}
          {group.status ? <StatusChip tone={statusTones[group.status] ?? "neutral"} size="sm">{formatEnumToken(t, group.status)}</StatusChip> : null}
        </header>
      ) : null}
      {context ? <p className="text-caption break-words text-muted">{context}</p> : null}
      <ul className="grid grid-cols-2 gap-2">
        {group.values.map((metric) => (
          <li key={metric.fieldName} className="min-w-0">
            <StatTile size="compact" icon={metricIcons[metric.fieldName] ?? Hash} iconTone="brand" label={fieldLabel(t, metric.fieldName)} value={formatMetricValue(metric, t("tool.noValue"))} className="h-full" />
          </li>
        ))}
      </ul>
      {group.isApproximate ? <p className="text-caption text-muted">{t("tool.metrics.approximate")}</p> : null}
    </section>
  );
}

/** The numbers of a metrics tool (SLO status): one block per SLO with its status and a tile per number. Tiles are not links. */
export function MetricsOutput({ output }: { output: Record<string, unknown> }) {
  const groups = readMetricGroups(output);
  return groups.length > 0 ? (
    <div className="flex flex-col gap-3">
      {groups.map((group) => <MetricGroupView key={group.key} group={group} />)}
    </div>
  ) : null;
}
