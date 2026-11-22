import type { StepKey } from "@/api/applicationsApi";
import type { RecordReference } from "@/api/askKeiganApi";

/** The workspace step of the application that shows each kind of record that has no page of its own. */
const applicationStepByRecordKind = {
  runbook: "runbooks",
  knowledge_document: "knowledge",
  service: "services",
  topology: "topology",
  team: "notifications",
} as const satisfies Partial<Record<RecordReference["kind"], StepKey>>;

/**
 * The Keigan page that shows a record a tool read, or null when no page shows that one record on its own (an evidence item belongs to its
 * investigation page, which the card does not know). Lists open filtered or whole, because those pages do not take a record id.
 */
export function recordPath(record: RecordReference): string | null {
  switch (record.kind) {
    case "investigation":
      return `/investigations/${encodeURIComponent(record.id)}`;
    case "incident":
      return `/incidents?search=${encodeURIComponent(record.label)}`;
    case "alert_group":
      return "/alerts";
    case "slo":
      return "/slo";
    case "signal":
      return "/intelligence";
    case "application":
      return `/applications/${encodeURIComponent(record.id)}`;
    case "runbook":
    case "knowledge_document":
    case "service":
    case "topology":
    case "team":
      return `/applications/${encodeURIComponent(record.applicationId)}/${applicationStepByRecordKind[record.kind]}`;
    case "evidence":
      return null;
  }
}

export interface RecordLink {
  record: RecordReference;
  path: string;
}

/** The first record of a tool call that has a page (spec 8.3: "Open in Keigan" opens the first record's page), or null. */
export function firstRecordLink(records: readonly RecordReference[]): RecordLink | null {
  for (const record of records) {
    const path = recordPath(record);
    if (path !== null) {
      return { record, path };
    }
  }
  return null;
}
