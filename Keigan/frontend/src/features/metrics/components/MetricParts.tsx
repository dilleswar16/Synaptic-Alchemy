import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MetricStat } from "@/api/metricsApi";
import { Popover } from "@/components/ui/Popover";
import { cn } from "@/utils/cn";
import { formatDuration, formatNumber } from "@/utils/formatters";

/** Seconds as "1h 5m". */
export function formatSeconds(seconds: number | null): string {
  return seconds === null ? "" : formatDuration(seconds * 1000);
}

/** Milliseconds as "620 ms" or "1.4 s" (formatDuration rounds a sub-second value down to 0 s). */
export function formatMilliseconds(milliseconds: number | null): string {
  if (milliseconds === null) {
    return "";
  }
  return milliseconds < 1000
    ? formatNumber(milliseconds, { style: "unit", unit: "millisecond", unitDisplay: "narrow", maximumFractionDigits: 0 })
    : formatNumber(milliseconds / 1000, { style: "unit", unit: "second", unitDisplay: "narrow", maximumFractionDigits: 1 });
}

export function formatCount(value: number | null): string {
  return value === null ? "" : formatNumber(value, { maximumFractionDigits: 0 });
}

/** A label with an info button that opens the metric's definition (click or Enter, so it also works on a phone). */
export function MetricLabel({ metricKey, label }: { metricKey: string; label?: string }) {
  const { t } = useTranslation("metrics");
  const title = label ?? t(`definitions.${metricKey}.title`);
  return (
    <span className="inline-flex items-center gap-1">
      <span>{title}</span>
      <Popover
        width="md"
        align="start"
        aria-label={title}
        trigger={
          <button type="button" aria-label={t("info.open", { metric: title })} className="grid size-6 place-items-center rounded-full text-subtle transition-colors hover:bg-surface-hover hover:text-action">
            <Info aria-hidden="true" size={15} strokeWidth={2} />
          </button>
        }
      >
        <p className="text-body-sm font-semibold text-default">{t(`definitions.${metricKey}.title`)}</p>
        <p className="mt-1 text-body-sm text-muted">{t(`definitions.${metricKey}.text`)}</p>
      </Popover>
    </span>
  );
}

/** The line under a headline figure: p90, the sample size n, and how many cases had to be left out (with the reason). */
export function StatDetail({ stat, format, excludedReasonKey }: { stat: MetricStat; format: (value: number | null) => string; excludedReasonKey?: string }) {
  const { t } = useTranslation("metrics");
  return (
    <>
      {stat.sampleCount > 0 ? (
        <span className="block">{t("figure.detail", { p90: format(stat.p90), count: stat.sampleCount })}</span>
      ) : (
        <span className="block">{t("figure.noSamples")}</span>
      )}
      {stat.excludedCount > 0 && excludedReasonKey ? <span className="block">{t("figure.excluded", { count: stat.excludedCount, reason: t(`reasons.${excludedReasonKey}`) })}</span> : null}
    </>
  );
}

/** A table cell: the median with "p90 · n" underneath; a dash and n = 0 when there is no data. */
export function StatCell({ stat, format, className }: { stat: MetricStat; format: (value: number | null) => string; className?: string }) {
  const { t } = useTranslation("metrics");
  return (
    <span className={cn("flex flex-col tabular-numbers", className)}>
      <span className={cn("font-medium", stat.sampleCount === 0 ? "text-muted" : "text-default")}>{stat.sampleCount > 0 ? format(stat.median) : t("figure.none")}</span>
      <span className="text-caption text-muted">{stat.sampleCount > 0 ? t("figure.detail", { p90: format(stat.p90), count: stat.sampleCount }) : t("figure.noSamplesShort")}</span>
    </span>
  );
}
