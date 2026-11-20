import { Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";
import { formatNumber } from "@/utils/formatters";
import { ChartFrame, type ChartLegendItem } from "./ChartFrame";
import { chartAxisTickStyle, chartGridStroke, chartToneColors, resolveSeriesColor } from "./chartTheme";
import { ChartTooltipContent } from "./ChartTooltipContent";
import { buildSeriesTable } from "./chartUtilities";

export interface TimeSeriesSeries {
  /** Key of the numeric field in each data record. */
  key: string;
  label: string;
  /** CSS colour or tone token; defaults to the categorical slot for the series index. */
  color?: string;
  /** Soft area wash under the line (use for a single series such as error budget). */
  showArea?: boolean;
}

export interface TimeSeriesAnomaly {
  /** Value of the x field at the anomaly. */
  x: string | number;
  /** Value of the y field at the anomaly. */
  y: number;
}

export interface TimeSeriesChartProps {
  data: ReadonlyArray<Record<string, unknown>>;
  series: TimeSeriesSeries[];
  /** Field holding the x value (timestamp or label). Default "time". */
  xKey?: string;
  xFormatter?: (value: string | number) => string;
  valueFormatter?: (value: number) => string;
  /** Horizontal target line (SLO target), dashed green. */
  targetValue?: number;
  targetLabel?: string;
  anomalies?: TimeSeriesAnomaly[];
  yDomain?: [number | "auto", number | "auto"];
  height?: number;
  ariaLabel: string;
  className?: string;
}

/** Line / area chart over time with optional dashed target line and anomaly dots; includes legend and table view. */
export function TimeSeriesChart({
  data,
  series,
  xKey = "time",
  xFormatter = (value) => String(value),
  valueFormatter = (value) => formatNumber(value, { maximumFractionDigits: 2 }),
  targetValue,
  targetLabel,
  anomalies = [],
  yDomain,
  height = 260,
  ariaLabel,
  className,
}: TimeSeriesChartProps) {
  const { t } = useTranslation("common");
  if (data.length === 0) {
    return <p className="py-10 text-center text-body-sm text-muted">{t("chart.noData")}</p>;
  }
  const colors = series.map((seriesItem, seriesIndex) => resolveSeriesColor(seriesItem.color, seriesIndex));
  const legendItems: ChartLegendItem[] = series.map((seriesItem, seriesIndex) => ({
    key: seriesItem.key,
    label: seriesItem.label,
    color: colors[seriesIndex] ?? "var(--chart-1)",
    shape: "line",
  }));
  if (targetValue !== undefined) {
    legendItems.push({ key: "__target", label: targetLabel ?? t("chart.target"), color: chartToneColors.target, shape: "dashed" });
  }
  if (anomalies.length > 0) {
    legendItems.push({ key: "__anomaly", label: t("chart.anomaly"), color: chartToneColors.anomaly, shape: "square" });
  }
  const seriesLabels = Object.fromEntries(series.map((seriesItem) => [seriesItem.key, seriesItem.label]));
  const seriesColors = Object.fromEntries(series.map((seriesItem, seriesIndex) => [seriesItem.key, colors[seriesIndex] ?? ""]));

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      legendItems={legendItems}
      className={className}
      tableData={buildSeriesTable(t("chart.time"), xKey, data, series, (category) => xFormatter(category), valueFormatter)}
    >
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data as Array<Record<string, unknown>>} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={chartGridStroke} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={xKey} tick={chartAxisTickStyle} tickLine={false} axisLine={{ stroke: chartGridStroke }} tickFormatter={xFormatter} minTickGap={24} />
          <YAxis tick={chartAxisTickStyle} tickLine={false} axisLine={false} width={52} tickFormatter={valueFormatter} domain={yDomain ?? ["auto", "auto"]} />
          <Tooltip
            cursor={{ stroke: "var(--color-border-strong)" }}
            content={(tooltipProps) => (
              <ChartTooltipContent
                active={tooltipProps.active}
                payload={tooltipProps.payload as never}
                label={tooltipProps.label as string | number | undefined}
                labelFormatter={(label) => xFormatter(label)}
                valueFormatter={valueFormatter}
                seriesLabels={seriesLabels}
                seriesColors={seriesColors}
              />
            )}
          />
          {targetValue !== undefined ? <ReferenceLine y={targetValue} stroke={chartToneColors.target} strokeDasharray="5 4" strokeWidth={1.5} /> : null}
          {series.map((seriesItem, seriesIndex) =>
            seriesItem.showArea ? (
              <Area
                key={seriesItem.key}
                dataKey={seriesItem.key}
                type="monotone"
                stroke={colors[seriesIndex]}
                strokeWidth={2}
                fill={colors[seriesIndex]}
                fillOpacity={0.15}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ) : (
              <Line
                key={seriesItem.key}
                dataKey={seriesItem.key}
                type="monotone"
                stroke={colors[seriesIndex]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
                connectNulls
              />
            ),
          )}
          {anomalies.map((anomaly, anomalyIndex) => (
            <ReferenceDot key={`${anomaly.x}-${anomalyIndex}`} x={anomaly.x} y={anomaly.y} r={5} fill={chartToneColors.anomaly} stroke="var(--color-surface)" strokeWidth={2} ifOverflow="extendDomain" />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
