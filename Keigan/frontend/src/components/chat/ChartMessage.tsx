import { useTranslation } from "react-i18next";
import { BarChart, DonutChart, TimeSeriesChart, chartToneColors } from "@/components/charts";
import type { ChartSpecification } from "@/api/chatApi";
import { formatDateTime, formatNumber, formatTime } from "@/utils/formatters";
import { cn } from "@/utils/cn";

export interface ChartMessageProps {
  specification: ChartSpecification;
  className?: string;
}

/** Colour tokens in a chart specification are semantic (`danger`, `success` …); unknown tokens fall back to the categorical palette. */
function seriesColor(colorToken: string | undefined): string | undefined {
  if (!colorToken) return undefined;
  if (colorToken === "primary") return chartToneColors.brand;
  return colorToken in chartToneColors ? chartToneColors[colorToken as keyof typeof chartToneColors] : undefined;
}

function formatTimeLabel(value: string | number, isLongRange: boolean): string {
  return isLongRange ? formatDateTime(value, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : formatTime(value);
}

/** Renders the AI chart specification (doc 05 §7) in a bordered card with an accessible "view as table" toggle. */
export function ChartMessage({ specification, className }: ChartMessageProps) {
  const { t } = useTranslation("chat");
  const { chartType, rows, series, xField, xFieldKind, unit, title } = specification;
  const isTime = xFieldKind === "time";
  const firstTime = isTime && rows.length ? new Date(String(rows.at(0)?.[xField])).getTime() : 0;
  const lastTime = isTime && rows.length ? new Date(String(rows.at(-1)?.[xField])).getTime() : 0;
  const isLongRange = lastTime - firstTime > 2 * 86_400_000;
  const valueFormatter = (value: number) => (unit && unit !== "count" ? `${formatNumber(value)} ${unit}` : formatNumber(value));
  const chartSeries = series.map((entry) => ({ key: entry.field, label: entry.label, color: seriesColor(entry.colorToken) }));

  let chart;
  if (chartType === "table") {
    chart = (
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-body-sm">
          <thead>
            <tr className="text-left text-caption text-muted">
              <th className="py-1 pr-3 font-medium">{xField}</th>
              {series.map((entry) => <th key={entry.field} className="py-1 pr-3 text-right font-medium">{entry.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-t border-hairline">
                <td className="py-1 pr-3">{isTime ? formatTimeLabel(String(row[xField]), isLongRange) : String(row[xField])}</td>
                {series.map((entry) => <td key={entry.field} className="py-1 pr-3 text-right tabular-nums">{formatNumber(Number(row[entry.field] ?? 0))}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  } else if (chartType === "pie") {
    chart = <DonutChart ariaLabel={title} size={180} slices={rows.map((row) => ({ key: String(row[xField]), label: String(row[xField]), value: Number(row[series[0]?.field ?? ""] ?? 0) }))} valueFormatter={valueFormatter} />;
  } else if (chartType === "bar" || chartType === "stacked_bar") {
    chart = (
      <BarChart
        ariaLabel={title} data={rows} series={chartSeries} categoryKey={xField} stacked={chartType === "stacked_bar"} height={220} valueFormatter={valueFormatter}
        categoryFormatter={(value) => (isTime ? formatDateTime(value, { month: "short", day: "numeric", ...(isLongRange ? {} : { hour: "2-digit" }) }) : String(value))}
      />
    );
  } else {
    chart = (
      <TimeSeriesChart
        ariaLabel={title} data={rows} xKey={xField} height={220} valueFormatter={valueFormatter} xFormatter={(value) => (isTime ? formatTimeLabel(value, isLongRange) : String(value))}
        series={chartSeries.map((entry) => ({ ...entry, showArea: chartType === "area" }))}
      />
    );
  }
  return (
    <figure className={cn("rounded-lg border border-hairline bg-surface p-4", className)}>
      <figcaption className="mb-2 text-body-sm font-semibold text-default">{title}</figcaption>
      {rows.length === 0 ? <p className="text-body-sm text-muted">{t("message.noData")}</p> : chart}
    </figure>
  );
}
