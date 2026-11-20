import type { ReactNode } from "react";
import { cn } from "@/utils/cn";
import { CopyButton } from "./CopyButton";

export interface KeyValueItem {
  key: string;
  label: ReactNode;
  value: ReactNode;
  /** Caption under the value, e.g. the source env var name `SERVICENOW_BASE_URL`. */
  helperText?: ReactNode;
  /** Adds a copy button for this value. */
  copyValue?: string;
  isMonospace?: boolean;
}

export interface KeyValueListProps {
  items: KeyValueItem[];
  /** `columns`: label left / value right (default). `stacked`: label above value. */
  layout?: "columns" | "stacked";
  dense?: boolean;
  /** Hairlines between rows. */
  isDivided?: boolean;
  className?: string;
}

/** Description list for settings and identities (`<dl>`), with optional copy buttons (doc 04 §6.10). */
export function KeyValueList({ items, layout = "columns", dense = false, isDivided = true, className }: KeyValueListProps) {
  return (
    <dl className={cn("flex flex-col", isDivided && "divide-y divide-hairline", className)}>
      {items.map((item) => (
        <div
          key={item.key}
          className={cn(
            layout === "columns" ? "grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-1 sm:grid-cols-[minmax(160px,2fr)_5fr]" : "flex flex-col gap-1",
            dense ? "py-2" : "py-3",
            !isDivided && "py-1.5",
          )}
        >
          <dt className="min-w-0 pt-0.5 text-body-sm break-words text-muted">{item.label}</dt>
          <dd className="flex min-w-0 items-start gap-1">
            <div className="min-w-0 flex-1">
              <div className={cn("text-body break-words text-default", item.isMonospace && "font-mono text-code")}>{item.value}</div>
              {item.helperText ? <div className="mt-0.5 text-caption text-subtle">{item.helperText}</div> : null}
            </div>
            {item.copyValue ? <CopyButton value={item.copyValue} className="-my-1" /> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
