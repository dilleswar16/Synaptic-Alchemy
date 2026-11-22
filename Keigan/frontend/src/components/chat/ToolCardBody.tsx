import { useState } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStepOutput, type RunStepToolView } from "@/api/askKeiganApi";
import { Button } from "@/components/ui/Button";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { CopyButton } from "@/components/ui/CopyButton";
import { Skeleton } from "@/components/ui/Skeleton";
import { KeyValueList } from "@/components/ui/KeyValueList";
import type { ToolProgress } from "./answerStreamReducer";
import { toolBlockMaximumHeights } from "./toolBlockHeights";
import { ToolOutputView } from "./ToolOutputView";
import { ToolRecordLink } from "./ToolRecordLink";
import { asRecord, fieldLabel, formatFieldValue } from "./toolValues";

export interface ToolCardBodyProps {
  answerRunId: string;
  runStepId: string;
  tool: RunStepToolView;
  /** Latest `tool.progress` of this step, while it runs. */
  progress?: ToolProgress;
  isRunning: boolean;
  /** The stored output can be opened in full (the call succeeded and produced output). */
  canViewFullOutput: boolean;
  onViewFullOutput: () => void;
  /** Stacks label and value in the input list: the container is too narrow for two columns. */
  isCompact?: boolean;
}

/** What a tool card shows once opened (spec 8.3): the inputs, the result by presentation, and the actions: open in Keigan, the full output, copy. */
export function ToolCardBody({ answerRunId, runStepId, tool, progress, isRunning, canViewFullOutput, onViewFullOutput, isCompact = false }: ToolCardBodyProps) {
  const { t } = useTranslation("chat");
  const [isJsonView, setIsJsonView] = useState(false);
  const progressDetail = asRecord(progress?.detail);
  const progressQueryText = typeof progressDetail?.queryText === "string" ? progressDetail.queryText : null;
  const argumentEntries = Object.entries(tool.arguments);
  const argumentsJson = JSON.stringify(tool.arguments, null, 2);
  // A preview the server cut at its limit arrives as text (half a JSON document): the stored output is read instead, so the result still shows as numbers, a list or a map.
  const isPreviewCut = typeof tool.outputPreview === "string";
  const fullOutput = useStepOutput(answerRunId, runStepId, isPreviewCut && canViewFullOutput);
  const output = isPreviewCut && fullOutput.data ? fullOutput.data.output : tool.outputPreview;
  const outputText = output === null || output === undefined ? null : typeof output === "string" ? output : JSON.stringify(output, null, 2);
  const hasRecordLink = tool.target.records.length > 0;

  return (
    <div className="flex flex-col gap-4">
      {argumentEntries.length > 0 ? (
        <section aria-label={t("tool.inputs")} className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-caption font-semibold text-muted">{t("tool.inputs")}</h4>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="sm" onClick={() => setIsJsonView((value) => !value)} aria-pressed={isJsonView}>{isJsonView ? t("tool.viewList") : t("tool.viewJson")}</Button>
              <CopyButton value={argumentsJson} label={t("tool.copyInputs")} />
            </div>
          </div>
          {isJsonView ? (
            <CommandBlock commands={argumentsJson} maximumHeight={toolBlockMaximumHeights.code} wrapLines />
          ) : (
            <KeyValueList
              dense
              layout={isCompact ? "stacked" : "columns"}
              items={argumentEntries.map(([argumentName, argumentValue]) => ({
                key: argumentName,
                label: fieldLabel(t, argumentName, "arguments"),
                value: formatFieldValue(t, argumentValue),
                helperText: tool.boundArgumentNames.includes(argumentName) ? (
                  <span className="inline-flex items-center gap-1"><Lock aria-hidden="true" size={12} />{t("tool.boundArgument")}</span>
                ) : undefined,
              }))}
            />
          )}
        </section>
      ) : null}

      {isRunning && progressQueryText ? <CommandBlock commands={progressQueryText} maximumHeight={toolBlockMaximumHeights.progressQuery} wrapLines /> : null}

      {output !== null && output !== undefined ? (
        <section aria-label={t("tool.result")} className="flex flex-col gap-2">
          <h4 className="text-caption font-semibold text-muted">{t("tool.result")}</h4>
          {isPreviewCut && fullOutput.isLoading ? <Skeleton className="h-24 w-full" /> : <ToolOutputView presentation={tool.presentation} output={output} isCompact={isCompact} />}
        </section>
      ) : null}

      {hasRecordLink || canViewFullOutput || outputText ? (
        <div className="flex flex-wrap items-center gap-2">
          <ToolRecordLink records={tool.target.records} />
          {canViewFullOutput ? <Button variant="secondary" size="sm" onClick={onViewFullOutput}>{t("tool.viewFullOutput")}</Button> : null}
          {outputText ? <CopyButton value={outputText} label={t("tool.copyOutput")} showLabel variant="secondary" /> : null}
        </div>
      ) : null}
    </div>
  );
}
