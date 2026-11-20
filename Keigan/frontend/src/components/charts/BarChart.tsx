import { Bar, BarChart as RechartsBarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";
import { formatNumber } from "@/utils/formatters";
import { ChartFrame, type ChartLegendItem } from "./ChartFrame";
import { chartAxisTickStyle, chartGridStroke, resolveSeriesColor } from "./chartTheme";
import { ChartTooltipContent } from "./ChartTooltipContent";
import { buildSeriesTable } from "./chartUtilities";

export interface BarChartSeries {
  key: string;
  label: string;
  color?: string;
}

export interface BarChartProps {
  data: ReadonlyArray<Record<string, unknown>>;
  series: BarChartSeries[];
  /** Field holding the category label. Default "category". */
  categoryKey?: string;
  categoryFormatter?: (value: string | number) => string;
  valueFormatter?: (value: number) => string;
  /** Stack the series (tokens by feature per day). */
  stacked?: boolean;
  /** Horizontal bars (long category names). */
  isHorizontal?: boolean;
  height?: number;
  ariaLabel: string;
  className?: string;
}

/** Grouped or stacked bar chart with legend and table view. */
export function BarChart({
  data,
  series,
  categoryKey = "category",
  categoryFormatter = (value) => String(value),
  valueFormatter = (value) => formatNumber(value, { maximumFractionDigits: 2 }),
  stacked = false,
  isHorizontal = false,
  height = 260,
  ariaLabel,
  className,
}: BarChartProps) {
  const { t } = useTranslation("common");
  if (data.length === 0) {
    return <p className="py-10 text-center text-body-sm text-muted">{t("chart.noData")}</p>;
  }
  const colors = series.map((seriesItem, seriesIndex) => resolveSeriesColor(seriesItem.color, seriesIndex));
  const legendItems: ChartLegendItem[] = series.map((seriesItem, seriesIndex) => ({
    key: seriesItem.key,
    label: seriesItem.label,
    color: colors[seriesIndex] ?? "var(--chart-1)",
    shape: "square",
  }));
  const seriesLabels = Object.fromEntries(series.map((seriesItem) => [seriesItem.key, seriesItem.label]));
  const seriesColors = Object.fromEntries(series.map((seriesItem, seriesIndex) => [seriesItem.key, colors[seriesIndex] ?? ""]));

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      legendItems={legendItems}
      className={className}
      tableData={buildSeriesTable(t("chart.category"), categoryKey, data, series, (category) => categoryFormatter(category), valueFormatter)}
    >
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart data={data as Array<Record<string, unknown>>} layout={isHorizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={chartGridStroke} strokeDasharray="3 3" vertical={isHorizontal} horizontal={!isHorizontal} />
          {isHorizontal ? (
            <>
              <XAxis type="number" tick={chartAxisTickStyle} tickLine={false} axisLine={false} tickFormatter={valueFormatter} />
              <YAxis type="category" dataKey={categoryKey} tick={chartAxisTickStyle} tickLine={false} axisLine={false} width={110} tickFormatter={categoryFormatter} />
            </>
          ) : (
            <>
              <XAxis dataKey={categoryKey} tick={chartAxisTickStyle} tickLine={false} axisLine={{ stroke: chartGridStroke }} tickFormatter={categoryFormatter} minTickGap={16} />
              <YAxis tick={chartAxisTickStyle} tickLine={false} axisLine={false} width={48} tickFormatter={valueFormatter} />
            </>
          )}
          <Tooltip
            cursor={{ fill: "var(--color-surface-hover)" }}
            content={(tooltipProps) => (
              <ChartTooltipContent
                active={tooltipProps.active}
                payload={tooltipProps.payload as never}
                label={tooltipProps.label as string | number | undefined}
                labelFormatter={(label) => categoryFormatter(label)}
                valueFormatter={valueFormatter}
                seriesLabels={seriesLabels}
                seriesColors={seriesColors}
                keyShape="square"
              />
            )}
          />
          {series.map((seriesItem, seriesIndex) => (
            <Bar
              key={seriesItem.key}
              dataKey={seriesItem.key}
              stackId={stacked ? "stack" : undefined}
              fill={colors[seriesIndex]}
              radius={stacked ? 0 : [4, 4, 0, 0]}
              maxBarSize={36}
              isAnimationActive={false}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
