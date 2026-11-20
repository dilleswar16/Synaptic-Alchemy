import type { ComponentProps } from "react";
import type { LucideIcon } from "lucide-react";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/utils/cn";
import { Tooltip } from "./Tooltip";

export type IconButtonVariant = "ghost" | "secondary" | "subtle" | "primary";
export type IconButtonSize = "sm" | "md" | "lg";

export interface IconButtonProps extends Omit<ComponentProps<"button">, "children"> {
  icon: LucideIcon;
  /** Required: used as `aria-label` and as the tooltip text. */
  label: string;
  variant?: IconButtonVariant;
  /** sm 32 px · md 36 px · lg 40 px. */
  size?: IconButtonSize;
  showTooltip?: boolean;
  tooltipSide?: "top" | "right" | "bottom" | "left";
  isLoading?: boolean;
  /** Pressed state for toggles (sets `aria-pressed`). */
  isPressed?: boolean;
}

const variantClasses: Record<IconButtonVariant, string> = {
  ghost: "text-muted hover:bg-surface-hover hover:text-default active:bg-surface-sunken",
  secondary: "border border-strong bg-surface text-default shadow-xs hover:bg-surface-hover",
  subtle: "bg-action-subtle text-action-subtle-text hover:bg-action-subtle-hover",
  primary: "bg-action text-on-action hover:bg-action-hover active:bg-action-pressed",
};

const sizeClasses: Record<IconButtonSize, string> = { sm: "size-8", md: "size-9", lg: "size-10" };
const iconSizes: Record<IconButtonSize, number> = { sm: 16, md: 18, lg: 20 };

export function IconButton({
  icon: Icon,
  label,
  variant = "ghost",
  size = "md",
  showTooltip = true,
  tooltipSide = "bottom",
  isLoading = false,
  isPressed,
  className,
  disabled,
  type,
  ...buttonProps
}: IconButtonProps) {
  const button = (
    <button
      type={type ?? "button"}
      aria-label={label}
      aria-pressed={isPressed}
      aria-busy={isLoading || undefined}
      disabled={disabled || isLoading}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-sm transition-colors duration-150",
        "disabled:pointer-events-none disabled:opacity-50",
        isPressed && "bg-surface-selected text-action-subtle-text",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...buttonProps}
    >
      {isLoading ? (
        <LoaderCircle aria-hidden="true" size={iconSizes[size]} className="keigan-spinner animate-spin" />
      ) : (
        <Icon aria-hidden="true" size={iconSizes[size]} strokeWidth={1.75} />
      )}
    </button>
  );
  return (
    <Tooltip content={label} side={tooltipSide} disabled={!showTooltip}>
      {button}
    </Tooltip>
  );
}
