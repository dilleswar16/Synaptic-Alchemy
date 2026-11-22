import { useTranslation } from "react-i18next";
import { useRawOutput } from "@/api/investigationsApi";
import { Banner } from "@/components/ui/Banner";
import { Dialog } from "@/components/ui/Dialog";
import { Skeleton } from "@/components/ui/Skeleton";

interface RawOutputDialogProps {
  investigationId: string;
  traceStepId: string | null;
  onClose: () => void;
}

/** The model's answer before Keigan's checks, as escaped text: no markdown, no links, no copy button, so nothing in it can be run by accident. Application admins only. */
export function RawOutputDialog({ investigationId, traceStepId, onClose }: RawOutputDialogProps) {
  const { t } = useTranslation("investigations");
  const rawOutput = useRawOutput(investigationId, traceStepId);
  return (
    <Dialog open={traceStepId !== null} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }} title={t("trace.rawDialog.title")} size="lg">
      <div className="flex flex-col gap-3">
        <Banner tone="warning">{t("trace.rawDialog.warning")}</Banner>
        {rawOutput.isPending ? <Skeleton className="h-40" aria-label={t("trace.rawDialog.loading")} /> : null}
        {rawOutput.isError ? <Banner tone="danger">{t("trace.rawDialog.error")}</Banner> : null}
        {rawOutput.data ? (
          <>
            {rawOutput.data.isTruncated ? <p className="text-caption text-muted">{t("trace.rawDialog.truncated")}</p> : null}
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md border border-hairline bg-surface-sunken p-3 font-mono text-caption select-text">{JSON.stringify(rawOutput.data.rawOutput, null, 2)}</pre>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
