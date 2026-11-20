import { useMemo, useState, type CSSProperties, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { currentLocale, formatNumber } from "@/utils/formatters";
import { Checkbox } from "./Checkbox";
import { EmptyState } from "./EmptyState";
import { IconButton } from "./IconButton";
import { Skeleton } from "./Skeleton";

export type SortDirection = "ascending" | "descending";

export interface DataTableSort {
  columnKey: string;
  direction: SortDirection;
}

export interface DataTableColumn<Row> {
  key: string;
  header: ReactNode;
  cell: (row: Row, rowIndex: number) => ReactNode;
  /** Value used for client-side sorting. Columns with `sortValue` (or `isSortable` in manual mode) are sortable. */
  sortValue?: (row: Row) => string | number | Date | boolean | null | undefined;
  /** Force sortability in manual (server-side) sorting mode. */
  isSortable?: boolean;
  align?: "start" | "center" | "end";
  /** CSS width, e.g. "120px" or "20%". */
  width?: string;
  /** Keep the column visible while scrolling horizontally (use on the first column only). */
  isSticky?: boolean;
  headerClassName?: string;
  cellClassName?: string;
}

export interface DataTableServerPagination {
  page: number;
  pageSize: number;
  totalCount: number;
  onPageChange: (page: number) => void;
}

export interface DataTableProps<Row> {
  columns: DataTableColumn<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
  /** Accessible table caption (visually hidden). */
  caption: string;
  isLoading?: boolean;
  loadingRowCount?: number;
  /** Custom empty state (defaults to a generic one). */
  emptyState?: ReactNode;
  onRowClick?: (row: Row) => void;
  /** Selection (checkbox column appears when `onSelectedRowIdsChange` is set). */
  selectedRowIds?: ReadonlySet<string>;
  onSelectedRowIdsChange?: (selectedRowIds: Set<string>) => void;
  isRowSelectable?: (row: Row) => boolean;
  /** Controlled sort; omit for internal state. */
  sort?: DataTableSort | null;
  defaultSort?: DataTableSort;
  onSortChange?: (sort: DataTableSort | null) => void;
  /** Rows are already sorted by the server; headers only report `onSortChange`. */
  isManualSorting?: boolean;
  density?: "comfortable" | "dense";
  /** Constrains the height so the header sticks while the body scrolls. */
  maximumHeight?: string;
  /** Client-side page size (default 50). Ignored with `serverPagination`. */
  pageSize?: number;
  serverPagination?: DataTableServerPagination;
  rowClassName?: (row: Row) => string | undefined;
  /** Render without the outer card border (when already inside a Card). */
  isFlush?: boolean;
  /**
   * Below the `sm` breakpoint each row becomes a stacked card: the first column is the title, the others show their header as a label. This keeps every
   * column on a phone instead of hiding the right-hand ones behind a sideways scroll. `scroll` keeps the wide table (for matrices that only make sense as a grid).
   */
  mobileLayout?: "cards" | "scroll";
  className?: string;
}

type SortableValue = string | number | Date | boolean | null | undefined;

function compareSortValues(firstValue: SortableValue, secondValue: SortableValue, collator: Intl.Collator): number {
  const isFirstEmpty = firstValue === null || firstValue === undefined || firstValue === "";
  const isSecondEmpty = secondValue === null || secondValue === undefined || secondValue === "";
  if (isFirstEmpty || isSecondEmpty) {
    return isFirstEmpty === isSecondEmpty ? 0 : isFirstEmpty ? 1 : -1;
  }
  if (firstValue instanceof Date && secondValue instanceof Date) {
    return firstValue.getTime() - secondValue.getTime();
  }
  if (typeof firstValue === "number" && typeof secondValue === "number") {
    return firstValue - secondValue;
  }
  return collator.compare(String(firstValue), String(secondValue));
}

const alignClasses = { start: "text-left", center: "text-center", end: "text-right" } as const;
const isInteractiveTarget = (target: EventTarget | null) =>
  target instanceof Element && Boolean(target.closest("button, a, input, select, textarea, label, [role='checkbox'], [data-row-click-ignore]"));

/**
 * Generic table: real `<table>`, sunken 40 px header, 48 px rows (40 dense), hairline dividers, row hover, sortable
 * headers, selection checkboxes, sticky header (with `maximumHeight`) and optional sticky first column, loading
 * skeleton, empty state and pagination (client or server).
 */
export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  caption,
  isLoading = false,
  loadingRowCount = 6,
  emptyState,
  onRowClick,
  selectedRowIds,
  onSelectedRowIdsChange,
  isRowSelectable,
  sort,
  defaultSort,
  onSortChange,
  isManualSorting = false,
  density = "comfortable",
  maximumHeight,
  pageSize = 50,
  serverPagination,
  rowClassName,
  isFlush = false,
  mobileLayout = "cards",
  className,
}: DataTableProps<Row>) {
  const { t } = useTranslation("common");
  const [internalSort, setInternalSort] = useState<DataTableSort | null>(defaultSort ?? null);
  const [clientPage, setClientPage] = useState(1);
  const activeSort = sort === undefined ? internalSort : sort;
  const isSelectable = Boolean(onSelectedRowIdsChange);
  const selectedIds = selectedRowIds ?? new Set<string>();

  const sortedRows = useMemo(() => {
    if (isManualSorting || !activeSort) {
      return rows;
    }
    const sortColumn = columns.find((column) => column.key === activeSort.columnKey);
    if (!sortColumn?.sortValue) {
      return rows;
    }
    const collator = new Intl.Collator(currentLocale(), { numeric: true, sensitivity: "base" });
    const directionMultiplier = activeSort.direction === "ascending" ? 1 : -1;
    const getSortValue = sortColumn.sortValue;
    return [...rows].sort((firstRow, secondRow) => directionMultiplier * compareSortValues(getSortValue(firstRow), getSortValue(secondRow), collator));
  }, [rows, columns, activeSort, isManualSorting]);

  const totalCount = serverPagination?.totalCount ?? sortedRows.length;
  const currentPage = serverPagination?.page ?? clientPage;
  const effectivePageSize = serverPagination?.pageSize ?? pageSize;
  const pageCount = Math.max(1, Math.ceil(totalCount / effectivePageSize));
  const visibleRows = serverPagination
    ? sortedRows
    : sortedRows.slice((Math.min(currentPage, pageCount) - 1) * effectivePageSize, Math.min(currentPage, pageCount) * effectivePageSize);
  const showPagination = totalCount > effectivePageSize;

  const selectableRows = sortedRows.filter((row) => isRowSelectable?.(row) ?? true);
  const selectedSelectableCount = selectableRows.filter((row) => selectedIds.has(getRowId(row))).length;
  const headerCheckboxState =
    selectedSelectableCount === 0 ? false : selectedSelectableCount === selectableRows.length ? true : ("indeterminate" as const);

  const changePage = (nextPage: number) => {
    const boundedPage = Math.min(Math.max(1, nextPage), pageCount);
    if (serverPagination) {
      serverPagination.onPageChange(boundedPage);
    } else {
      setClientPage(boundedPage);
    }
  };

  const toggleSort = (columnKey: string) => {
    let nextSort: DataTableSort | null;
    if (activeSort?.columnKey !== columnKey) {
      nextSort = { columnKey, direction: "ascending" };
    } else if (activeSort.direction === "ascending") {
      nextSort = { columnKey, direction: "descending" };
    } else {
      nextSort = null;
    }
    if (sort === undefined) {
      setInternalSort(nextSort);
    }
    onSortChange?.(nextSort);
    setClientPage(1);
  };

  const toggleRowSelection = (rowId: string, isSelected: boolean) => {
    const nextSelectedIds = new Set(selectedIds);
    if (isSelected) {
      nextSelectedIds.add(rowId);
    } else {
      nextSelectedIds.delete(rowId);
    }
    onSelectedRowIdsChange?.(nextSelectedIds);
  };

  const toggleAllRows = (isSelected: boolean) => {
    const nextSelectedIds = new Set(selectedIds);
    for (const row of selectableRows) {
      if (isSelected) {
        nextSelectedIds.add(getRowId(row));
      } else {
        nextSelectedIds.delete(getRowId(row));
      }
    }
    onSelectedRowIdsChange?.(nextSelectedIds);
  };

  const handleRowClick = (mouseEvent: MouseEvent<HTMLTableRowElement>, row: Row) => {
    if (!onRowClick || isInteractiveTarget(mouseEvent.target)) {
      return;
    }
    onRowClick(row);
  };

  const handleRowKeyDown = (keyboardEvent: KeyboardEvent<HTMLTableRowElement>, row: Row) => {
    if (onRowClick && (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") && keyboardEvent.target === keyboardEvent.currentTarget) {
      keyboardEvent.preventDefault();
      onRowClick(row);
    }
  };

  const cellPadding = density === "dense" ? "px-3 py-2" : "px-4 py-3";
  const rowHeight = density === "dense" ? "h-10" : "h-12";
  const stickyCellClasses = "sticky left-0 z-[1] bg-surface group-hover:bg-surface-hover";
  const columnCount = columns.length + (isSelectable ? 1 : 0);
  const isStacked = mobileLayout === "cards";
  /** Columns a phone can sort by: sortable and with a text header to name the option. */
  const sortableColumns = columns.filter((column) => typeof column.header === "string" && (Boolean(column.sortValue) || (isManualSorting && column.isSortable)));
  const containerStyle: CSSProperties | undefined = maximumHeight ? { maxHeight: maximumHeight } : undefined;
  const pageStart = totalCount === 0 ? 0 : (currentPage - 1) * effectivePageSize + 1;
  const pageEnd = Math.min(currentPage * effectivePageSize, totalCount);

  return (
    <div className={cn("flex min-w-0 flex-col overflow-hidden bg-surface", !isFlush && "rounded-md border border-hairline shadow-xs", className)}>
      {isStacked && !isLoading && (isSelectable || sortableColumns.length > 0) ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline bg-surface-sunken px-4 py-2 sm:hidden">
          {isSelectable ? (
            <Checkbox label={t("dataTable.selectAllRows")} checked={headerCheckboxState} onCheckedChange={(checkedState) => toggleAllRows(checkedState === true)} disabled={selectableRows.length === 0} />
          ) : <span />}
          {sortableColumns.length > 0 ? (
            <label className="flex items-center gap-2 text-caption text-muted">
              {t("dataTable.sortLabel")}
              <select
                value={activeSort ? `${activeSort.columnKey}:${activeSort.direction}` : ""}
                onChange={(changeEvent) => {
                  const [columnKey, direction] = changeEvent.target.value.split(":");
                  const nextSort = columnKey ? { columnKey, direction: direction as SortDirection } : null;
                  if (sort === undefined) setInternalSort(nextSort);
                  onSortChange?.(nextSort);
                  setClientPage(1);
                }}
                className="rounded-sm border border-control bg-surface px-2 py-1 text-body-sm text-default"
              >
                <option value="">{t("dataTable.sortNone")}</option>
                {sortableColumns.flatMap((column) => [
                  <option key={`${column.key}:ascending`} value={`${column.key}:ascending`}>{column.header as string} ↑</option>,
                  <option key={`${column.key}:descending`} value={`${column.key}:descending`}>{column.header as string} ↓</option>,
                ])}
              </select>
            </label>
          ) : null}
        </div>
      ) : null}
      {/* A scrolling area must be reachable by keyboard, and says when it is loading. */}
      <div className="min-w-0 overflow-auto" style={containerStyle} tabIndex={0} role="region" aria-label={caption} aria-busy={isLoading || undefined}>
        <table className={cn("w-full border-separate border-spacing-0 text-body-sm", isStacked && "max-sm:block")}>
          <caption className="sr-only">{caption}</caption>
          <thead className={cn(isStacked && "max-sm:hidden")}>
            <tr>
              {isSelectable ? (
                <th scope="col" className="sticky top-0 z-[2] h-10 w-11 border-b border-hairline bg-surface-sunken px-4">
                  <Checkbox
                    aria-label={t("dataTable.selectAllRows")}
                    checked={headerCheckboxState}
                    onCheckedChange={(checkedState) => toggleAllRows(checkedState === true)}
                    disabled={selectableRows.length === 0}
                  />
                </th>
              ) : null}
              {columns.map((column) => {
                const isSortable = Boolean(column.sortValue) || (isManualSorting && column.isSortable);
                const isSorted = activeSort?.columnKey === column.key;
                const SortIcon = !isSorted ? ChevronsUpDown : activeSort?.direction === "ascending" ? ArrowUp : ArrowDown;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={isSorted ? activeSort?.direction : undefined}
                    style={column.width ? { width: column.width } : undefined}
                    className={cn(
                      "sticky top-0 z-[2] h-10 border-b border-hairline bg-surface-sunken text-caption font-semibold whitespace-nowrap text-muted",
                      density === "dense" ? "px-3" : "px-4",
                      alignClasses[column.align ?? "start"],
                      column.isSticky && "left-0 z-[3]",
                      column.headerClassName,
                    )}
                  >
                    {isSortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        aria-label={typeof column.header === "string" ? t("dataTable.sortBy", { column: column.header }) : undefined}
                        className={cn(
                          "-mx-1 inline-flex items-center gap-1 rounded-xs px-1 py-0.5 hover:text-default",
                          isSorted && "text-default",
                          column.align === "end" && "flex-row-reverse",
                        )}
                      >
                        {column.header}
                        <SortIcon aria-hidden="true" size={13} strokeWidth={2} className={cn(!isSorted && "opacity-50")} />
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className={cn(isStacked && "max-sm:block")}>
            {isLoading
              ? Array.from({ length: loadingRowCount }, (_, skeletonRowIndex) => (
                  <tr key={`skeleton-${skeletonRowIndex}`} className={cn(rowHeight, isStacked && "max-sm:block max-sm:h-auto")} aria-hidden="true">
                    {Array.from({ length: columnCount }, (_, skeletonCellIndex) => (
                      <td key={skeletonCellIndex} className={cn("border-b border-hairline", cellPadding, isStacked && "max-sm:block max-sm:border-b-0")}>
                        <Skeleton className={cn("h-3.5", skeletonCellIndex === 0 ? "w-3/4" : "w-1/2")} />
                      </td>
                    ))}
                  </tr>
                ))
              : visibleRows.map((row, rowIndex) => {
                  const rowId = getRowId(row);
                  const isSelected = selectedIds.has(rowId);
                  return (
                    <tr
                      key={rowId}
                      tabIndex={onRowClick ? 0 : undefined}
                      aria-selected={isSelectable ? isSelected : undefined}
                      onClick={(mouseEvent) => handleRowClick(mouseEvent, row)}
                      onKeyDown={(keyboardEvent) => handleRowKeyDown(keyboardEvent, row)}
                      className={cn(
                        "group transition-colors hover:bg-surface-hover focus-visible:outline-offset-[-3px]",
                        rowHeight,
                        isStacked && "max-sm:block max-sm:h-auto max-sm:border-b max-sm:border-hairline max-sm:py-2.5",
                        onRowClick && "cursor-pointer",
                        isSelected && "bg-surface-selected hover:bg-surface-selected",
                        rowClassName?.(row),
                      )}
                    >
                      {isSelectable ? (
                        <td className={cn("w-11 border-b border-hairline group-last:border-b-0", cellPadding, isStacked && "max-sm:block max-sm:border-b-0 max-sm:pb-0")}>
                          <Checkbox
                            aria-label={t("dataTable.selectRow")}
                            checked={isSelected}
                            disabled={!(isRowSelectable?.(row) ?? true)}
                            onCheckedChange={(checkedState) => toggleRowSelection(rowId, checkedState === true)}
                          />
                        </td>
                      ) : null}
                      {columns.map((column, columnIndex) => (
                        <td
                          key={column.key}
                          data-label={isStacked && columnIndex > 0 && typeof column.header === "string" ? column.header : undefined}
                          className={cn(
                            isStacked && "max-sm:flex max-sm:items-start max-sm:justify-between max-sm:gap-4 max-sm:border-b-0 max-sm:px-4 max-sm:py-1 max-sm:text-right",
                            isStacked && "max-sm:before:max-w-[45%] max-sm:before:shrink-0 max-sm:before:text-left max-sm:before:text-caption max-sm:before:text-muted max-sm:before:content-[attr(data-label)]",
                            isStacked && columnIndex === 0 && "max-sm:justify-start max-sm:text-left max-sm:font-semibold",
                            isStacked && column.isSticky && "max-sm:static",
                            "border-b border-hairline align-middle text-default group-last:border-b-0",
                            cellPadding,
                            alignClasses[column.align ?? "start"],
                            column.align === "end" && "tabular-numbers",
                            column.isSticky && stickyCellClasses,
                            column.isSticky && isSelected && "bg-surface-selected group-hover:bg-surface-selected",
                            column.cellClassName,
                          )}
                        >
                          {column.cell(row, rowIndex)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
          </tbody>
        </table>
        {!isLoading && visibleRows.length === 0 ? (
          <div className="border-t border-hairline">
            {emptyState ?? <EmptyState size="sm" title={t("dataTable.emptyTitle")} description={t("dataTable.emptyDescription")} />}
          </div>
        ) : null}
      </div>
      {(showPagination || (isSelectable && selectedIds.size > 0)) && !isLoading ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline px-4 py-2.5 text-body-sm text-muted">
          <span>{isSelectable && selectedIds.size > 0 ? t("dataTable.selectedCount", { count: selectedIds.size }) : null}</span>
          {showPagination ? (
            <div className="flex items-center gap-1">
              <span className="mr-2 tabular-numbers">
                {t("dataTable.pageSummary", { start: formatNumber(pageStart), end: formatNumber(pageEnd), total: formatNumber(totalCount) })}
              </span>
              <IconButton icon={ChevronLeft} label={t("dataTable.previousPage")} size="sm" disabled={currentPage <= 1} onClick={() => changePage(currentPage - 1)} />
              <IconButton icon={ChevronRight} label={t("dataTable.nextPage")} size="sm" disabled={currentPage >= pageCount} onClick={() => changePage(currentPage + 1)} />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
