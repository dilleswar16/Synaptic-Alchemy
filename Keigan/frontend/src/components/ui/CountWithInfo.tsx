import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { formatNumber } from "@/utils/formatters";
import { Button } from "./Button";
import { Popover, PopoverClose } from "./Popover";

export interface CountWithInfoItem {
  key: string;
  label: ReactNode;
  /** Right-aligned detail (count, unit, status). */
  secondary?: ReactNode;
}

export interface CountWithInfoProps {
  count: number;
  /** Words after the number, e.g. "available". */
  label?: ReactNode;
  /** Popover heading. */
  title?: ReactNode;
  /** Top items shown in the popover. */
  items: CountWithInfoItem[];
  maximumItems?: number;
  /** Opens the full list (usually a Drawer). */
  onViewAll?: () => void;
  className?: string;
}

/** "27 available ⓘ": a number whose info popover lists the top items and links to the full list. */
export function CountWithInfo({ count, label, title, items, maximumItems = 5, onViewAll, className }: CountWithInfoProps) {
  const { t } = useTranslation("common");
  const shownItems = items.slice(0, maximumItems);
  const hiddenItemCount = Math.max(0, count - shownItems.length);
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <span className="font-semibold tabular-numbers text-default">{formatNumber(count)}</span>
      {label ? <span className="text-muted">{label}</span> : null}
      <Popover
        width="md"
        isFlush
        aria-label={typeof title === "string" ? title : undefined}
        trigger={
          <button
            type="button"
            aria-label={t("actions.showDetails")}
            className="grid size-6 place-items-center rounded-full text-subtle transition-colors hover:bg-surface-hover hover:text-action"
          >
            <Info aria-hidden="true" size={15} strokeWidth={2} />
          </button>
        }
      >
        {title ? <p className="border-b border-hairline px-4 py-3 text-body-sm font-semibold text-default">{title}</p> : null}
        <ul className="max-h-64 overflow-y-auto py-1.5">
          {shownItems.map((item) => (
            <li key={item.key} className="flex items-center justify-between gap-3 px-4 py-1.5 text-body-sm">
              <span className="min-w-0 truncate text-default">{item.label}</span>
              {item.secondary ? <span className="shrink-0 text-caption text-muted tabular-numbers">{item.secondary}</span> : null}
            </li>
          ))}
          {hiddenItemCount > 0 ? <li className="px-4 py-1.5 text-caption text-muted">{t("countWithInfo.moreItems", { count: hiddenItemCount })}</li> : null}
        </ul>
        {onViewAll ? (
          <div className="border-t border-hairline px-2 py-2">
            <PopoverClose asChild>
              <Button variant="ghost" size="sm" fullWidth onClick={onViewAll} className="justify-start text-action">
                {t("actions.viewAll")}
              </Button>
            </PopoverClose>
          </div>
        ) : null}
      </Popover>
    </span>
  );
}
