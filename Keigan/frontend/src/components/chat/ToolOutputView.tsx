import { useTranslation } from "react-i18next";
import type { ToolPresentation } from "@/api/askKeiganApi";
import { Badge } from "@/components/ui/Badge";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { cn } from "@/utils/cn";
import { formatList, formatPercentage } from "@/utils/formatters";
import { GraphOutput } from "./GraphOutput";
import { MetricsOutput } from "./MetricsOutput";
import { QueryResultOutput } from "./QueryResultOutput";
import { RecordListOutput } from "./RecordListOutput";
import { RecordOutput } from "./RecordOutput";
import { SeriesOutput } from "./SeriesOutput";
import { readGraphModel, readMetricGroups } from "./toolOutputModels";
import { readSeriesModels } from "./toolSeriesModels";
import { asRecord, asRecordArray } from "./toolValues";

export interface ToolOutputViewProps {
  presentation: ToolPresentation;
  /** The tool's output as the server sent it: an object, or text when it was cut at the preview limit. */
  output: unknown;
  isCompact?: boolean;
  className?: string;
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

/**
 * The result of a tool call, by how its tool says it should be shown (spec 8.3). Every value is drawn as text or as sanitised Markdown,
 * never as HTML. Outputs of an unexpected shape fall back to a plain list of the output's fields, so a new tool needs no change here.
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
  const series = presentation === "series" ? readSeriesModels(record) : [];
  let view;
  if (presentation === "record_list" && listItems.length > 0) {
    view = <RecordListOutput items={listItems} />;
  } else if (presentation === "passages" && passages.length > 0) {
    view = <PassagesOutput record={record} passages={passages} />;
  } else if (presentation === "query_result" && typeof record.query_text === "string") {
    view = <QueryResultOutput record={record} />;
  } else if (series.length > 0) {
    view = <SeriesOutput record={record} models={series} isCompact={isCompact} />;
  } else if (presentation === "metrics" && readMetricGroups(record).length > 0) {
    view = <MetricsOutput output={record} />;
  } else if (presentation === "graph" && readGraphModel(record) !== null) {
    view = <GraphOutput output={record} />;
  } else {
    view = <RecordOutput record={record} isCompact={isCompact} />;
  }
  return <div className={className}>{view}</div>;
}
