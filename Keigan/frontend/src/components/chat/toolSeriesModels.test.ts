import { describe, expect, it } from "vitest";
import { readSeriesModels, seriesFieldKind, summariseSeries, withoutSeries } from "./toolSeriesModels";

const logQuery = {
  summary: "312 failed requests on claims-api in the last 24 hours",
  total: 312,
  series: [
    { timestamp: "2026-11-21T10:00:00+00:00", value: 4 },
    { timestamp: "2026-11-21T11:00:00+00:00", value: 18 },
    { timestamp: "2026-11-21T12:00:00+00:00", value: 7 },
  ],
};

const sloHistory = {
  summary: "SLO history over 7 days",
  sli_name: "Claim submission availability",
  points: [
    { timestamp: "2026-11-20T00:00:00Z", sli_percentage: 99.9, budget_remaining_percentage: 80, good_event_count: 999, total_event_count: 1000 },
    { timestamp: "2026-11-21T00:00:00Z", sli_percentage: null, budget_remaining_percentage: null, good_event_count: 0, total_event_count: 0 },
    { timestamp: "2026-11-22T00:00:00Z", sli_percentage: 99.5, budget_remaining_percentage: 40, good_event_count: 995, total_event_count: 1000 },
  ],
};

describe("readSeriesModels", () => {
  it("reads the series of a log query as one numeric field over time", () => {
    expect(readSeriesModels(logQuery)).toEqual([
      {
        sourceFieldName: "series",
        xKey: "timestamp",
        xKind: "datetime",
        fieldKind: "number",
        valueFieldNames: ["value"],
        rows: [
          { timestamp: "2026-11-21T10:00:00+00:00", value: 4 },
          { timestamp: "2026-11-21T11:00:00+00:00", value: 18 },
          { timestamp: "2026-11-21T12:00:00+00:00", value: 7 },
        ],
      },
    ]);
  });

  it("finds a list a series tool names as it likes, and gives every numeric field its own series", () => {
    const [model] = readSeriesModels({ summary: "30 days", points: [{ day: "2026-11-20", health_score: 91, slo_component: 40.5 }, { day: "2026-11-21", health_score: 88, slo_component: 39 }] });
    expect(model).toMatchObject({ sourceFieldName: "points", xKey: "day", xKind: "date", valueFieldNames: ["health_score", "slo_component"] });
  });

  it("draws percentages and event counts apart, so two units never share an axis, and skips a point that has no value for a unit", () => {
    const models = readSeriesModels(sloHistory);
    expect(models.map((model) => [model.fieldKind, model.valueFieldNames])).toEqual([
      ["percentage", ["sli_percentage", "budget_remaining_percentage"]],
      ["count", ["good_event_count", "total_event_count"]],
    ]);
    expect(models[0]?.rows).toHaveLength(2);
    expect(models[1]?.rows).toHaveLength(3);
  });

  it("draws bars for names, and a line for moments and for days", () => {
    expect(readSeriesModels({ series: [{ label: "claims-api", value: 3 }, { label: "payments-api", value: 5 }] })[0]?.xKind).toBe("category");
    expect(readSeriesModels(logQuery)[0]?.xKind).toBe("datetime");
  });

  it("leaves out a field that has no value at a point, and keeps the point", () => {
    const [model] = readSeriesModels({ series: [{ timestamp: "2026-11-21T10:00:00Z", value: 1, other: 2 }, { timestamp: "2026-11-21T11:00:00Z", value: 3 }] });
    expect(model?.rows[1]).toEqual({ timestamp: "2026-11-21T11:00:00Z", value: 3 });
  });

  it("gives no model for an output without a list a chart can draw", () => {
    expect(readSeriesModels({ summary: "x", total: 3, series: [] })).toEqual([]);
    expect(readSeriesModels({ series: [{ timestamp: "2026-11-21T10:00:00Z" }] })).toEqual([]);
    expect(readSeriesModels({ series: [{ value: 1 }] })).toEqual([]);
    expect(readSeriesModels({ series: "not a list" })).toEqual([]);
  });
});

describe("seriesFieldKind", () => {
  it("tells the unit of a field from its name", () => {
    expect(seriesFieldKind("sli_percentage")).toBe("percentage");
    expect(seriesFieldKind("total_event_count")).toBe("count");
    expect(seriesFieldKind("health_score")).toBe("number");
  });
});

describe("withoutSeries", () => {
  it("drops only the list that was drawn", () => {
    const models = readSeriesModels(logQuery);
    expect(withoutSeries(logQuery, models)).toEqual({ summary: logQuery.summary, total: 312 });
  });
});

describe("summariseSeries", () => {
  it("gives the count, the span, the lowest, the highest and the latest value of each field", () => {
    const [model] = readSeriesModels(logQuery);
    expect(model && summariseSeries(model)).toEqual([
      { fieldName: "value", pointCount: 3, firstX: "2026-11-21T10:00:00+00:00", lastX: "2026-11-21T12:00:00+00:00", minimum: 4, maximum: 18, latest: 7 },
    ]);
  });

  it("counts only the points a field has a value at", () => {
    const [model] = readSeriesModels({ series: [{ timestamp: "2026-11-21T10:00:00Z", value: 1, other: 2 }, { timestamp: "2026-11-21T11:00:00Z", value: 3 }] });
    const other = model && summariseSeries(model).find((summary) => summary.fieldName === "other");
    expect(other).toMatchObject({ pointCount: 1, latest: 2 });
  });
});
