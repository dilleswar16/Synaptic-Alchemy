/**
 * SimilarityNetworkGraph.tsx — Feature 11: Investigation Similarity Network
 *
 * Renders a force-directed graph of investigations where:
 *  - Each node = one completed investigation
 *  - Edge thickness = similarity score
 *  - Node size = incident priority (P1 = largest)
 *  - Node colour = service name (consistent per service)
 *  - Focus node (if provided) is highlighted with a gold ring
 *
 * Built on @xyflow/react (already in deps). The layout is computed once on
 * load using a simple circle + weighted radial placement; users can drag nodes
 * to explore the graph interactively.
 *
 * Empty states:
 *   - No data yet   → skeleton + load button
 *   - No edges      → nodes only, with a "no connections above threshold" notice
 *   - API error     → error banner with retry
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  fetchSimilarityNetwork,
  type SimilarityNode,
  type SimilarityEdge,
  type SimilarityNetworkResponse,
} from '../api/client'

// ── Colour palette (one per service, deterministic from name hash) ────────────

const PALETTE = [
  '#4f9cf9', '#f97316', '#22c55e', '#a855f7', '#ec4899',
  '#14b8a6', '#f59e0b', '#6366f1', '#84cc16', '#ef4444',
]

function serviceColor(serviceName: string): string {
  let hash = 0
  for (let i = 0; i < serviceName.length; i++) {
    hash = (hash * 31 + serviceName.charCodeAt(i)) & 0xffffff
  }
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

// ── Priority → node radius ────────────────────────────────────────────────────

function nodeRadius(nodeSize: number): number {
  return 20 + nodeSize * 8  // P1=60px, P2=52px, P3=44px, else=36px
}

// ── Custom node component ─────────────────────────────────────────────────────

interface SimilarityNodeData {
  label: string
  service_name: string
  environment: string
  priority: string
  rca_summary: string
  created_at: string
  node_size: number
  isFocus: boolean
}

function SimilarityNodeComponent({ data }: { data: SimilarityNodeData }) {
  const radius = nodeRadius(data.node_size)
  const color = serviceColor(data.service_name)
  return (
    <div
      title={`${data.service_name} | ${data.environment}\n${data.rca_summary}`}
      style={{
        width: radius,
        height: radius,
        borderRadius: '50%',
        background: color,
        border: data.isFocus ? '3px solid #f5c518' : '2px solid rgba(255,255,255,0.25)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        boxShadow: data.isFocus
          ? '0 0 0 4px rgba(245,197,24,0.4)'
          : '0 2px 8px rgba(0,0,0,0.3)',
        overflow: 'hidden',
        padding: 4,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <span style={{
        fontSize: 9,
        fontWeight: 700,
        color: '#fff',
        lineHeight: 1.2,
        textAlign: 'center',
        wordBreak: 'break-word',
        maxWidth: radius - 8,
        display: '-webkit-box',
        WebkitLineClamp: 3,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}>
        {data.service_name}
      </span>
      <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.7)', marginTop: 1 }}>
        {data.priority}
      </span>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes: NodeTypes = {
  similarityNode: SimilarityNodeComponent as any,
}

// ── Layout algorithm — radial placement ──────────────────────────────────────

function buildLayout(
  nodes: SimilarityNode[],
  focusId: string | null,
): { id: string; x: number; y: number }[] {
  if (nodes.length === 0) return []

  const CX = 600
  const CY = 400
  const BASE_RADIUS = Math.min(300, 60 + nodes.length * 18)

  // Focus node in the centre; others on a circle, grouped by service.
  const focusIdx = nodes.findIndex(n => n.id === focusId)
  const ordered = focusIdx >= 0
    ? [nodes[focusIdx], ...nodes.filter((_, i) => i !== focusIdx)]
    : nodes

  return ordered.map((n, i) => {
    if (i === 0 && focusId) return { id: n.id, x: CX, y: CY }
    const angle = ((i - (focusId ? 1 : 0)) / (nodes.length - (focusId ? 1 : 0))) * 2 * Math.PI
    return {
      id: n.id,
      x: CX + BASE_RADIUS * Math.cos(angle),
      y: CY + BASE_RADIUS * Math.sin(angle),
    }
  })
}

// ── Conversion helpers ────────────────────────────────────────────────────────

function toFlowNodes(
  nodes: SimilarityNode[],
  focusId: string | null,
): Node[] {
  const layout = buildLayout(nodes, focusId)
  const posMap = new Map(layout.map(l => [l.id, { x: l.x, y: l.y }]))

  return nodes.map(n => {
    const pos = posMap.get(n.id) ?? { x: 0, y: 0 }
    const radius = nodeRadius(n.node_size)
    return {
      id: n.id,
      type: 'similarityNode',
      position: { x: pos.x - radius / 2, y: pos.y - radius / 2 },
      data: {
        label: n.label,
        service_name: n.service_name,
        environment: n.environment,
        priority: n.priority,
        rca_summary: n.rca_summary,
        created_at: n.created_at,
        node_size: n.node_size,
        isFocus: n.id === focusId,
      } satisfies SimilarityNodeData,
    }
  })
}

function toFlowEdges(edges: SimilarityEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `edge-${i}-${e.source_id}-${e.target_id}`,
    source: e.source_id,
    target: e.target_id,
    label: e.reasons[0] ?? '',
    style: {
      strokeWidth: 1 + e.similarity_score * 5,
      stroke: `rgba(100,160,255,${0.3 + e.similarity_score * 0.6})`,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(100,160,255,0.5)', width: 12, height: 12 },
    labelStyle: { fontSize: 10, fill: 'var(--c-text-muted)' },
    labelBgStyle: { fill: 'var(--c-bg)', fillOpacity: 0.7 },
  }))
}

// ── Main component ────────────────────────────────────────────────────────────

interface SimilarityNetworkGraphProps {
  /** When set, this investigation is highlighted and used as focus for edges */
  focusId?: string
  /** Initial service filter */
  serviceFilter?: string
  /** Initial environment filter */
  environmentFilter?: string
}

export default function SimilarityNetworkGraph({
  focusId,
  serviceFilter,
  environmentFilter,
}: SimilarityNetworkGraphProps) {
  const navigate = useNavigate()
  const [data, setData] = useState<SimilarityNetworkResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minSimilarity, setMinSimilarity] = useState(0.20)
  const [limit, setLimit] = useState(50)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await fetchSimilarityNetwork({
        focusId,
        limit,
        minSimilarity,
        serviceFilter,
        environmentFilter,
      })
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load similarity network.')
    } finally {
      setIsLoading(false)
    }
  }, [focusId, limit, minSimilarity, serviceFilter, environmentFilter])

  useEffect(() => {
    load()
  }, [load])

  const { flowNodes, flowEdges } = useMemo(() => {
    if (!data) return { flowNodes: [], flowEdges: [] }
    return {
      flowNodes: toFlowNodes(data.nodes, data.focus_id ?? null),
      flowEdges: toFlowEdges(data.edges),
    }
  }, [data])

  const handleNodeClick = useCallback((_: unknown, node: Node) => {
    navigate(`/investigations/${node.id}`)
  }, [navigate])

  // ── Legend pills ────────────────────────────────────────────────────────────
  const services = useMemo(() => {
    if (!data) return []
    const seen = new Set<string>()
    return data.nodes.filter(n => {
      if (seen.has(n.service_name)) return false
      seen.add(n.service_name)
      return true
    })
  }, [data])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        padding: '8px 0',
      }}>
        <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>
          Similarity Network
        </span>
        <label style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
          Min similarity
          <input
            type="range"
            min={0.05}
            max={0.95}
            step={0.05}
            value={minSimilarity}
            onChange={e => setMinSimilarity(parseFloat(e.target.value))}
            style={{ width: 80 }}
          />
          <span style={{ minWidth: 28 }}>{Math.round(minSimilarity * 100)}%</span>
        </label>
        <label style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
          Nodes
          <select
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            style={{
              fontSize: '0.78rem',
              padding: '2px 6px',
              borderRadius: 4,
              border: '1px solid var(--c-border)',
              background: 'var(--c-bg)',
              color: 'var(--c-text)',
            }}
          >
            {[20, 50, 100, 200].map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
        <button
          className="btn-primary"
          onClick={load}
          disabled={isLoading}
          style={{ fontSize: '0.78rem', padding: '4px 12px' }}
        >
          {isLoading ? 'Loading…' : '↺ Refresh'}
        </button>
        {data && (
          <span style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)', marginLeft: 'auto' }}>
            {data.stats.node_count} nodes · {data.stats.edge_count} edges
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '8px 12px',
          borderRadius: 6,
          background: 'rgba(239,68,68,0.08)',
          color: 'var(--c-red)',
          fontSize: '0.82rem',
        }} role="alert">
          ⚠️ {error}
        </div>
      )}

      {/* No edges notice */}
      {data && data.stats.edge_count === 0 && data.stats.node_count > 0 && (
        <div style={{
          padding: '8px 12px',
          borderRadius: 6,
          background: 'rgba(100,160,255,0.06)',
          fontSize: '0.8rem',
          color: 'var(--c-text-muted)',
        }}>
          No connections above {Math.round(minSimilarity * 100)}% similarity threshold.
          Try lowering the slider to see more edges.
        </div>
      )}

      {/* Graph canvas */}
      <div style={{
        height: 480,
        borderRadius: 12,
        border: '1px solid var(--c-border)',
        overflow: 'hidden',
        background: 'var(--c-surface)',
        position: 'relative',
      }}>
        {isLoading && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,0.25)', zIndex: 10, borderRadius: 12,
          }}>
            <div className="pulse-skeleton" style={{ width: 200, height: 20 }} />
          </div>
        )}
        {!isLoading && data && (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            onNodeClick={handleNodeClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            attributionPosition="bottom-right"
          >
            <Background gap={24} size={1} color="var(--c-border)" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={n => serviceColor((n.data as SimilarityNodeData).service_name)}
              maskColor="rgba(0,0,0,0.2)"
              style={{ background: 'var(--c-surface)' }}
            />
          </ReactFlow>
        )}
        {!isLoading && !data && !error && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--c-text-muted)', fontSize: '0.85rem' }}>
            Click <strong style={{ margin: '0 4px' }}>Refresh</strong> to build the network.
          </div>
        )}
      </div>

      {/* Service legend */}
      {services.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {services.map(n => (
            <span
              key={n.service_name}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                fontSize: '0.74rem',
                padding: '2px 8px',
                borderRadius: 20,
                background: 'var(--c-surface)',
                border: '1px solid var(--c-border)',
                color: 'var(--c-text)',
              }}
            >
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: serviceColor(n.service_name),
                flexShrink: 0,
              }} />
              {n.service_name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
