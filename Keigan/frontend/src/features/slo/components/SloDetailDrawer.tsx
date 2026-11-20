import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSloSeries, type SloSummary } from "@/api/sloApi";
import { TimeSeriesChart } from "@/components/charts";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatNumber } from "@/utils/formatters";
import { BurnChip, SloStatusChip } from "./SloCard";

/** SLI over time with the dashed target line, and the error budget burn-down. */
export function SloDetailDrawer({ slo, onClose }: { slo: SloSummary | null; onClose: () => void }) {
  const { t } = useTranslation("slo");
  const [resolution, setResolution] = useState<"60" | "1440">("1440");
  const seriesQuery = useSloSeries(slo?.sloId ?? null, Number(resolution));
  const points = (seriesQuery.data?.points ?? []).map((point) => ({ time: point.timestamp, sli: point.sliPercentage, budget: point.budgetRemainingPercentage }));
  const valuesWithData = points.map((point) => point.sli).filter((value): value is number => value !== null);
  const lowest = valuesWithData.length ? Math.min(...valuesWithData, slo?.targetPercentage ?? 100) : 90;
  return (
    <Drawer open={slo !== null} onOpenChange={(isOpen) => (isOpen ? undefined : onClose())} size="lg" title={slo?.sliName ?? ""} description={slo ? `${slo.applicationName} · ${slo.serviceName ?? ""}` : undefined}
      headerContent={slo ? <div className="flex flex-wrap items-center gap-2"><SloStatusChip status={slo.status} /><BurnChip label={t("card.burn1h")} rate={slo.burnRateOneHour} /><BurnChip label={t("card.burn6h")} rate={slo.burnRateSixHours} /></div> : undefined}>
      {slo ? (
        <div className="flex flex-col gap-6">
          <KeyValueList isDivided dense items={[
            { key: "compliance", label: t("detail.compliance"), value: slo.compliancePercentage === null ? "–" : `${formatNumber(slo.compliancePercentage, { maximumFractionDigits: 3 })} %` },
            { key: "target", label: t("detail.target"), value: `${slo.targetPercentage} %` },
            { key: "budget", label: t("detail.budget"), value: slo.errorBudgetRemainingMinutes === null ? "–" : t("detail.budgetValue", { minutes: Math.round(slo.errorBudgetRemainingMinutes), total: Math.round(slo.errorBudgetTotalMinutes ?? 0) }) },
          ]} />
          <SegmentedControl aria-label={t("detail.resolution")} value={resolution} onValueChange={setResolution} size="sm" options={[{ value: "1440", label: t("detail.daily") }, { value: "60", label: t("detail.hourly") }]} />
          {seriesQuery.isLoading ? <Skeleton className="h-64 w-full" /> : null}
          {seriesQuery.isError ? <ErrorState size="sm" error={seriesQuery.error} onRetry={() => seriesQuery.refetch()} /> : null}
          {points.length > 0 ? (
            <>
              <section className="flex flex-col gap-2">
                <h3 className="text-h3 font-semibold">{t("detail.sliOverTime")}</h3>
                <TimeSeriesChart data={points} series={[{ key: "sli", label: t("detail.sli") }]} targetValue={slo.targetPercentage} targetLabel={t("detail.targetLine")} yDomain={[Math.floor(lowest - 0.2), 100]}
                  xFormatter={(value) => formatDate(String(value), { month: "short", day: "numeric" })} valueFormatter={(value) => `${formatNumber(value, { maximumFractionDigits: 3 })} %`} ariaLabel={t("detail.sliOverTime")} />
              </section>
              <section className="flex flex-col gap-2">
                <h3 className="text-h3 font-semibold">{t("detail.burnDown")}</h3>
                <TimeSeriesChart data={points} series={[{ key: "budget", label: t("detail.budgetRemaining"), showArea: true }]} yDomain={["auto", 100]} xFormatter={(value) => formatDate(String(value), { month: "short", day: "numeric" })}
                  valueFormatter={(value) => `${formatNumber(value, { maximumFractionDigits: 1 })} %`} ariaLabel={t("detail.burnDown")} />
              </section>
            </>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
