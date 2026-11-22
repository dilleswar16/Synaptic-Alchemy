import { asRecordArray } from "./toolValues";

/**
 * Reading the outputs of the tools that have a view of their own (application map, SLO status). The output is the tool's JSON, so every reader checks
 * the shape and keeps only what it can draw; a missing or unexpected field leaves a part out and never fails.
 */

function textOrNull(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function textList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item !== "") : [];
}

/* ── Application map (presentation `graph`) ────────────────────────── */
export interface GraphNode {
  key: string;
  label: string;
  nodeType: string | null;
  technology: string | null;
  criticality: string | null;
  description: string | null;
}

export interface GraphEdge {
  key: string;
  sourceLabel: string;
  targetLabel: string;
  relationship: string | null;
  protocol: string | null;
  description: string | null;
}

export interface GraphModel {
  summaryMarkdown: string | null;
  versionNumber: number | null;
  reviewStatus: string | null;
  uncertainties: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodeCount: number;
  totalNodeCount: number;
  edgeCount: number;
  totalEdgeCount: number;
}

function readNode(record: Record<string, unknown>, position: number): GraphNode | null {
  const label = textOrNull(record.label) ?? textOrNull(record.node_key);
  return label
    ? {
        key: textOrNull(record.node_key) ?? `node-${position}`,
        label,
        nodeType: textOrNull(record.node_type),
        technology: textOrNull(record.technology),
        criticality: textOrNull(record.criticality),
        description: textOrNull(record.description),
      }
    : null;
}

function readEdge(record: Record<string, unknown>, position: number): GraphEdge | null {
  const sourceLabel = textOrNull(record.source_label) ?? textOrNull(record.source_node_key);
  const targetLabel = textOrNull(record.target_label) ?? textOrNull(record.target_node_key);
  return sourceLabel && targetLabel
    ? {
        key: `edge-${position}`,
        sourceLabel,
        targetLabel,
        relationship: textOrNull(record.relationship),
        protocol: textOrNull(record.protocol),
        description: textOrNull(record.description),
      }
    : null;
}

/** The nodes, the edges and the notes of a `get_topology` output; null when the output has neither a node nor an edge list. */
export function readGraphModel(output: Record<string, unknown>): GraphModel | null {
  if (!Array.isArray(output.nodes) && !Array.isArray(output.edges)) {
    return null;
  }
  const nodes = asRecordArray(output.nodes).flatMap((record, position) => readNode(record, position) ?? []);
  const edges = asRecordArray(output.edges).flatMap((record, position) => readEdge(record, position) ?? []);
  const countOf = (value: unknown, fallback: number) => (typeof value === "number" ? value : fallback);
  return {
    summaryMarkdown: textOrNull(output.understanding_summary),
    versionNumber: typeof output.topology_version_number === "number" ? output.topology_version_number : null,
    reviewStatus: textOrNull(output.review_status),
    uncertainties: textList(output.uncertainties),
    nodes,
    edges,
    nodeCount: countOf(output.node_count, nodes.length),
    totalNodeCount: countOf(output.total_node_count, nodes.length),
    edgeCount: countOf(output.edge_count, edges.length),
    totalEdgeCount: countOf(output.total_edge_count, edges.length),
  };
}

/* ── Numbers (presentation `metrics`) ──────────────────────────────── */
/** How a metric value is written: a share in percent, or a plain number (a burn rate, a count). */
export type MetricValueKind = "percentage" | "number";

export interface MetricValue {
  fieldName: string;
  kind: MetricValueKind;
  /** Null when the tool has no data for it yet. */
  value: number | null;
}

export interface MetricGroup {
  key: string;
  /** The service and the indicator's name, as the parts the view lists in the user's language (the service is left out when the name already starts with it). */
  titleParts: string[];
  /** The application and, for an SLO, the length of its window: the context a number needs. */
  applicationName: string | null;
  windowDays: number | null;
  status: string | null;
  isApproximate: boolean;
  values: MetricValue[];
}

/** Fields that describe a group instead of being one of its numbers. */
const describingFieldNames: ReadonlySet<string> = new Set(["rolling_window_days", "item_count", "total_count", "node_count", "total_node_count", "edge_count", "total_edge_count"]);
/** Fields that are numbers even when the tool has no value yet (`null`), in the order they are shown. */
const knownMetricFieldNames = ["compliance_percentage", "target_percentage", "error_budget_remaining_percentage", "burn_rate_one_hour", "burn_rate_six_hours"] as const;
const groupTitleFieldNames = ["sli_name", "title", "name", "label"] as const;

function metricValueKind(fieldName: string): MetricValueKind {
  return fieldName.endsWith("_percentage") ? "percentage" : "number";
}

function readMetricValues(record: Record<string, unknown>): MetricValue[] {
  const names = [
    ...knownMetricFieldNames.filter((fieldName) => fieldName in record),
    ...Object.keys(record).filter((fieldName) => typeof record[fieldName] === "number" && !describingFieldNames.has(fieldName) && !knownMetricFieldNames.some((known) => known === fieldName)),
  ];
  return names.map((fieldName) => {
    const value = record[fieldName];
    return { fieldName, kind: metricValueKind(fieldName), value: typeof value === "number" ? value : null };
  });
}

function readMetricGroup(record: Record<string, unknown>, position: number): MetricGroup {
  const titleFieldName = groupTitleFieldNames.find((fieldName) => textOrNull(record[fieldName]) !== null);
  const serviceName = textOrNull(record.service_name);
  const sliName = titleFieldName ? textOrNull(record[titleFieldName]) : null;
  return {
    key: textOrNull(record.slo_id) ?? `metrics-${position}`,
    // The indicator's name often starts with its service ("claims-api: Pod readiness"): the service is added only when it does not.
    titleParts: serviceName !== null && sliName !== null && !sliName.includes(serviceName) ? [serviceName, sliName] : [sliName ?? serviceName].filter((part): part is string => part !== null),
    applicationName: textOrNull(record.application_name),
    windowDays: typeof record.rolling_window_days === "number" ? record.rolling_window_days : null,
    status: textOrNull(record.status),
    isApproximate: record.is_approximate === true,
    values: readMetricValues(record),
  };
}

/** The numbers of a metrics output: one group per entry of `items` (an SLO), or one group of the output's own numbers when it has no list. */
export function readMetricGroups(output: Record<string, unknown>): MetricGroup[] {
  const items = asRecordArray(output.items);
  const groups = items.length > 0 ? items.map(readMetricGroup) : [readMetricGroup(output, 0)];
  return groups.filter((group) => group.values.length > 0);
}
