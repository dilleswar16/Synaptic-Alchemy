import { useTranslation } from "react-i18next";
import type { ToolPresentation } from "@/api/askKeiganApi";
import { Badge } from "@/components/ui/Badge";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { KeyValueList, type KeyValueItem } from "@/components/ui/KeyValueList";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { cn } from "@/utils/cn";
import { formatDateTime, formatList, formatPercentage } from "@/utils/formatters";
import { GraphOutput } from "./GraphOutput";
import { MetricsOutput } from "./MetricsOutput";
import { toolBlockMaximumHeights } from "./toolBlockHeights";
import { readGraphModel, readMetricGroups } from "./toolOutputModels";
import { asRecord, asRecordArray, fieldLabel, formatFieldValue, isScalar } from "./toolValues";

/** Fields every tool output carries for the engine and the card header; the result view does not repeat them. */
const envelopeFieldNames: ReadonlySet<string> = new Set(["summary", "records", "item_count", "total_count", "is_truncated", "is_simulated"]);
/** The first of these that an item has becomes its title in a list. */
const itemTitleFieldNames = ["title", "name", "label", "summary", "description"] as const;

export interface ToolOutputViewProps {
  presentation: ToolPresentation;
  /** The tool's output as the server sent it: an object, or text when it was cut at the preview limit. */
  output: unknown;
  isCompact?: boolean;
  className?: string;
}

function RecordOutput({ record, isCompact }: { record: Record<string, unknown>; isCompact: boolean }) {
  const { t } = useTranslation("chat");
  const items: KeyValueItem[] = Object.entries(record)
    .filter(([fieldName, value]) => !envelopeFieldNames.has(fieldName) && !(Array.isArray(value) && value.length === 0))
    .map(([fieldName, value]) => ({ key: fieldName, label: fieldLabel(t, fieldName), value: <span className="whitespace-pre-wrap">{formatFieldValue(t, value)}</span> }));
  return items.length > 0 ? <KeyValueList items={items} dense layout={isCompact ? "stacked" : "columns"} /> : null;
}

function RecordListOutput({ items }: { items: Array<Record<string, unknown>> }) {
  const { t } = useTranslation("chat");
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, itemIndex) => {
        const titleFieldName = itemTitleFieldNames.find((fieldName) => typeof item[fieldName] === "string" && item[fieldName] !== "");
        const detailFieldNames = Object.keys(item).filter((fieldName) => fieldName !== titleFieldName && isScalar(item[fieldName]) && item[fieldName] !== null && item[fieldName] !== "");
        return (
          <li key={itemIndex} className="rounded-md border border-hairline bg-surface-sunken px-3 py-2">
            {titleFieldName ? <p className="text-body-sm font-medium break-words text-default">{String(item[titleFieldName])}</p> : null}
            <p className="text-caption break-words text-muted">
              {formatList(detailFieldNames.map((fieldName) => t("tool.fieldPair", { label: fieldLabel(t, fieldName), value: formatFieldValue(t, item[fieldName]) })))}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

/** How well a passage fits the question, as a percentage; the tool sends a score between 0 and 1. */
function matchPercentage(passage: Record<string, unknown>): string | null {
  return typeof passage.match_score === "number" ? formatPercentage(passage.match_score * 100, { maximumFractionDigits: 0 }) : null;
}

function PassageItem({ passage }: { passage: Record<string, unknown> }) {
  const { t } = useTranslation("chat");
  const match = matchPercentage(passage);
  return (
    <article className="rounded-md border border-hairline bg-surface-sunken px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 text-caption font-semibold break-words text-default">
          {formatList([passage.document_title, passage.section_heading].filter((part): part is string => typeof part === "string" && part !== ""))}
        </p>
        {match ? <Badge tone="neutral">{t("tool.passages.match", { percentage: match })}</Badge> : null}
      </div>
      {typeof passage.text === "string" ? <MarkdownView content={passage.text} className="mt-1" /> : null}
    </article>
  );
}

function PassagesOutput({ record, passages }: { record: Record<string, unknown>; passages: Array<Record<string, unknown>> }) {
  const topologySummary = typeof record.topology_summary === "string" ? record.topology_summary : null;
  return (
    <div className="flex flex-col gap-3">
      {topologySummary ? <p className="text-body-sm break-words text-muted">{topologySummary}</p> : null}
      {passages.map((passage, passageIndex) => <PassageItem key={passageIndex} passage={passage} />)}
    </div>
  );
}

function QueryResultOutput({ record }: { record: Record<string, unknown> }) {
  const { t } = useTranslation("chat");
  const { t: translateOnboarding } = useTranslation("onboarding");
  const queryText = typeof record.query_text === "string" ? record.query_text : "";
  const queryLanguage = typeof record.query_language === "string" ? record.query_language : "";
  const rowCount = typeof record.row_count === "number" ? record.row_count : 0;
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

/**
 * The result of a tool call, by how its tool says it should be shown (spec 8.3). Every value is drawn as text or as sanitised Markdown,
 * never as HTML. Presentations without a view of their own yet (series) and outputs of an unexpected shape fall back to a plain list of
 * the output's fields, so a new tool needs no change here.
 */
export function ToolOutputView({ presentation, output, isCompact = false, className }: ToolOutputViewProps) {
  const record = asRecord(output);
  if (typeof output === "string") {
    return <pre className={cn("max-h-48 overflow-auto rounded-md bg-surface-sunken p-3 font-mono text-code break-words whitespace-pre-wrap text-default", className)}>{output}</pre>;
  }
  if (!record) {
    return null;
  }
  const listItems = asRecordArray(record.items);
  const passages = asRecordArray(record.passages);
  let view;
  if (presentation === "record_list" && listItems.length > 0) {
    view = <RecordListOutput items={listItems} />;
  } else if (presentation === "passages" && passages.length > 0) {
    view = <PassagesOutput record={record} passages={passages} />;
  } else if (presentation === "query_result" && typeof record.query_text === "string") {
    view = <QueryResultOutput record={record} />;
  } else if (presentation === "metrics" && readMetricGroups(record).length > 0) {
    view = <MetricsOutput output={record} />;
  } else if (presentation === "graph" && readGraphModel(record) !== null) {
    view = <GraphOutput output={record} />;
  } else {
    view = <RecordOutput record={record} isCompact={isCompact} />;
  }
  return <div className={className}>{view}</div>;
}
