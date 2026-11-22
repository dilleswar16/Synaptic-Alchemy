import { describe, expect, it } from "vitest";
import type { RecordReference } from "@/api/askKeiganApi";
import { firstRecordLink, recordPath } from "./toolRecordLinks";

function record(kind: RecordReference["kind"], overrides: Partial<RecordReference> = {}): RecordReference {
  return { kind, id: "id-1", label: "Label", applicationId: "app-1", ...overrides };
}

describe("recordPath", () => {
  it("opens an investigation and an application by id", () => {
    expect(recordPath(record("investigation"))).toBe("/investigations/id-1");
    expect(recordPath(record("application"))).toBe("/applications/id-1");
  });

  it("opens an incident through the filtered list, because that page does not take an id", () => {
    expect(recordPath(record("incident", { label: "INC0012345" }))).toBe("/incidents?search=INC0012345");
  });

  it("opens the step of the application that shows the record", () => {
    expect(recordPath(record("runbook"))).toBe("/applications/app-1/runbooks");
    expect(recordPath(record("knowledge_document"))).toBe("/applications/app-1/knowledge");
    expect(recordPath(record("service"))).toBe("/applications/app-1/services");
    expect(recordPath(record("topology"))).toBe("/applications/app-1/topology");
    expect(recordPath(record("team"))).toBe("/applications/app-1/notifications");
  });

  it("opens whole pages for the lists that have no page per record", () => {
    expect(recordPath(record("alert_group"))).toBe("/alerts");
    expect(recordPath(record("slo"))).toBe("/slo");
    expect(recordPath(record("signal"))).toBe("/intelligence");
  });

  it("has no page for an evidence item", () => {
    expect(recordPath(record("evidence"))).toBeNull();
  });

  it("encodes what it puts in a path or a query, so a record cannot change where the link goes", () => {
    const hostile = "../../x?y=1#z/https://evil.example";
    expect(recordPath(record("investigation", { id: hostile }))).toBe(`/investigations/${encodeURIComponent(hostile)}`);
    expect(recordPath(record("application", { id: "a/b" }))).toBe("/applications/a%2Fb");
    expect(recordPath(record("runbook", { applicationId: "a b/../c" }))).toBe("/applications/a%20b%2F..%2Fc/runbooks");
    expect(recordPath(record("incident", { label: "a&b=c#d" }))).toBe("/incidents?search=a%26b%3Dc%23d");
  });

  it("never produces an external or protocol-relative address", () => {
    for (const kind of ["investigation", "incident", "alert_group", "slo", "signal", "application", "runbook", "knowledge_document", "service", "topology", "team"] as const) {
      const path = recordPath(record(kind, { id: "//evil.example", label: "https://evil.example", applicationId: "//evil.example" }));
      expect(path).toMatch(/^\/[^/]/);
      expect(path).not.toMatch(/^\/\//);
    }
  });
});

describe("firstRecordLink", () => {
  it("returns the first record that has a page, skipping evidence", () => {
    const link = firstRecordLink([record("evidence", { id: "e1" }), record("investigation", { id: "inv-1" }), record("slo", { id: "slo-1" })]);
    expect(link?.record.id).toBe("inv-1");
    expect(link?.path).toBe("/investigations/inv-1");
  });

  it("returns null when no record has a page, or there are none", () => {
    expect(firstRecordLink([record("evidence")])).toBeNull();
    expect(firstRecordLink([])).toBeNull();
  });
});
