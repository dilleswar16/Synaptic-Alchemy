import type { ReactNode } from "react";
import { Link } from "react-router";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/utils/cn";
import { toneSoftClasses, type StatusTone } from "./toneStyles";

export interface StatTileProps {
  icon: LucideIcon;
  iconTone?: StatusTone;
  label: ReactNode;
  /** Big number (already formatted). */
  value: ReactNode;
  /** Delta or secondary line ("+3 since yesterday"). */
  secondaryText?: ReactNode;
  secondaryTone?: "default" | "positive" | "negative";
  /** Optional trend, e.g. `<Sparkline values={…} />`. */
  trend?: ReactNode;
  /** Makes the whole tile a link. */
  to?: string;
  /** `compact` is for tiles inside another card (a tool result): less padding, a 32 px icon and the small KPI size. */
  size?: "default" | "compact";
  className?: string;
}

const secondaryClasses = { default: "text-muted", positive: "text-success", negative: "text-danger" } as const;

/** KPI tile: tinted icon, label, big tabular number, optional delta and sparkline; the whole tile can be a link. */
export function StatTile({ icon: Icon, iconTone = "brand", label, value, secondaryText, secondaryTone = "default", trend, to, size = "default", className }: StatTileProps) {
  const isCompact = size === "compact";
  const tileClassName = cn(
    "flex min-w-0 items-start rounded-md border border-hairline bg-surface shadow-xs",
    isCompact ? "gap-3 p-3" : "gap-4 p-5",
    to && "transition-[box-shadow,transform] duration-150 hover:-translate-y-px hover:shadow-md focus-visible:outline-2 focus-visible:outline-action",
    className,
  );
  const content = (
    <>
      <span className={cn("grid shrink-0 place-items-center", isCompact ? "size-8 rounded-md" : "size-10 rounded-[10px]", toneSoftClasses[iconTone])}>
        <Icon aria-hidden="true" size={isCompact ? 16 : 20} strokeWidth={1.75} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className={cn("text-muted", isCompact ? "text-caption" : "text-body-sm")}>{label}</span>
        <span className={cn("font-display tabular-numbers text-default", isCompact ? "text-kpi-sm" : "text-kpi")}>{value}</span>
        {secondaryText ? <span className={cn("text-caption", secondaryClasses[secondaryTone])}>{secondaryText}</span> : null}
      </span>
      {trend ? <span className="self-end">{trend}</span> : null}
    </>
  );
  return to ? (
    <Link to={to} className={tileClassName}>
      {content}
    </Link>
  ) : (
    <div className={tileClassName}>{content}</div>
  );
}
