import { describe, expect, it } from "vitest";
import { readMetricGroups } from "./toolOutputModels";

const statistic = (median: number | null, sampleCount: number) => ({ sample_count: sampleCount, median, p90: null, mean: null, excluded_count: 0 });

describe("readMetricGroups for the reliability tool", () => {
  const output = {
    summary: "Reliability over 30 days",
    items: [
      {
        application_code: "CLMJP",
        application_name: "Claims Processing (JP)",
        incidents_opened_count: 7,
        time_to_detect: statistic(300, 5),
        time_to_resolve: statistic(null, 0),
        share_correct: 80,
      },
    ],
  };

  it("titles a group that has no title of its own by its application, and does not repeat the application as context", () => {
    const [group] = readMetricGroups(output);
    expect(group).toMatchObject({ key: "CLMJP", titleParts: ["Claims Processing (JP)"], applicationName: null });
  });

  it("shows the median of a statistic as the number, in seconds for a time, with the cases it was worked out from", () => {
    const [group] = readMetricGroups(output);
    expect(group?.values.find((value) => value.fieldName === "time_to_detect")).toMatchObject({ kind: "duration", value: 300, sampleCount: 5 });
  });

  it("keeps a statistic with no value as an empty number, so the tile says there is nothing yet", () => {
    const [group] = readMetricGroups(output);
    expect(group?.values.find((value) => value.fieldName === "time_to_resolve")).toMatchObject({ kind: "duration", value: null });
  });

  it("writes the share correct as a percentage and a count as a plain number", () => {
    const [group] = readMetricGroups(output);
    expect(group?.values.find((value) => value.fieldName === "share_correct")?.kind).toBe("percentage");
    expect(group?.values.find((value) => value.fieldName === "incidents_opened_count")).toMatchObject({ kind: "number", value: 7, sampleCount: null });
  });
});
