import { Hash } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { StatTile } from "@/components/ui/StatTile";
import { formatDateTime, formatList, formatNumber } from "@/utils/formatters";
import { SeriesCharts } from "./SeriesCharts";
import { toolBlockMaximumHeights } from "./toolBlockHeights";
import { readSeriesModels } from "./toolSeriesModels";
import { asRecordArray, asText, fieldLabel, formatFieldValue } from "./toolValues";

/**
 * The result of a log query: the query that ran, the number (`total`), the pattern over time when one was asked for (`series`) and up to ten sample
 * rows. The total and the series are the query's own figures; they are shown as sent, never recomputed here.
 */
export function QueryResultOutput({ record }: { record: Record<string, unknown> }) {
  const { t } = useTranslation("chat");
  const { t: translateOnboarding } = useTranslation("onboarding");
  const queryText = typeof record.query_text === "string" ? record.query_text : "";
  const queryLanguage = typeof record.query_language === "string" ? record.query_language : "";
  const rowCount = typeof record.row_count === "number" ? record.row_count : 0;
  const total = typeof record.total === "number" ? record.total : null;
  const series = readSeriesModels(record);
  const sampleRows = asRecordArray(record.sample_rows);
  const columnNames = Object.keys(sampleRows[0] ?? {});
  const columns: Array<DataTableColumn<{ rowId: string; cells: Record<string, unknown> }>> = columnNames.map((columnName) => ({
    key: columnName,
    header: fieldLabel(t, columnName),
    cell: (row) => formatFieldValue(t, row.cells[columnName]),
  }));
  const metaParts: string[] = [
    t("message.queryMeta", {
      service: record.service_name,
      source: translateOnboarding(`logSource.kinds.${String(record.source_kind)}`, { defaultValue: String(record.source_kind ?? "") }),
      language: queryLanguage.toUpperCase(),
      count: rowCount,
    }),
    ...(typeof record.time_range_start === "string" && typeof record.time_range_end === "string" ? [t("tool.timeRange", { start: formatDateTime(record.time_range_start), end: formatDateTime(record.time_range_end) })] : []),
  ];
  return (
    <div className="flex flex-col gap-2">
      <p className="text-caption break-words text-muted">{formatList(metaParts)}</p>
      {queryText ? <CommandBlock commands={queryText} title={queryLanguage.toUpperCase()} maximumHeight={toolBlockMaximumHeights.code} wrapLines /> : null}
      {total === null ? null : <StatTile size="compact" icon={Hash} iconTone="brand" label={fieldLabel(t, "total")} value={formatNumber(total)} />}
      <SeriesCharts models={series} title={asText(record.summary)} />
      {sampleRows.length > 0 ? (
        <DataTable
          caption={t("tool.sampleRows")}
          columns={columns}
          rows={sampleRows.map((cells, rowIndex) => ({ rowId: String(rowIndex), cells }))}
          getRowId={(row) => row.rowId}
          density="dense"
          maximumHeight={toolBlockMaximumHeights.sampleRows}
          isFlush
        />
      ) : null}
    </div>
  );
}
