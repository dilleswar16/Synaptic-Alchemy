import type { ReactNode } from "react";
import type { ChartTableData } from "./ChartFrame";

/** Builds the "View as table" rows for a chart whose data is an array of records keyed by `categoryKey`. */
export function buildSeriesTable(
  categoryHeader: string,
  categoryKey: string,
  data: ReadonlyArray<Record<string, unknown>>,
  series: ReadonlyArray<{ key: string; label: string }>,
  formatCategory: (category: string | number) => ReactNode,
  formatValue: (value: number) => string,
): ChartTableData {
  return {
    columns: [
      { key: "category", header: categoryHeader },
      ...series.map((seriesItem) => ({ key: seriesItem.key, header: seriesItem.label, align: "end" as const })),
    ],
    rows: data.map((datum, rowIndex) => {
      const row: Record<string, ReactNode> = {
        __rowKey: rowIndex,
        category: formatCategory(datum[categoryKey] as string | number),
      };
      for (const seriesItem of series) {
        const value = datum[seriesItem.key];
        row[seriesItem.key] = typeof value === "number" ? formatValue(value) : "–";
      }
      return row;
    }),
  };
}
