import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Box, Boxes, Cloud, Cpu, Database, Globe, HardDrive, Layers, ListOrdered, Network, Server, Users, Workflow, Zap, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { EmptyState } from "@/components/ui/EmptyState";

export type TopologyImpactLevel = "direct" | "indirect";

export interface TopologyGraphNode {
  /** Stable key (service key or component id). */
  key: string;
  name: string;
  /** Node type: aks, functions, app_service, logic_apps, api_management, data_factory, service, database, storage, queue, external, hardware, mainframe, saas, users. */
  type: string;
  /** Optional second line (e.g. component name). */
  subtitle?: string;
  /** Optional fixed position; otherwise a layered left-to-right layout is computed from the edges. */
  position?: { x: number; y: number };
}

export interface TopologyGraphEdge {
  source: string;
  target: string;
  label?: string;
}

export interface TopologyGraphProps {
  nodes: TopologyGraphNode[];
  edges: TopologyGraphEdge[];
  /** Impacted nodes: `{ "claims-api": "direct", "payments": "indirect" }`. Edges between impacted nodes animate. */
  highlightedNodeKeys?: Record<string, TopologyImpactLevel>;
  /** Called when a node is clicked. */
  onNodeSelect?: (nodeKey: string) => void;
  height?: number | string;
  showMiniMap?: boolean;
  className?: string;
}

const nodeTypeIcons: Record<string, LucideIcon> = {
  aks: Boxes,
  functions: Zap,
  app_service: Layers,
  logic_apps: Workflow,
  api_management: Network,
  data_factory: Workflow,
  service: Box,
  database: Database,
  storage: HardDrive,
  queue: ListOrdered,
  external: Globe,
  hardware: Cpu,
  mainframe: Server,
  saas: Cloud,
  users: Users,
};

const nodeWidth = 208;
const nodeHeight = 64;
const columnGap = 96;
const rowGap = 28;

interface ServiceNodeData extends Record<string, unknown> {
  name: string;
  subtitle?: string;
  typeLabel: string;
  iconType: string;
  impact?: TopologyImpactLevel;
  impactLabel?: string;
}

/** Longest-path layering (cycles tolerated): columns by depth from the sources, rows in input order. */
function computeLayout(nodes: TopologyGraphNode[], edges: TopologyGraphEdge[]): Map<string, { x: number; y: number }> {
  const depthByKey = new Map<string, number>(nodes.map((node) => [node.key, 0]));
  for (let pass = 0; pass < nodes.length; pass += 1) {
    let hasChanged = false;
    for (const edge of edges) {
      const sourceDepth = depthByKey.get(edge.source);
      const targetDepth = depthByKey.get(edge.target);
      if (sourceDepth === undefined || targetDepth === undefined) continue;
      if (targetDepth < sourceDepth + 1 && sourceDepth + 1 < nodes.length) {
        depthByKey.set(edge.target, sourceDepth + 1);
        hasChanged = true;
      }
    }
    if (!hasChanged) break;
  }
  const rowCountByDepth = new Map<number, number>();
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of nodes) {
    const depth = depthByKey.get(node.key) ?? 0;
    const rowIndex = rowCountByDepth.get(depth) ?? 0;
    rowCountByDepth.set(depth, rowIndex + 1);
    positions.set(node.key, node.position ?? { x: depth * (nodeWidth + columnGap), y: rowIndex * (nodeHeight + rowGap) });
  }
  return positions;
}

function ServiceNode({ data }: NodeProps<Node<ServiceNodeData>>) {
  const Icon = nodeTypeIcons[data.iconType] ?? Box;
  return (
    <div
      className={cn(
        "relative flex h-16 w-52 items-center gap-2.5 rounded-md border bg-surface px-3 shadow-xs",
        data.impact === "direct" && "border-danger-fill ring-2 ring-danger-fill/40",
        data.impact === "indirect" && "border-alert-fill ring-2 ring-alert-fill/30",
        !data.impact && "border-hairline",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-strong" />
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-sm",
          data.impact === "direct" ? "bg-danger-soft text-danger" : data.impact === "indirect" ? "bg-alert-soft text-alert" : "bg-info-soft text-info",
        )}
      >
        <Icon aria-hidden="true" size={18} strokeWidth={1.75} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-body-sm font-semibold text-default" title={data.name}>
          {data.name}
        </span>
        <span className="block truncate text-caption text-muted">{data.impactLabel ?? data.subtitle ?? data.typeLabel}</span>
      </span>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-strong" />
    </div>
  );
}

const nodeTypes = { service: ServiceNode };

/** Service dependency graph (React Flow). Impacted nodes get a red / berry ring; edges between impacted nodes animate. */
export function TopologyGraph({ nodes, edges, highlightedNodeKeys = {}, onNodeSelect, height = 480, showMiniMap = true, className }: TopologyGraphProps) {
  const { t } = useTranslation("common");

  const flowNodes = useMemo<Node<ServiceNodeData>[]>(() => {
    const positions = computeLayout(nodes, edges);
    return nodes.map((node) => {
      const impact = highlightedNodeKeys[node.key];
      return {
        id: node.key,
        type: "service",
        position: positions.get(node.key) ?? { x: 0, y: 0 },
        data: {
          name: node.name,
          subtitle: node.subtitle,
          typeLabel: t(`topology.nodeTypes.${node.type}`, { defaultValue: node.type }),
          iconType: node.type,
          impact,
          impactLabel: impact === "direct" ? t("topology.impactDirect") : impact === "indirect" ? t("topology.impactIndirect") : undefined,
        },
      };
    });
  }, [nodes, edges, highlightedNodeKeys, t]);

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => {
        const isImpactedPath = Boolean(highlightedNodeKeys[edge.source] && highlightedNodeKeys[edge.target]);
        const strokeColor = isImpactedPath ? "var(--color-danger-fill)" : "var(--color-border-strong)";
        return {
          id: `${edge.source}->${edge.target}`,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          animated: isImpactedPath,
          style: { stroke: strokeColor, strokeWidth: isImpactedPath ? 2 : 1.5, strokeDasharray: isImpactedPath ? "6 4" : undefined },
          markerEnd: { type: MarkerType.ArrowClosed, color: strokeColor, width: 16, height: 16 },
        };
      }),
    [edges, highlightedNodeKeys],
  );

  if (nodes.length === 0) {
    return <EmptyState icon={Network} title={t("topology.emptyTitle")} description={t("topology.emptyDescription")} isBordered className={className} />;
  }

  return (
    <div className={cn("keigan-topology overflow-hidden rounded-md border border-hairline bg-surface-sunken", className)} style={{ height }} role="group" aria-label={t("topology.label")}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={1.6}
        nodesConnectable={false}
        nodesDraggable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={onNodeSelect ? (_event, node) => onNodeSelect(node.id) : undefined}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--color-border-strong)" />
        <Controls showInteractive={false} position="bottom-left" />
        {showMiniMap ? <MiniMap pannable zoomable ariaLabel={t("topology.minimap")} nodeColor={(node) => (node.data?.impact === "direct" ? "var(--color-danger-fill)" : node.data?.impact === "indirect" ? "var(--color-alert-fill)" : "var(--chart-1)")} /> : null}
        <Panel position="top-left">
          <ul className="flex flex-col gap-1 rounded-sm border border-hairline bg-surface px-2.5 py-2 text-caption text-muted shadow-xs" aria-label={t("topology.legend")}>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="size-2.5 rounded-full bg-danger-fill" />
              {t("topology.impactDirect")}
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="size-2.5 rounded-full bg-alert-fill" />
              {t("topology.impactIndirect")}
            </li>
          </ul>
        </Panel>
      </ReactFlow>
    </div>
  );
}
