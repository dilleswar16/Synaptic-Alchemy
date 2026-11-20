import type { ReactNode } from "react";

export interface ChartTooltipEntry {
  name?: unknown;
  value?: unknown;
  color?: string;
  stroke?: string;
  fill?: string;
  dataKey?: unknown;
}

export interface ChartTooltipContentProps {
  active?: boolean;
  payload?: ReadonlyArray<ChartTooltipEntry>;
  label?: string | number;
  labelFormatter?: (label: string | number) => ReactNode;
  valueFormatter?: (value: number) => string;
  /** Map dataKey → display name (series labels). */
  seriesLabels?: Record<string, string>;
  /** Map dataKey → colour, when the payload colour is a gradient or missing. */
  seriesColors?: Record<string, string>;
  /** Key line (line charts) or square (bars, slices). */
  keyShape?: "line" | "square";
}

/**
 * Token-styled tooltip for Recharts: value first (strong), series name second, keyed with a short stroke of the
 * series colour. Pass as `<Tooltip content={(props) => <ChartTooltipContent {...props} … />} />`.
 */
export function ChartTooltipContent({
  active,
  payload,
  label,
  labelFormatter,
  valueFormatter = (value) => String(value),
  seriesLabels = {},
  seriesColors = {},
  keyShape = "line",
}: ChartTooltipContentProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  return (
    <div className="min-w-40 rounded-sm border border-hairline bg-surface px-3 py-2.5 shadow-md">
      {label !== undefined ? <p className="mb-1.5 text-caption text-muted">{labelFormatter ? labelFormatter(label) : label}</p> : null}
      <ul className="flex flex-col gap-1">
        {payload.map((entry, entryIndex) => {
          const dataKey = String(entry.dataKey ?? entry.name ?? entryIndex);
          const color = seriesColors[dataKey] ?? entry.color ?? entry.stroke ?? entry.fill ?? "var(--chart-1)";
          const numericValue = typeof entry.value === "number" ? entry.value : Number(entry.value);
          return (
            <li key={dataKey} className="flex items-center gap-2">
              {keyShape === "line" ? (
                <span aria-hidden="true" className="h-0.5 w-3 shrink-0 rounded-full" style={{ backgroundColor: color }} />
              ) : (
                <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: color }} />
              )}
              <span className="text-body-sm font-semibold tabular-numbers text-default">
                {Number.isFinite(numericValue) ? valueFormatter(numericValue) : String(entry.value ?? "")}
              </span>
              <span className="text-caption text-muted">{seriesLabels[dataKey] ?? String(entry.name ?? dataKey)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
