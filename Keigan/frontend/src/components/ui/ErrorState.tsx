import type { ReactNode } from "react";
import { CloudOff, FileQuestionMark, RefreshCw, ShieldX, TriangleExclamationPoint } from "lucide-react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { cn } from "@/utils/cn";
import { Button } from "./Button";

export interface ErrorStateProps {
  /** The error from a query or mutation; ApiError status picks the message. */
  error?: unknown;
  title?: ReactNode;
  description?: ReactNode;
  onRetry?: () => void;
  isRetrying?: boolean;
  size?: "sm" | "md";
  className?: string;
}

/** Friendly error with retry and the correlation id for support. Use for failed queries in cards and pages. */
export function ErrorState({ error, title, description, onRetry, isRetrying = false, size = "md", className }: ErrorStateProps) {
  const { t } = useTranslation("common");
  const apiError = isApiError(error) ? error : null;

  let Icon = TriangleExclamationPoint;
  let defaultTitle = t("errors.genericTitle");
  let defaultDescription = t("errors.genericDescription");
  if (apiError?.isNetworkError) {
    Icon = CloudOff;
    defaultTitle = t("errors.networkTitle");
    defaultDescription = t("errors.networkDescription");
  } else if (apiError?.status === 403) {
    Icon = ShieldX;
    defaultTitle = t("errors.forbiddenTitle");
    defaultDescription = t("errors.forbiddenDescription");
  } else if (apiError?.status === 404) {
    Icon = FileQuestionMark;
    defaultTitle = t("errors.notFoundTitle");
    defaultDescription = t("errors.notFoundDescription");
  } else if (apiError?.status === 409) {
    defaultTitle = t("errors.conflictTitle");
    defaultDescription = t("errors.conflictDescription");
  }

  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center justify-center text-center", size === "sm" ? "gap-2 px-4 py-6" : "gap-3 px-6 py-12", className)}
    >
      <span aria-hidden="true" className={cn("grid place-items-center rounded-full bg-danger-soft text-danger", size === "sm" ? "size-10" : "size-14")}>
        <Icon size={size === "sm" ? 20 : 26} strokeWidth={1.75} />
      </span>
      <div className="flex max-w-md flex-col gap-1">
        <h3 className={cn("font-display text-default", size === "sm" ? "text-h4" : "text-h3")}>{title ?? defaultTitle}</h3>
        <p className="text-body-sm text-muted">{description ?? (apiError?.detail && !apiError.isNetworkError ? apiError.detail : defaultDescription)}</p>
        {apiError?.correlationId ? (
          <p className="font-mono text-micro font-normal text-subtle">{t("errors.reference", { correlationId: apiError.correlationId })}</p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" leadingIcon={RefreshCw} onClick={onRetry} isLoading={isRetrying}>
          {t("actions.retry")}
        </Button>
      ) : null}
    </div>
  );
}
