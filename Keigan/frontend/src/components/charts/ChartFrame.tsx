import { useState, type ReactNode } from "react";
import { ChartLine, Table } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";

export interface ChartLegendItem {
  key: string;
  label: ReactNode;
  color: string;
  /** Legend key mirrors the mark: a short line for lines, a square for bars / areas / slices. */
  shape?: "line" | "square" | "dashed";
}

export interface ChartTableColumn {
  key: string;
  header: string;
  align?: "start" | "end";
}

export interface ChartTableData {
  columns: ChartTableColumn[];
  rows: Array<Record<string, ReactNode>>;
}

export interface ChartFrameProps {
  /** Accessible name of the chart (also the table caption). */
  ariaLabel: string;
  /** Legend items; shown for two or more series. */
  legendItems?: ChartLegendItem[];
  /** Data for the "View as table" alternative (doc 04 §8). */
  tableData: ChartTableData;
  /** Extra controls on the right of the footer row. */
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function ChartLegend({ items, className }: { items: ChartLegendItem[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5", className)}>
      {items.map((item) => (
        <li key={item.key} className="inline-flex items-center gap-1.5 text-caption text-muted">
          {item.shape === "line" || item.shape === "dashed" ? (
            <svg aria-hidden="true" width="16" height="8" className="shrink-0">
              <line x1="1" y1="4" x2="15" y2="4" stroke={item.color} strokeWidth="2" strokeLinecap="round" strokeDasharray={item.shape === "dashed" ? "3 3" : undefined} />
            </svg>
          ) : (
            <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: item.color }} />
          )}
          <span className="text-default">{item.label}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Wraps every chart: the chart itself, its legend and a "View as table" toggle so data is never colour-only or
 * hover-only. Used by all chart components; feature code rarely needs it directly.
 */
export function ChartFrame({ ariaLabel, legendItems = [], tableData, toolbar, children, className }: ChartFrameProps) {
  const { t } = useTranslation("common");
  const [isTableView, setIsTableView] = useState(false);
  const showLegend = legendItems.length > 1 && !isTableView;

  const tableColumns: DataTableColumn<Record<string, ReactNode>>[] = tableData.columns.map((column) => ({
    key: column.key,
    header: column.header,
    align: column.align,
    cell: (row) => row[column.key],
  }));

  return (
    <figure className={cn("keigan-chart flex min-w-0 flex-col gap-3", className)}>
      {isTableView ? (
        <DataTable
          columns={tableColumns}
          rows={tableData.rows}
          getRowId={(row) => String(row.__rowKey ?? JSON.stringify(Object.values(row).slice(0, 2)))}
          caption={ariaLabel}
          density="dense"
          maximumHeight="320px"
          pageSize={500}
        />
      ) : (
        <div role="img" aria-label={ariaLabel} className="min-w-0">
          {children}
        </div>
      )}
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {showLegend ? <ChartLegend items={legendItems} /> : <span />}
        <span className="flex items-center gap-2">
          {toolbar}
          <button
            type="button"
            onClick={() => setIsTableView((currentValue) => !currentValue)}
            aria-pressed={isTableView}
            className="inline-flex h-7 items-center gap-1.5 rounded-xs px-2 text-caption font-medium text-action transition-colors hover:bg-action-subtle"
          >
            {isTableView ? <ChartLine aria-hidden="true" size={14} /> : <Table aria-hidden="true" size={14} />}
            {isTableView ? t("chart.viewAsChart") : t("chart.viewAsTable")}
          </button>
        </span>
      </figcaption>
    </figure>
  );
}
