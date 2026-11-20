import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { formatNumber } from "@/utils/formatters";
import { ChartFrame } from "./ChartFrame";

export interface HeatmapAxisItem {
  key: string;
  label: string;
}

export interface HeatmapGridProps {
  rows: HeatmapAxisItem[];
  columns: HeatmapAxisItem[];
  /** Value for a cell, or null/undefined for "no data". */
  getValue: (rowKey: string, columnKey: string) => number | null | undefined;
  valueFormatter?: (value: number) => string;
  /**
   * Cell fill for a value. Default: sequential Blue 1 wash from `minimumValue` to `maximumValue`.
   * Pass a custom function for status colouring (e.g. SLO compliance below target → danger).
   */
  colorForValue?: (value: number, rowKey: string) => string;
  minimumValue?: number;
  maximumValue?: number;
  /** Show the value inside each cell (otherwise only in the tooltip / table view). */
  showValues?: boolean;
  ariaLabel: string;
  className?: string;
}

/** Rows × columns grid (applications × days). Cells carry the value in a title and the table view, so colour is never the only signal. */
export function HeatmapGrid({
  rows,
  columns,
  getValue,
  valueFormatter = (value) => formatNumber(value, { maximumFractionDigits: 2 }),
  colorForValue,
  minimumValue = 0,
  maximumValue = 100,
  showValues = false,
  ariaLabel,
  className,
}: HeatmapGridProps) {
  const { t } = useTranslation("common");
  if (rows.length === 0 || columns.length === 0) {
    return <p className="py-10 text-center text-body-sm text-muted">{t("chart.noData")}</p>;
  }
  const resolveColor =
    colorForValue ??
    ((value: number) => {
      const ratio = Math.min(1, Math.max(0, (value - minimumValue) / (maximumValue - minimumValue || 1)));
      return `color-mix(in srgb, var(--chart-1) ${Math.round(12 + ratio * 78)}%, var(--color-surface))`;
    });

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      className={className}
      tableData={{
        columns: [{ key: "row", header: t("chart.category") }, ...columns.map((column) => ({ key: column.key, header: column.label, align: "end" as const }))],
        rows: rows.map((row) => {
          const tableRow: Record<string, ReactNode> = { __rowKey: row.key, row: row.label };
          for (const column of columns) {
            const value = getValue(row.key, column.key);
            tableRow[column.key] = typeof value === "number" ? valueFormatter(value) : "–";
          }
          return tableRow;
        }),
      }}
    >
      <div className="overflow-x-auto">
        <div className="grid gap-1" style={{ gridTemplateColumns: `minmax(120px,180px) repeat(${columns.length}, minmax(28px, 1fr))` }}>
          <span />
          {columns.map((column) => (
            <span key={column.key} className="truncate text-center text-caption text-muted">
              {column.label}
            </span>
          ))}
          {rows.map((row) => (
            <div key={row.key} className="contents">
              <span className="truncate pr-2 text-body-sm text-default" title={row.label}>
                {row.label}
              </span>
              {columns.map((column) => {
                const value = getValue(row.key, column.key);
                const hasValue = typeof value === "number" && Number.isFinite(value);
                return (
                  <span
                    key={column.key}
                    title={`${row.label} · ${column.label}: ${hasValue ? valueFormatter(value) : t("chart.noValue")}`}
                    className="flex h-8 items-center justify-center rounded-xs border border-hairline text-micro tabular-numbers text-default"
                    style={{ backgroundColor: hasValue ? resolveColor(value, row.key) : "var(--color-surface-sunken)" }}
                  >
                    {showValues && hasValue ? valueFormatter(value) : null}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </ChartFrame>
  );
}
