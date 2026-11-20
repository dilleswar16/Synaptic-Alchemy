import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { Tooltip } from "./Tooltip";

/** Copies text, falling back to a hidden textarea where the async clipboard API is unavailable (plain http). */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path.
  }
  const temporaryTextarea = document.createElement("textarea");
  temporaryTextarea.value = text;
  temporaryTextarea.setAttribute("readonly", "");
  temporaryTextarea.style.position = "fixed";
  temporaryTextarea.style.opacity = "0";
  document.body.appendChild(temporaryTextarea);
  temporaryTextarea.select();
  const isCopied = document.execCommand("copy");
  temporaryTextarea.remove();
  return isCopied;
}

export interface CopyButtonProps {
  /** Text to copy, or a function returning it at click time. */
  value: string | (() => string);
  /** Accessible label and tooltip; defaults to "Copy". */
  label?: string;
  /** Show the label next to the icon. */
  showLabel?: boolean;
  size?: "sm" | "md";
  /** `onDark` for code surfaces. */
  variant?: "ghost" | "secondary" | "onDark";
  className?: string;
}

/** Copy with a 2-second "Copied" confirmation (announced to screen readers). */
export function CopyButton({ value, label, showLabel = false, size = "sm", variant = "ghost", className }: CopyButtonProps) {
  const { t } = useTranslation("common");
  const [isCopied, setIsCopied] = useState(false);
  const resetTimeoutRef = useRef<number | undefined>(undefined);
  const buttonLabel = label ?? t("actions.copy");

  useEffect(() => () => window.clearTimeout(resetTimeoutRef.current), []);

  const handleCopy = async () => {
    const isSuccessful = await copyTextToClipboard(typeof value === "function" ? value() : value);
    if (isSuccessful) {
      setIsCopied(true);
      window.clearTimeout(resetTimeoutRef.current);
      resetTimeoutRef.current = window.setTimeout(() => setIsCopied(false), 2000);
    }
  };

  const Icon = isCopied ? Check : Copy;
  const button = (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={showLabel ? undefined : buttonLabel}
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-sm font-medium transition-colors",
        size === "sm" ? "h-8 min-w-8 px-2 text-caption" : "h-9 min-w-9 px-2.5 text-body-sm",
        variant === "ghost" && "text-muted hover:bg-surface-hover hover:text-default",
        variant === "secondary" && "border border-control bg-surface text-default hover:bg-surface-hover",
        variant === "onDark" && "text-white/70 hover:bg-white/10 hover:text-white",
        isCopied && (variant === "onDark" ? "text-[#B6DA6E] hover:text-[#B6DA6E]" : "text-success hover:text-success"),
        className,
      )}
    >
      <Icon aria-hidden="true" size={size === "sm" ? 15 : 16} strokeWidth={2} />
      {showLabel ? <span>{isCopied ? t("actions.copied") : buttonLabel}</span> : null}
      <span aria-live="polite" className="sr-only">
        {isCopied ? t("actions.copied") : ""}
      </span>
    </button>
  );
  return showLabel ? button : <Tooltip content={isCopied ? t("actions.copied") : buttonLabel}>{button}</Tooltip>;
}
