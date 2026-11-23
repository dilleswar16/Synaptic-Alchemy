import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/Badge";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { MermaidDiagram } from "@/components/ui/MermaidDiagram";
import { formatList } from "@/utils/formatters";
import { graphToMermaid } from "./graphDiagram";
import { readGraphModel, type GraphEdge, type GraphModel, type GraphNode } from "./toolOutputModels";
import { formatEnumToken } from "./toolValues";

function NodeItem({ node }: { node: GraphNode }) {
  const { t } = useTranslation("chat");
  const kindParts = [node.nodeType, node.technology].filter((part): part is string => part !== null).map((part) => formatEnumToken(t, part, true));
  return (
    <li className="flex flex-col gap-0.5 rounded-md border border-hairline bg-surface-sunken px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-body-sm font-medium break-words text-default">{node.label}</span>
        {node.criticality ? <Badge tone="neutral">{t("tool.graph.criticality", { level: formatEnumToken(t, node.criticality, true) })}</Badge> : null}
      </div>
      {kindParts.length > 0 ? <span className="text-caption break-words text-muted">{formatList(kindParts)}</span> : null}
      {node.description ? <span className="text-caption break-words text-muted">{node.description}</span> : null}
    </li>
  );
}

function EdgeItem({ edge }: { edge: GraphEdge }) {
  const { t } = useTranslation("chat");
  const detail = formatList([edge.relationship, edge.protocol].filter((part): part is string => part !== null).map((part) => formatEnumToken(t, part, true)));
  return (
    <li className="flex flex-col gap-0.5 rounded-md border border-hairline bg-surface-sunken px-3 py-2">
      <span className="text-body-sm font-medium break-words text-default">{t("tool.graph.edge", { source: edge.sourceLabel, target: edge.targetLabel })}</span>
      {detail ? <span className="text-caption break-words text-muted">{detail}</span> : null}
      {edge.description ? <span className="text-caption break-words text-muted">{edge.description}</span> : null}
    </li>
  );
}

/** One of the two lists of the map: a heading with how many of how many are shown, then the items. */
function GraphList({ heading, shown, total, children }: { heading: string; shown: number; total: number; children: ReactNode }) {
  const { t } = useTranslation("chat");
  return (
    <section className="flex flex-col gap-2">
      <h5 className="text-caption font-semibold text-muted">{shown < total ? t("tool.graph.headingPartial", { heading, shown, total }) : t("tool.graph.heading", { heading, total })}</h5>
      <ul className="flex flex-col gap-2">{children}</ul>
    </section>
  );
}

function GraphMeta({ graph }: { graph: GraphModel }) {
  const { t } = useTranslation("chat");
  const metaParts = [
    graph.versionNumber === null ? null : t("tool.graph.version", { version: graph.versionNumber }),
    graph.reviewStatus ? t("tool.graph.review", { status: formatEnumToken(t, graph.reviewStatus, true) }) : null,
  ].filter((part): part is string => part !== null);
  return (
    <>
      {metaParts.length > 0 ? <p className="text-caption text-muted">{formatList(metaParts)}</p> : null}
      {graph.summaryMarkdown ? <MarkdownView content={graph.summaryMarkdown} /> : null}
      {graph.uncertainties.length > 0 ? (
        <section className="flex flex-col gap-1">
          <h5 className="text-caption font-semibold text-muted">{t("tool.graph.uncertainties")}</h5>
          <ul className="list-disc space-y-1 pl-5 text-body-sm break-words text-default">
            {graph.uncertainties.map((uncertainty) => <li key={uncertainty}>{uncertainty}</li>)}
          </ul>
        </section>
      ) : null}
    </>
  );
}

/** The map as a picture, drawn by code from the map's own components and connections (spec 36, D7). It is drawn only once opened. */
function GraphDiagram({ source }: { source: string }) {
  const { t } = useTranslation("chat");
  const [isOpen, setIsOpen] = useState(false);
  return (
    <details className="text-body-sm" onToggle={(event) => setIsOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-muted hover:text-default">{t("tool.graph.diagram")}</summary>
      {isOpen ? <MermaidDiagram source={source} caption={t("tool.graph.diagramCaption")} /> : null}
    </details>
  );
}

/** The application map as two lists, components and connections, with the notes the map was built with, and a picture of it when there are not too many components. */
export function GraphOutput({ output }: { output: Record<string, unknown> }) {
  const { t } = useTranslation("chat");
  const graph = readGraphModel(output);
  if (!graph || (graph.nodes.length === 0 && graph.edges.length === 0 && !graph.summaryMarkdown)) {
    return null;
  }
  const diagramSource = graphToMermaid(graph);
  return (
    <div className="flex flex-col gap-3">
      <GraphMeta graph={graph} />
      {diagramSource ? <GraphDiagram source={diagramSource} /> : null}
      {graph.nodes.length > 0 ? (
        <GraphList heading={t("tool.graph.nodes")} shown={graph.nodeCount} total={graph.totalNodeCount}>
          {graph.nodes.map((node) => <NodeItem key={node.key} node={node} />)}
        </GraphList>
      ) : null}
      {graph.edges.length > 0 ? (
        <GraphList heading={t("tool.graph.edges")} shown={graph.edgeCount} total={graph.totalEdgeCount}>
          {graph.edges.map((edge) => <EdgeItem key={edge.key} edge={edge} />)}
        </GraphList>
      ) : null}
    </div>
  );
}
