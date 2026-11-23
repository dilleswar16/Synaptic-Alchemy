import { AlarmClockOff, CircleCheckBig, ListChecks, Timer } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CompletionFigures } from "@/api/actionItemsApi";
import { StatTile } from "@/components/ui/StatTile";
import { formatNumber, formatPercentage } from "@/utils/formatters";

/** Four figures for the chosen period. A rate or a median says how many items it rests on, and is not shown as a number when there is nothing to divide. */
export function OverviewTiles({ completion }: { completion: CompletionFigures }) {
  const { t } = useTranslation("actionItems");
  const none = t("overview.notEnoughData");
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatTile icon={ListChecks} label={t("overview.open")} value={formatNumber(completion.openCount)} secondaryText={t("overview.openHelp")} />
      <StatTile
        icon={AlarmClockOff}
        iconTone={completion.overdueCount > 0 ? "danger" : "brand"}
        label={t("overview.overdue")}
        value={formatNumber(completion.overdueCount)}
        secondaryText={t("overview.overdueHelp")}
        secondaryTone={completion.overdueCount > 0 ? "negative" : "default"}
      />
      <StatTile
        icon={CircleCheckBig}
        iconTone="success"
        label={t("overview.completionRate")}
        value={completion.completionRate === null ? "—" : formatPercentage(completion.completionRate)}
        secondaryText={completion.completionRate === null ? none : t("overview.sample", { count: completion.completionRateSampleCount })}
      />
      <StatTile
        icon={Timer}
        iconTone="info"
        label={t("overview.medianDays")}
        value={completion.medianDaysToComplete === null ? "—" : t("overview.days", { count: completion.medianDaysToComplete, value: formatNumber(completion.medianDaysToComplete, { maximumFractionDigits: 1 }) })}
        secondaryText={completion.medianDaysToComplete === null ? none : t("overview.sample", { count: completion.medianSampleCount })}
      />
    </div>
  );
}
