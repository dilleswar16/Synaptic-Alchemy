import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStepOutput, type ToolPresentation } from "@/api/askKeiganApi";
import { Button } from "@/components/ui/Button";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { toolBlockMaximumHeights } from "./toolBlockHeights";
import { ToolOutputView } from "./ToolOutputView";

export interface ToolOutputDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  answerRunId: string;
  runStepId: string;
  /** Tool label, for the title. */
  title: string;
  /** Tool name, for the name of the downloaded file. */
  toolName: string;
  /** How the tool's result is drawn above the raw JSON. */
  presentation: ToolPresentation;
  /** The tool's citation code, for the name of the downloaded file. */
  citationCode: string | null;
}

/** How long the object URL of a download stays valid after the click: the browser reads it asynchronously, so revoking it at once can cancel the download. */
const downloadUrlLifetimeMilliseconds = 10_000;

function downloadJson(fileName: string, jsonText: string): void {
  const downloadUrl = URL.createObjectURL(new Blob([jsonText], { type: "application/json" }));
  const downloadLink = document.createElement("a");
  downloadLink.href = downloadUrl;
  downloadLink.download = fileName;
  downloadLink.click();
  window.setTimeout(() => URL.revokeObjectURL(downloadUrl), downloadUrlLifetimeMilliseconds);
}

/** The full stored output of one tool call, and the exact text Keigan's AI received for it (spec 8.3). Loaded when the drawer opens. */
export function ToolOutputDrawer({ open, onOpenChange, answerRunId, runStepId, title, toolName, presentation, citationCode }: ToolOutputDrawerProps) {
  const { t } = useTranslation("chat");
  const stepOutput = useStepOutput(answerRunId, runStepId, open);
  const outputJson = stepOutput.data ? JSON.stringify(stepOutput.data.output, null, 2) : "";
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={t("drawer.title", { label: title })}
      headerActions={
        outputJson ? (
          <Button variant="secondary" size="sm" leadingIcon={Download} onClick={() => downloadJson(`${toolName}${citationCode ? `-${citationCode}` : ""}.json`, outputJson)}>
            {t("tool.downloadOutput")}
          </Button>
        ) : null
      }
    >
      {stepOutput.isLoading ? <Skeleton className="h-48 w-full" /> : null}
      {stepOutput.isError ? <ErrorState error={stepOutput.error} onRetry={() => void stepOutput.refetch()} isRetrying={stepOutput.isFetching} /> : null}
      {stepOutput.data ? (
        <div className="flex flex-col gap-4">
          {stepOutput.data.outputIsTruncated ? <p className="text-body-sm text-muted">{t("drawer.storedTruncated")}</p> : null}
          <section aria-label={t("tool.result")} className="flex flex-col gap-2">
            <h3 className="text-caption font-semibold text-muted">{t("tool.result")}</h3>
            <ToolOutputView presentation={presentation} output={stepOutput.data.output} />
          </section>
          <CommandBlock commands={outputJson} title={t("drawer.outputHeading")} maximumHeight={toolBlockMaximumHeights.fullOutput} wrapLines={false} />
          <details className="rounded-md border border-hairline bg-surface-sunken px-4 py-3">
            <summary className="cursor-pointer text-body-sm font-semibold text-default">{t("tool.modelView")}</summary>
            <p className="mt-2 text-caption text-muted">{t("drawer.modelViewHint")}</p>
            <p className="mt-2 font-mono text-caption break-all text-muted">{t("drawer.sha256", { hash: stepOutput.data.modelViewSha256 })}</p>
            <CommandBlock commands={stepOutput.data.modelViewText} className="mt-2" maximumHeight={toolBlockMaximumHeights.modelView} wrapLines />
          </details>
        </div>
      ) : null}
    </Drawer>
  );
}
