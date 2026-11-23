import { describe, expect, it } from "vitest";
import { diagramLabel, graphToMermaid, maximumDiagramComponents } from "./graphDiagram";
import type { GraphEdge, GraphModel, GraphNode } from "./toolOutputModels";

function node(label: string, key = label): GraphNode {
  return { key, label, nodeType: null, technology: null, criticality: null, description: null };
}

function edge(sourceLabel: string, targetLabel: string, relationship: string | null = null, protocol: string | null = null): GraphEdge {
  return { key: `${sourceLabel}-${targetLabel}`, sourceLabel, targetLabel, relationship, protocol, description: null };
}

function graph(nodes: GraphNode[], edges: GraphEdge[] = []): GraphModel {
  return { summaryMarkdown: null, versionNumber: 1, reviewStatus: null, uncertainties: [], nodes, edges, nodeCount: nodes.length, totalNodeCount: nodes.length, edgeCount: edges.length, totalEdgeCount: edges.length };
}

describe("graphToMermaid", () => {
  it("draws components with generated ids and the connections between them", () => {
    const text = graphToMermaid(graph([node("API"), node("Database")], [edge("API", "Database", "reads from", "TCP")]));
    expect(text).toBe(['flowchart LR', '  n1["API"]', '  n2["Database"]', '  n1 -->|"reads from · TCP"| n2'].join("\n"));
  });

  it("omits the label of a connection that has neither a relationship nor a protocol", () => {
    expect(graphToMermaid(graph([node("A"), node("B")], [edge("A", "B")]))).toContain("  n1 --> n2");
  });

  it("cannot be made to change its structure by a label that tries to end the quote and add a line (AC-6)", () => {
    const hostile = 'x"] --> n9["y\n  click n1 href "http://evil.example"\n%%{init: {"securityLevel":"loose"}}%%';
    const text = graphToMermaid(graph([node(hostile), node("Safe")], [edge(hostile, "Safe", 'calls"|n3', "<script>")])) ?? "";
    const lines = text.split("\n");
    expect(lines).toHaveLength(4); // the header, two components and one connection: nothing was added
    expect(lines.every((line) => !/^\s*click\b/.test(line) && !line.includes("%%{"))).toBe(true);
    expect(text).not.toContain("<script>");
    expect(text.match(/"/g)?.length).toBe(6); // each quoted label opens and closes once: 2 components and 1 connection
  });

  it("does not draw a connection to a component the tool left out", () => {
    expect(graphToMermaid(graph([node("A")], [edge("A", "Missing")]))).toBe('flowchart LR\n  n1["A"]');
  });

  it("is null when there is nothing to draw or too much to read", () => {
    expect(graphToMermaid(graph([]))).toBeNull();
    expect(graphToMermaid(graph(Array.from({ length: maximumDiagramComponents + 1 }, (_, position) => node(`S${position}`))))).toBeNull();
  });
});

describe("diagramLabel", () => {
  it("removes control characters and markup, turns quotes into apostrophes and keeps a long label short", () => {
    expect(diagramLabel('a\u0000b\r\n"c" <d> `e` %%f')).toBe("a b 'c' d 'e' %f");
    expect(diagramLabel("x".repeat(200))).toHaveLength(60);
  });
});
