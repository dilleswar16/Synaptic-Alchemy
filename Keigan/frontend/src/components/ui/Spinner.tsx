import { LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";

export interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  /** Accessible label; defaults to "Loading…". */
  label?: string;
  className?: string;
}

const spinnerSizes = { sm: 14, md: 18, lg: 28 } as const;

/** Indeterminate loading indicator. Inherits the current text colour. */
export function Spinner({ size = "md", label, className }: SpinnerProps) {
  const { t } = useTranslation("common");
  return (
    <span role="status" className={cn("inline-flex items-center justify-center", className)}>
      <LoaderCircle aria-hidden="true" size={spinnerSizes[size]} strokeWidth={2} className="keigan-spinner animate-spin" />
      <span className="sr-only">{label ?? t("states.loading")}</span>
    </span>
  );
}
