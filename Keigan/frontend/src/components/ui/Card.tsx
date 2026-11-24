import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/utils/cn";
import { toneSoftClasses, type StatusTone } from "./toneStyles";

export interface CardProps extends ComponentProps<"div"> {
  /** Hover lift (shadow-md, −1 px) for clickable cards. */
  interactive?: boolean;
  /** 20 px padding instead of 24 px. */
  dense?: boolean;
  /** Larger radius (16 px) for panels and hero cards. */
  radius?: "md" | "lg" | "xl";
  /** 3 px brand-gradient stripe on top (e.g. the leading hypothesis). */
  accent?: boolean;
}

const radiusClasses = { md: "rounded-md", lg: "rounded-lg", xl: "rounded-xl" } as const;

/**
 * Surface card: border, radius 12, shadow-xs. Compose with `CardHeader`, `CardBody`, `CardFooter`, which share the
 * card's padding (24 px, or 20 px when `dense`).
 */
export function Card({ interactive = false, dense = false, radius = "md", accent = false, className, children, ...divProps }: CardProps) {
  return (
    <div
      data-dense={dense || undefined}
      className={cn(
        "relative flex min-w-0 flex-col border border-hairline bg-surface shadow-xs [--card-padding:var(--card-padding-base,1.5rem)] data-[dense]:[--card-padding:var(--card-padding-dense,1.25rem)]",
        radiusClasses[radius],
        interactive &&
          "cursor-pointer transition-[box-shadow,transform] duration-150 ease-[var(--ease-standard)] hover:-translate-y-px hover:shadow-md focus-within:shadow-md",
        accent && "overflow-hidden before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:bg-gradient-brand",
        className,
      )}
      {...divProps}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps extends Omit<ComponentProps<"div">, "title"> {
  title: ReactNode;
  description?: ReactNode;
  /** Right-aligned actions (buttons, menus). */
  actions?: ReactNode;
  /** Optional 40 px icon tile before the title. */
  icon?: LucideIcon;
  iconTone?: StatusTone;
  /** Heading element for the title; defaults to h3. */
  titleAs?: "h2" | "h3" | "h4";
}

export function CardHeader({ title, description, actions, icon: Icon, iconTone = "brand", titleAs: TitleElement = "h3", className, ...divProps }: CardHeaderProps) {
  return (
    <div
      data-card-header=""
      className={cn("flex items-start gap-3 px-[var(--card-padding)] pt-[var(--card-padding)] pb-4", className)}
      {...divProps}
    >
      {Icon ? (
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-[10px]", toneSoftClasses[iconTone])}>
          <Icon aria-hidden="true" size={20} strokeWidth={1.75} />
        </span>
      ) : null}
      <div className="min-w-0 flex-1">
        <TitleElement className="font-display text-h3 text-default">{title}</TitleElement>
        {description ? <p className="mt-0.5 text-body-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...divProps }: ComponentProps<"div">) {
  return (
    <div
      className={cn("min-w-0 flex-1 p-[var(--card-padding)] [[data-card-header]+&]:pt-0", className)}
      {...divProps}
    />
  );
}

export function CardFooter({ className, ...divProps }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end gap-2 border-t border-hairline px-[var(--card-padding)] py-4",
        className,
      )}
      {...divProps}
    />
  );
}
