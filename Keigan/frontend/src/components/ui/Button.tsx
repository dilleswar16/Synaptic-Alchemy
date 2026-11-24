import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { LoaderCircle } from "lucide-react";
import { Slot } from "radix-ui";
import { cn } from "@/utils/cn";

export type ButtonVariant = "primary" | "secondary" | "subtle" | "ghost" | "danger" | "gradient-outline";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ComponentProps<"button"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Icon before the label; replaced by a spinner while `isLoading`. */
  leadingIcon?: LucideIcon;
  trailingIcon?: LucideIcon;
  isLoading?: boolean;
  fullWidth?: boolean;
  /** Render the single child element (e.g. a router `<Link>`) with button styling. */
  asChild?: boolean;
  children?: ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-action text-on-action shadow-xs hover:bg-action-hover active:bg-action-pressed",
  secondary: "border border-control bg-surface text-default shadow-xs hover:bg-surface-hover active:bg-surface-sunken",
  subtle: "bg-action-subtle text-action-subtle-text hover:bg-action-subtle-hover active:bg-action-subtle-hover",
  ghost: "bg-transparent text-default hover:bg-surface-hover active:bg-surface-sunken",
  danger: "bg-danger-fill text-white shadow-xs hover:brightness-95 active:brightness-90",
  "gradient-outline":
    "gradient-border text-action-subtle-text shadow-xs hover:[--gradient-border-fill:var(--color-surface-hover)] active:[--gradient-border-fill:var(--color-surface-sunken)]",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-[var(--button-h-sm,2rem)] gap-1.5 px-[var(--button-px-sm,0.75rem)] text-[length:var(--button-text-sm,var(--text-body-sm))]",
  md: "h-[var(--button-h-md,2.5rem)] gap-2 px-[var(--button-px-md,1rem)] text-[length:var(--button-text-md,var(--text-body))]",
  lg: "h-[var(--button-h-lg,3rem)] gap-2 px-[var(--button-px-lg,1.25rem)] text-[length:var(--button-text-lg,var(--text-body))]",
};

const iconSizes: Record<ButtonSize, number> = { sm: 16, md: 18, lg: 18 };

/** Button styles without the component, for links styled as buttons outside `asChild`. */
export function buttonClassName(variant: ButtonVariant = "primary", size: ButtonSize = "md", fullWidth = false): string {
  return cn(
    "inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap rounded-[var(--radius-button,var(--radius-sm))] font-[weight:var(--button-weight,600)]",
    "transition-[background-color,box-shadow,color,filter] duration-150",
    "disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50",
    variantClasses[variant],
    sizeClasses[size],
    fullWidth && "w-full",
  );
}

export function Button({
  variant = "primary",
  size = "md",
  leadingIcon: LeadingIcon,
  trailingIcon: TrailingIcon,
  isLoading = false,
  fullWidth = false,
  asChild = false,
  disabled,
  className,
  children,
  type,
  ...buttonProps
}: ButtonProps) {
  const iconSize = iconSizes[size];
  const leadingVisual = isLoading ? (
    <LoaderCircle aria-hidden="true" size={iconSize} className="keigan-spinner animate-spin" />
  ) : LeadingIcon ? (
    <LeadingIcon aria-hidden="true" size={iconSize} strokeWidth={1.75} />
  ) : null;
  const trailingVisual = TrailingIcon ? <TrailingIcon aria-hidden="true" size={iconSize} strokeWidth={1.75} /> : null;

  if (asChild) {
    return (
      <Slot.Root className={cn(buttonClassName(variant, size, fullWidth), className)} {...buttonProps}>
        {children}
      </Slot.Root>
    );
  }

  return (
    <button
      type={type ?? "button"}
      className={cn(buttonClassName(variant, size, fullWidth), className)}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...buttonProps}
    >
      {leadingVisual}
      {children}
      {trailingVisual}
    </button>
  );
}
