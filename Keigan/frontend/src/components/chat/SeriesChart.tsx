import { useTranslation } from "react-i18next";
import { BarChart, TimeSeriesChart } from "@/components/charts";
import { formatDate, formatDateTime, formatNumber, formatPercentage, formatTime, toDate } from "@/utils/formatters";
import { seriesFieldKind, summariseSeries, type SeriesModel } from "./toolSeriesModels";
import { fieldLabel } from "./toolValues";

/** Height of the chart inside a card or a drawer. */
const chartHeight = 220;
/** A series over more than this many days labels its axis with the date as well as the time. */
const longRangeDays = 2;
const millisecondsPerDay = 86_400_000;
const numberFractionDigits = 2;
const percentageFractionDigits = 2;

const isPercentageField = (fieldName: string) => seriesFieldKind(fieldName) === "percentage";
const formatNumberValue = (value: number) => formatNumber(value, { maximumFractionDigits: numberFractionDigits });
const formatPercentageValue = (value: number) => formatPercentage(value, { maximumFractionDigits: percentageFractionDigits });

function isLongRange(model: SeriesModel): boolean {
  const first = toDate(String(model.rows[0]?.[model.xKey]));
  const last = toDate(String(model.rows.at(-1)?.[model.xKey]));
  return first !== null && last !== null && last.getTime() - first.getTime() > longRangeDays * millisecondsPerDay;
}

export interface SeriesChartProps {
  model: SeriesModel;
  /** The chart's accessible name: what the numbers are (the tool's own summary); a general name when the tool sent none. */
  title: string | undefined;
}

/**
 * A tool's numbers over time as a line (or as bars when the x values are names) with its legend and "View as table", and under it the same numbers in
 * words (how many points, over what span, lowest, highest and latest), so the chart is never the only way to read them. Colours come from the chart
 * theme; every series has a name in the legend and the table, so colour is never the only signal.
 */
export function SeriesChart({ model, title }: SeriesChartProps) {
  const { t } = useTranslation("chat");
  const chartTitle = title ?? t("tool.series.untitled");
  const isLong = isLongRange(model);
  // The axis shows the time alone when the series spans a day or two; the words always say the day too, so "from 7:25 PM to 7:25 PM" cannot happen.
  // A day (no time of day) is written in UTC: it names a calendar day, which a time zone must not move.
  const formatMoment = (value: string | number) => {
    if (model.xKind === "datetime") {
      return formatDateTime(value, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    }
    return model.xKind === "date" ? formatDate(value, { month: "short", day: "numeric", timeZone: "UTC" }) : String(value);
  };
  const formatX = (value: string | number) => (model.xKind === "datetime" && !isLong ? formatTime(value) : formatMoment(value));
  const areAllPercentages = model.valueFieldNames.every(isPercentageField);
  const formatValue = areAllPercentages ? formatPercentageValue : formatNumberValue;
  const series = model.valueFieldNames.map((fieldName) => ({ key: fieldName, label: fieldLabel(t, fieldName) }));
  const summaries = summariseSeries(model);
  const describe = (summary: (typeof summaries)[number]) => {
    const format = isPercentageField(summary.fieldName) ? formatPercentageValue : formatNumberValue;
    const text = t("tool.series.summary", {
      count: summary.pointCount,
      start: formatMoment(summary.firstX),
      end: formatMoment(summary.lastX),
      minimum: format(summary.minimum),
      maximum: format(summary.maximum),
      latest: format(summary.latest),
    });
    return summaries.length > 1 ? t("tool.fieldPair", { label: fieldLabel(t, summary.fieldName), value: text }) : text;
  };

  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-md border border-hairline bg-surface p-3">
      {model.xKind === "category" ? (
        <BarChart ariaLabel={chartTitle} data={model.rows} series={series} categoryKey={model.xKey} height={chartHeight} categoryFormatter={formatX} valueFormatter={formatValue} />
      ) : (
        <TimeSeriesChart ariaLabel={chartTitle} data={model.rows} series={series} xKey={model.xKey} height={chartHeight} xFormatter={formatX} valueFormatter={formatValue} />
      )}
      <ul className="flex flex-col gap-0.5 text-caption break-words text-muted">
        {summaries.map((summary) => <li key={summary.fieldName}>{describe(summary)}</li>)}
      </ul>
    </div>
  );
}
