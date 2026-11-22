import { asRecordArray } from "./toolValues";

/**
 * Reading the numbers over time of a tool output (the `series` of a log query, the `points` of a history or health tool). The output is the tool's JSON,
 * so the reader checks the shape and keeps only what a chart can draw; an output without such a list yields no model and the card shows its fields instead.
 */

/** One point of a series: the time or category it stands for and one number per field (a field with no value at that point is absent). */
export type SeriesRow = Record<string, string | number>;

/** What the x values are: moments (a line over time), days (a line over dates) or names (bars). */
export type SeriesXKind = "datetime" | "date" | "category";

/** The unit a field is in, from its name: charts never mix units on one axis (a percentage and an event count are drawn apart). */
export type SeriesFieldKind = "percentage" | "number" | "count";

export interface SeriesModel {
  /** The field of the output the rows were read from. */
  sourceFieldName: string;
  /** The field of every row that holds its time or category. */
  xKey: string;
  xKind: SeriesXKind;
  fieldKind: SeriesFieldKind;
  /** The numeric fields of this unit, in the order the output lists them: one line or bar series each. */
  valueFieldNames: string[];
  rows: SeriesRow[];
}

/** What a person needs to read a series without the chart: how many points, over what span, and where it went. */
export interface SeriesFieldSummary {
  fieldName: string;
  pointCount: number;
  firstX: string;
  lastX: string;
  minimum: number;
  maximum: number;
  latest: number;
}

const timeFieldNames = ["timestamp", "time", "date", "day", "bucket_start", "period_start", "recorded_at", "occurred_at"] as const;
const dateTimePattern = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const datePattern = /^\d{4}-\d{2}-\d{2}$/;
/** The order the charts of one output are drawn in. */
const fieldKindOrder: readonly SeriesFieldKind[] = ["percentage", "number", "count"];

export function seriesFieldKind(fieldName: string): SeriesFieldKind {
  if (fieldName.endsWith("_percentage")) {
    return "percentage";
  }
  return fieldName.endsWith("_count") ? "count" : "number";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** The field every row names its x value in: a known time field, else the first text field. Null when the rows have none. */
function findXKey(records: Array<Record<string, unknown>>): string | null {
  const first = records[0];
  if (!first) {
    return null;
  }
  return timeFieldNames.find((fieldName) => typeof first[fieldName] === "string") ?? Object.keys(first).find((fieldName) => typeof first[fieldName] === "string") ?? null;
}

function xKindOf(xValues: readonly string[]): SeriesXKind {
  if (xValues.every((x) => dateTimePattern.test(x))) {
    return "datetime";
  }
  return xValues.every((x) => datePattern.test(x)) ? "date" : "category";
}

/** One model for each unit among the numeric fields of the list in `sourceFieldName`, or none when it is not a list a chart can draw. */
function readModels(sourceFieldName: string, records: Array<Record<string, unknown>>): SeriesModel[] {
  const xKey = findXKey(records);
  if (xKey === null) {
    return [];
  }
  const pointRecords = records.filter((record) => typeof record[xKey] === "string");
  const numericFieldNames: string[] = [];
  for (const record of pointRecords) {
    for (const [fieldName, value] of Object.entries(record)) {
      if (fieldName !== xKey && isNumber(value) && !numericFieldNames.includes(fieldName)) {
        numericFieldNames.push(fieldName);
      }
    }
  }
  const xKind = xKindOf(pointRecords.map((record) => String(record[xKey])));
  return fieldKindOrder.flatMap((fieldKind): SeriesModel[] => {
    const valueFieldNames = numericFieldNames.filter((fieldName) => seriesFieldKind(fieldName) === fieldKind);
    const rows = pointRecords.flatMap((record): SeriesRow[] => {
      const row: SeriesRow = { [xKey]: String(record[xKey]) };
      for (const fieldName of valueFieldNames) {
        const value = record[fieldName];
        if (isNumber(value)) {
          row[fieldName] = value;
        }
      }
      return Object.keys(row).length > 1 ? [row] : [];
    });
    return rows.length === 0 ? [] : [{ sourceFieldName, xKey, xKind, fieldKind, valueFieldNames, rows }];
  });
}

/**
 * The charts of a tool output: from the list in `preferredFieldName` when it holds one, otherwise from the first list of records that has an x field and a
 * numeric field (a series tool may name its list as it likes). One model for each unit of number the list carries. Empty when the output has no list a chart can draw.
 */
export function readSeriesModels(output: Record<string, unknown>, preferredFieldName = "series"): SeriesModel[] {
  const candidateNames = [preferredFieldName, ...Object.keys(output).filter((fieldName) => fieldName !== preferredFieldName)];
  for (const fieldName of candidateNames) {
    const models = readModels(fieldName, asRecordArray(output[fieldName]));
    if (models.length > 0) {
      return models;
    }
  }
  return [];
}

/** The output without the list that was drawn as charts, so its other fields can be listed beside them. */
export function withoutSeries(output: Record<string, unknown>, models: readonly SeriesModel[]): Record<string, unknown> {
  const drawnFieldName = models[0]?.sourceFieldName;
  return Object.fromEntries(Object.entries(output).filter(([fieldName]) => fieldName !== drawnFieldName));
}

/** Count, span, lowest, highest and latest of each numeric field; a field that has no value in any row has no summary. */
export function summariseSeries(model: SeriesModel): SeriesFieldSummary[] {
  return model.valueFieldNames.flatMap((fieldName): SeriesFieldSummary[] => {
    const points = model.rows.flatMap((row) => {
      const value = row[fieldName];
      return isNumber(value) ? [{ x: String(row[model.xKey]), value }] : [];
    });
    const first = points[0];
    const last = points.at(-1);
    if (!first || !last) {
      return [];
    }
    const values = points.map((point) => point.value);
    return [{ fieldName, pointCount: points.length, firstX: first.x, lastX: last.x, minimum: Math.min(...values), maximum: Math.max(...values), latest: last.value }];
  });
}
