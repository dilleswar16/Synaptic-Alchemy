import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useEcosystemHeatmap } from "@/api/sloApi";
import { HeatmapGrid, chartToneColors } from "@/components/charts";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatNumber } from "@/utils/formatters";

/** All applications by SLOs, one cell per day; cells below target are coloured as breaches. */
export function EcosystemHeatmap({ days = 30 }: { days?: number }) {
  const { t } = useTranslation("slo");
  const heatmapQuery = useEcosystemHeatmap(days);
  const heatmap = heatmapQuery.data;
  const cellByKey = useMemo(() => new Map((heatmap?.rows ?? []).flatMap((row) => row.cells.map((cell) => [`${row.sloId}|${cell.date}`, cell.compliancePercentage] as const))), [heatmap]);
  const targetBySloId = useMemo(() => new Map((heatmap?.rows ?? []).map((row) => [row.sloId, row.targetPercentage] as const)), [heatmap]);
  /** Judge each day against that SLO's own target: met → green; within twice the daily budget → amber; worse → red. */
  const colorForCompliance = (compliancePercentage: number, sloId: string) => {
    const targetPercentage = targetBySloId.get(sloId) ?? 99;
    if (compliancePercentage >= targetPercentage) return chartToneColors.success;
    return compliancePercentage >= targetPercentage - (100 - targetPercentage) ? chartToneColors.warning : chartToneColors.danger;
  };
  if (heatmapQuery.isLoading) return <Skeleton className="h-64 w-full" />;
  if (heatmapQuery.isError) return <ErrorState size="sm" error={heatmapQuery.error} onRetry={() => heatmapQuery.refetch()} />;
  if (!heatmap || heatmap.rows.length === 0) return <EmptyState isBordered size="sm" title={t("heatmap.emptyTitle")} description={t("heatmap.emptyDescription")} />;
  return (
    <HeatmapGrid
      ariaLabel={t("heatmap.title")}
      rows={heatmap.rows.map((row) => ({ key: row.sloId, label: `${row.applicationName.split(" (")[0]} · ${row.rowLabel}` }))}
      columns={heatmap.dates.map((date) => ({ key: date, label: formatDate(date, { month: "short", day: "numeric" }) }))}
      getValue={(rowKey, columnKey) => cellByKey.get(`${rowKey}|${columnKey}`)}
      valueFormatter={(value) => `${formatNumber(value, { maximumFractionDigits: 2 })} %`}
      minimumValue={95}
      maximumValue={100}
      colorForValue={colorForCompliance}
    />
  );
}

