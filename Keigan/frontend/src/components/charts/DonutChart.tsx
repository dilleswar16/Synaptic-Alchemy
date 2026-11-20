import type { ReactNode } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useTranslation } from "react-i18next";
import { formatNumber, formatPercentage } from "@/utils/formatters";
import { ChartFrame, type ChartLegendItem } from "./ChartFrame";
import { resolveSeriesColor } from "./chartTheme";
import { ChartTooltipContent } from "./ChartTooltipContent";

export interface DonutSlice {
  key: string;
  label: string;
  value: number;
  /** CSS colour or tone token (e.g. "success", "danger"); defaults to the categorical slot. */
  color?: string;
}

export interface DonutChartProps {
  slices: DonutSlice[];
  /** Big number in the hole (e.g. "62%"). */
  centerValue?: ReactNode;
  centerLabel?: ReactNode;
  valueFormatter?: (value: number) => string;
  size?: number;
  ariaLabel: string;
  className?: string;
}

/** Donut with centre label; keep to 5 slices or fewer (fold the rest into "Other"). */
export function DonutChart({ slices, centerValue, centerLabel, valueFormatter = (value) => formatNumber(value), size = 200, ariaLabel, className }: DonutChartProps) {
  const { t } = useTranslation("common");
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  if (slices.length === 0 || total <= 0) {
    return <p className="py-10 text-center text-body-sm text-muted">{t("chart.noData")}</p>;
  }
  const colors = slices.map((slice, sliceIndex) => resolveSeriesColor(slice.color, sliceIndex));
  const legendItems: ChartLegendItem[] = slices.map((slice, sliceIndex) => ({
    key: slice.key,
    label: `${slice.label} · ${valueFormatter(slice.value)}`,
    color: colors[sliceIndex] ?? "var(--chart-1)",
    shape: "square",
  }));

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      legendItems={legendItems}
      className={className}
      tableData={{
        columns: [
          { key: "category", header: t("chart.category") },
          { key: "value", header: t("chart.value"), align: "end" },
          { key: "share", header: t("chart.share"), align: "end" },
        ],
        rows: slices.map((slice) => ({
          __rowKey: slice.key,
          category: slice.label,
          value: valueFormatter(slice.value),
          share: formatPercentage((slice.value / total) * 100),
        })),
      }}
    >
      <div className="relative mx-auto" style={{ width: size, height: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip
              content={(tooltipProps) => (
                <ChartTooltipContent
                  active={tooltipProps.active}
                  payload={tooltipProps.payload?.map((entry) => ({ ...entry, dataKey: entry.name })) as never}
                  valueFormatter={valueFormatter}
                  keyShape="square"
                />
              )}
            />
            <Pie
              data={slices}
              dataKey="value"
              nameKey="label"
              innerRadius="66%"
              outerRadius="100%"
              paddingAngle={slices.length > 1 ? 2 : 0}
              stroke="var(--color-surface)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {slices.map((slice, sliceIndex) => (
                <Cell key={slice.key} fill={colors[sliceIndex]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        {centerValue !== undefined || centerLabel !== undefined ? (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            {centerValue !== undefined ? <span className="font-display text-kpi-sm tabular-numbers text-default">{centerValue}</span> : null}
            {centerLabel !== undefined ? <span className="text-caption text-muted">{centerLabel}</span> : null}
          </div>
        ) : null}
      </div>
    </ChartFrame>
  );
}
