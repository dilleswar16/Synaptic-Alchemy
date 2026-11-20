import { Check, CircleExclamationPoint, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { formatTime, type DateInput } from "@/utils/formatters";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export interface SaveIndicatorProps {
  status: SaveStatus;
  /** When the last successful save happened ("Saved 10:42"). */
  savedAt?: DateInput | null;
  onRetry?: () => void;
  className?: string;
}

/** Autosave feedback: "Saving…", "Saved 10:42 ✓", "Couldn't save — Retry" (doc 04 §5). */
export function SaveIndicator({ status, savedAt, onRetry, className }: SaveIndicatorProps) {
  const { t } = useTranslation("common");
  return (
    <span role="status" aria-live="polite" className={cn("inline-flex min-h-6 items-center gap-1.5 text-caption", className)}>
      {status === "saving" ? (
        <>
          <LoaderCircle aria-hidden="true" size={14} className="keigan-spinner animate-spin text-muted" />
          <span className="text-muted">{t("saveIndicator.saving")}</span>
        </>
      ) : null}
      {status === "saved" ? (
        <>
          <span className="text-muted">{savedAt ? t("saveIndicator.savedAt", { time: formatTime(savedAt) }) : t("saveIndicator.saved")}</span>
          <Check aria-hidden="true" size={14} strokeWidth={2.5} className="text-success" />
        </>
      ) : null}
      {status === "error" ? (
        <>
          <CircleExclamationPoint aria-hidden="true" size={14} strokeWidth={2} className="text-danger" />
          <span className="text-danger">{t("saveIndicator.failed")}</span>
          {onRetry ? (
            <>
              <span aria-hidden="true" className="text-subtle">
                —
              </span>
              <button type="button" onClick={onRetry} className="font-semibold text-action underline-offset-2 hover:underline">
                {t("saveIndicator.retry")}
              </button>
            </>
          ) : null}
        </>
      ) : null}
    </span>
  );
}
