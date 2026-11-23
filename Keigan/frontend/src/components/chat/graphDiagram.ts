import type { GraphModel } from "./toolOutputModels";

/** Past this many components a picture stops helping; the lists below it stay the way to read the map. */
export const maximumDiagramComponents = 40;
const maximumLabelCharacters = 60;

/** Text safe inside a quoted Mermaid label: no quote, markup or line break can end the label or start something else. */
export function diagramLabel(text: string): string {
  const cleaned = text
    .replace(/[\u0000-\u001F\u007F]+/g, " ")
    .replace(/["`]/g, "'")
    .replace(/[<>]/g, "")
    .replace(/%%/g, "%")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.length > maximumLabelCharacters ? `${cleaned.slice(0, maximumLabelCharacters - 1)}…` : cleaned;
}

/**
 * The application map as Mermaid text, written by code from the tool's own components and connections (spec 36, D7): node ids are generated, never taken from the data, and every
 * label is cleaned and quoted, so what the map says can change the words in the picture but not its structure. Null when there is nothing to draw or too much to read.
 */
export function graphToMermaid(graph: GraphModel): string | null {
  if (graph.nodes.length === 0 || graph.nodes.length > maximumDiagramComponents) {
    return null;
  }
  const identifierByLabel = new Map<string, string>();
  const lines = ["flowchart LR"];
  graph.nodes.forEach((node, position) => {
    const identifier = `n${position + 1}`;
    if (!identifierByLabel.has(node.label)) {
      identifierByLabel.set(node.label, identifier);
    }
    lines.push(`  ${identifier}["${diagramLabel(node.label)}"]`);
  });
  for (const edge of graph.edges) {
    const source = identifierByLabel.get(edge.sourceLabel);
    const target = identifierByLabel.get(edge.targetLabel);
    if (!source || !target) {
      continue; // a connection to a component the tool left out (it shows the first ones only) is not drawn
    }
    const connectionLabel = diagramLabel([edge.relationship, edge.protocol].filter((part): part is string => part !== null).join(" · "));
    lines.push(connectionLabel ? `  ${source} -->|"${connectionLabel}"| ${target}` : `  ${source} --> ${target}`);
  }
  return lines.join("\n");
}
