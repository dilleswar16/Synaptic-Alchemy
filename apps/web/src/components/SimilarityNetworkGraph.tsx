/**
 * SimilarityNetworkGraph.tsx — Feature 11: Investigation Similarity Network
 *
 * Design inspired by Datadog Service Map + PagerDuty Service Graph:
 *  - All nodes visible, edges capped at top-3 per node (no full-mesh spaghetti)
 *  - Click node → highlight 1-hop neighbourhood, dim everything else
 *  - Click same node again → navigate to investigation
 *  - Click canvas → clear focus
 *  - No animated edges — stroke width + opacity carry the similarity signal
 *  - Hover card shows top connections with similarity %
 *  - Light canvas, force-directed layout
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  fetchSimilarityNetwork,
  type SimilarityNode,
  type SimilarityEdge,
  type SimilarityNetworkResponse,
} from '../api/client'

// ── Palette (pastel fill, saturated border, dark text — light-bg optimised) ──

const PALETTE = [
  { fill: '#dbeafe', border: '#2563eb', glow: 'rgba(37,99,235,0.22)',  text: '#1e3a8a' },
  { fill: '#f3e8ff', border: '#9333ea', glow: 'rgba(147,51,234,0.22)', text: '#581c87' },
  { fill: '#dcfce7', border: '#16a34a', glow: 'rgba(22,163,74,0.22)',  text: '#14532d' },
  { fill: '#ffedd5', border: '#ea580c', glow: 'rgba(234,88,12,0.22)',  text: '#7c2d12' },
  { fill: '#fee2e2', border: '#dc2626', glow: 'rgba(220,38,38,0.22)',  text: '#7f1d1d' },
  { fill: '#ccfbf1', border: '#0d9488', glow: 'rgba(13,148,136,0.22)', text: '#134e4a' },
  { fill: '#fef9c3', border: '#ca8a04', glow: 'rgba(202,138,4,0.22)',  text: '#713f12' },
  { fill: '#e0e7ff', border: '#4f46e5', glow: 'rgba(79,70,229,0.22)',  text: '#312e81' },
  { fill: '#ecfccb', border: '#65a30d', glow: 'rgba(101,163,13,0.22)', text: '#365314' },
  { fill: '#fce7f3', border: '#db2777', glow: 'rgba(219,39,119,0.22)', text: '#831843' },
]

function svcTheme(name: string) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffff
  return PALETTE[Math.abs(h) % PALETTE.length]
}

// 2-char initials — never raw text inside a circle
function svcInitials(name: string): string {
  const parts = name
    .replace(/(api|sso|service|svc|db|cache|auth|pay|fund|partner|user|order|notif|mgmt|admin|gateway|gw)/gi, ' $1 ')
    .trim().split(/\s+/).filter(Boolean)
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : name.slice(0, 2).toUpperCase()
}

const PRIORITY_COLOR: Record<string, string> = { P1: '#ef4444', P2: '#f97316', P3: '#22c55e' }

// ── Node geometry ─────────────────────────────────────────────────────────────

const CIRCLE_D = 72
const NODE_W   = 104
const NODE_H   = CIRCLE_D + 6 + 16   // circle + gap + label row

// ── Edge helpers ──────────────────────────────────────────────────────────────

function edgeKey(e: SimilarityEdge) {
  return [e.source_id, e.target_id].sort().join('::')
}

// Keep only the top `maxPerNode` highest-similarity edges per node.
// This is the core anti-spaghetti mechanism (Datadog/Grafana pattern).
function capEdgesPerNode(edges: SimilarityEdge[], maxPerNode: number): SimilarityEdge[] {
  const perNode = new Map<string, SimilarityEdge[]>()
  edges.forEach(e => {
    for (const id of [e.source_id, e.target_id]) {
      const list = perNode.get(id) ?? []
      list.push(e)
      perNode.set(id, list)
    }
  })
  const kept = new Set<string>()
  perNode.forEach(list => {
    list
      .sort((a, b) => b.similarity_score - a.similarity_score)
      .slice(0, maxPerNode)
      .forEach(e => kept.add(edgeKey(e)))
  })
  return edges.filter(e => kept.has(edgeKey(e)))
}

function computeNeighbors(nodeId: string, edges: SimilarityEdge[]): Set<string> {
  const s = new Set<string>([nodeId])
  edges.forEach(e => {
    if (e.source_id === nodeId) s.add(e.target_id)
    if (e.target_id === nodeId) s.add(e.source_id)
  })
  return s
}

// ── Force-directed layout (runs once per data load, not on every focus) ───────

interface FN { id: string; x: number; y: number; vx: number; vy: number }

function computeForceLayout(
  nodes: SimilarityNode[],
  edges: SimilarityEdge[],
  W = 920, H = 500,
): Map<string, { x: number; y: number }> {
  if (!nodes.length) return new Map()

  const pos = new Map<string, FN>()
  nodes.forEach((n, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI
    const r = Math.min(W, H) * 0.26
    pos.set(n.id, { id: n.id, x: W / 2 + r * Math.cos(angle), y: H / 2 + r * Math.sin(angle), vx: 0, vy: 0 })
  })

  const REPULSION = 25000
  const K_SPRING  = 0.025
  const IDEAL     = 210
  const K_CLUSTER = 0.005
  const IDEAL_SVC = 110
  const K_CENTER  = 0.005
  const DAMPING   = 0.80
  const ITERS     = 200

  for (let iter = 0; iter < ITERS; iter++) {
    const cool = Math.max(0.06, 1 - iter / ITERS)
    const all  = [...pos.values()]

    // Node-node repulsion
    for (let i = 0; i < all.length; i++) {
      for (let j = i + 1; j < all.length; j++) {
        const a = all[i], b = all[j]
        const dx = b.x - a.x || 0.01, dy = b.y - a.y || 0.01
        const d2 = Math.max(dx * dx + dy * dy, 1), d = Math.sqrt(d2)
        const f  = (REPULSION / d2) * cool
        a.vx -= (dx / d) * f;  a.vy -= (dy / d) * f
        b.vx += (dx / d) * f;  b.vy += (dy / d) * f
      }
    }

    // Edge spring: more similar → shorter ideal distance
    edges.forEach(e => {
      const a = pos.get(e.source_id), b = pos.get(e.target_id)
      if (!a || !b) return
      const dx = b.x - a.x, dy = b.y - a.y
      const d  = Math.sqrt(dx * dx + dy * dy) || 1
      const ideal = IDEAL * (1.1 - e.similarity_score * 0.65)
      const f  = (d - ideal) * K_SPRING * cool
      a.vx += (dx / d) * f;  a.vy += (dy / d) * f
      b.vx -= (dx / d) * f;  b.vy -= (dy / d) * f
    })

    // Same-service cluster pull
    nodes.forEach((na, i) => nodes.slice(i + 1).forEach(nb => {
      if (na.service_name !== nb.service_name) return
      const a = pos.get(na.id)!, b = pos.get(nb.id)!
      const dx = b.x - a.x, dy = b.y - a.y
      const d  = Math.sqrt(dx * dx + dy * dy) || 1
      const f  = (d - IDEAL_SVC) * K_CLUSTER * cool
      a.vx += (dx / d) * f;  a.vy += (dy / d) * f
      b.vx -= (dx / d) * f;  b.vy -= (dy / d) * f
    }))

    // Center gravity
    all.forEach(n => {
      n.vx += (W / 2 - n.x) * K_CENTER * cool
      n.vy += (H / 2 - n.y) * K_CENTER * cool
    })

    // Integrate + clamp
    all.forEach(n => {
      n.x += n.vx; n.y += n.vy
      n.vx *= DAMPING; n.vy *= DAMPING
      n.x = Math.max(60, Math.min(W - 60, n.x))
      n.y = Math.max(60, Math.min(H - 60, n.y))
    })
  }

  return new Map([...pos.entries()].map(([id, p]) => [id, { x: p.x, y: p.y }]))
}

// ── Custom node ───────────────────────────────────────────────────────────────

interface SimilarityNodeData {
  label: string
  service_name: string
  priority: string
  rca_summary: string
  created_at: string
  isFocus: boolean
  isNodeFocused: boolean   // clicked in graph = focus mode
  isDimmed: boolean        // not in focused neighbourhood
  onHover: (id: string | null) => void
  nodeId: string
}

function SimilarityNodeComponent({ data }: { data: SimilarityNodeData }) {
  const [hovered, setHovered] = useState(false)
  const theme    = svcTheme(data.service_name)
  const initials = svcInitials(data.service_name)
  const pColor   = PRIORITY_COLOR[data.priority] ?? '#64748b'
  const svcLabel = data.service_name.length > 15 ? data.service_name.slice(0, 14) + '…' : data.service_name

  return (
    <div
      onMouseEnter={() => { data.onHover(data.nodeId); setHovered(true) }}
      onMouseLeave={() => { data.onHover(null); setHovered(false) }}
      style={{
        width: NODE_W, height: NODE_H,
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        cursor: 'pointer', userSelect: 'none', background: 'transparent',
        opacity: data.isDimmed ? 0.1 : 1,
        filter: data.isDimmed ? 'grayscale(70%)' : 'none',
        transform: hovered ? 'scale(1.12)' : data.isNodeFocused ? 'scale(1.07)' : 'scale(1)',
        transition: 'opacity 0.24s ease, transform 0.17s ease, filter 0.24s ease',
      }}
    >
      <Handle type="target" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none', top: '36px' }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none', top: '36px' }} />

      {/* ── Circle ──────────────────────────────────────────────────── */}
      <div style={{
        width: CIRCLE_D, height: CIRCLE_D, borderRadius: '50%',
        background: `radial-gradient(circle at 36% 32%, #ffffff, ${theme.fill})`,
        border: `2.5px solid ${data.isNodeFocused ? '#4f46e5' : theme.border}`,
        boxShadow: data.isNodeFocused
          ? `0 0 0 5px rgba(79,70,229,0.15), 0 8px 28px ${theme.glow}`
          : hovered
          ? `0 0 0 3px ${theme.border}28, 0 8px 22px ${theme.glow}, inset 0 1px 0 rgba(255,255,255,0.85)`
          : `0 4px 16px ${theme.glow}, 0 1px 3px rgba(0,0,0,0.07), inset 0 1px 0 rgba(255,255,255,0.85)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative', flexShrink: 0,
        transition: 'box-shadow 0.17s ease, border-color 0.17s ease',
      }}>
        {/* Priority badge */}
        <div style={{
          position: 'absolute', top: 5, right: 5,
          fontSize: '0.44rem', fontWeight: 800, padding: '1px 4px', borderRadius: 3,
          background: `${pColor}20`, color: pColor, border: `1px solid ${pColor}50`,
          lineHeight: 1, letterSpacing: '0.03em',
        }}>
          {data.priority}
        </div>

        {/* Initials — 2 chars, always fits */}
        <span style={{
          fontSize: '1.05rem', fontWeight: 900, color: theme.text,
          letterSpacing: '-0.02em', fontFamily: 'var(--font-display, system-ui)', lineHeight: 1,
        }}>
          {initials}
        </span>
      </div>

      {/* ── Service label below circle — single line, never wraps ───── */}
      <div style={{
        marginTop: 5, fontSize: '0.595rem', fontWeight: 600, color: '#374151',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        maxWidth: NODE_W, textAlign: 'center', lineHeight: 1,
        padding: '2px 5px', background: 'rgba(255,255,255,0.78)', borderRadius: 4,
        backdropFilter: 'blur(4px)',
      }}>
        {svcLabel}
      </div>
    </div>
  )
}

const NODE_TYPES: NodeTypes = { similarityNode: SimilarityNodeComponent as any }

// ── Main component ────────────────────────────────────────────────────────────

interface SimilarityNetworkGraphProps {
  focusId?: string
  serviceFilter?: string
  environmentFilter?: string
}

export default function SimilarityNetworkGraph({
  focusId, serviceFilter, environmentFilter,
}: SimilarityNetworkGraphProps) {
  const navigate = useNavigate()
  const [data, setData]             = useState<SimilarityNetworkResponse | null>(null)
  const [isLoading, setIsLoading]   = useState(false)
  const [error, setError]           = useState<string | null>(null)
  // 60% default: service-match alone (40%) no longer qualifies — needs RCA text overlap too
  const [minSimilarity, setMin]     = useState(0.40)
  const [limit, setLimit]           = useState(50)
  const [hoveredId, setHoveredId]   = useState<string | null>(null)
  const [focusedNodeId, setFocused] = useState<string | null>(null)

  const handleHover = useCallback((id: string | null) => setHoveredId(id), [])

  const load = useCallback(async () => {
    setIsLoading(true); setError(null); setFocused(null)
    try {
      const res = await fetchSimilarityNetwork({ focusId, limit, minSimilarity, serviceFilter, environmentFilter })
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally { setIsLoading(false) }
  }, [focusId, limit, minSimilarity, serviceFilter, environmentFilter])

  useEffect(() => { load() }, [load])

  // Phase 1: expensive — force layout + edge capping, only on data change
  const layoutData = useMemo(() => {
    if (!data) return null
    const cappedEdges = capEdgesPerNode(data.edges, 3)
    const positions   = computeForceLayout(data.nodes, cappedEdges)
    return { cappedEdges, positions }
  }, [data])

  // Phase 2: cheap — apply focus/dim state on top of stable layout
  const { flowNodes, flowEdges } = useMemo(() => {
    if (!data || !layoutData) return { flowNodes: [], flowEdges: [] }
    const { cappedEdges, positions } = layoutData

    const neighborIds = focusedNodeId ? computeNeighbors(focusedNodeId, cappedEdges) : null
    const isActive    = (id: string) => !neighborIds || neighborIds.has(id)

    const flowNodes: Node[] = data.nodes.map(n => ({
      id: n.id,
      type: 'similarityNode',
      // Centre circle (not whole node) at the layout position
      position: {
        x: (positions.get(n.id)?.x ?? 0) - NODE_W / 2,
        y: (positions.get(n.id)?.y ?? 0) - CIRCLE_D / 2,
      },
      data: {
        label: n.label,
        service_name: n.service_name,
        priority: n.priority,
        rca_summary: n.rca_summary,
        created_at: n.created_at,
        isFocus: n.id === (data.focus_id ?? ''),
        isNodeFocused: n.id === focusedNodeId,
        isDimmed: !!focusedNodeId && !isActive(n.id),
        onHover: handleHover,
        nodeId: n.id,
      } satisfies SimilarityNodeData,
    }))

    const flowEdges: Edge[] = cappedEdges.map(e => {
      const s         = e.similarity_score
      const bothActive = isActive(e.source_id) && isActive(e.target_id)
      const baseAlpha  = 0.14 + s * 0.62
      return {
        id: edgeKey(e),
        source: e.source_id,
        target: e.target_id,
        type: 'straight',
        animated: false,   // no animated edges — Datadog/Grafana pattern
        style: {
          strokeWidth: 0.9 + s * 3.8,
          stroke: focusedNodeId
            ? `rgba(79,70,229,${bothActive ? Math.min(baseAlpha + 0.28, 0.9) : 0.03})`
            : `rgba(79,70,229,${baseAlpha})`,
          transition: 'stroke 0.24s ease',
        },
      }
    })

    return { flowNodes, flowEdges }
  }, [data, layoutData, focusedNodeId, handleHover])

  const hoveredNode = useMemo(() =>
    hoveredId && data ? data.nodes.find(n => n.id === hoveredId) ?? null : null,
    [hoveredId, data],
  )

  // Edges for the hovered node (used in hover card "top connections" section)
  const hoveredEdges = useMemo(() => {
    if (!hoveredId || !layoutData) return []
    return layoutData.cappedEdges
      .filter(e => e.source_id === hoveredId || e.target_id === hoveredId)
      .sort((a, b) => b.similarity_score - a.similarity_score)
  }, [hoveredId, layoutData])

  // Click node: first click focuses, second click on same node navigates
  const handleNodeClick = useCallback((_e: React.MouseEvent, node: Node) => {
    if (focusedNodeId === node.id) {
      navigate(`/investigations/${node.id}`)
    } else {
      setFocused(node.id)
    }
  }, [focusedNodeId, navigate])

  const handlePaneClick = useCallback(() => setFocused(null), [])

  const services = useMemo(() => {
    if (!data) return []
    const seen = new Set<string>()
    return data.nodes.filter(n => { if (seen.has(n.service_name)) return false; seen.add(n.service_name); return true })
  }, [data])

  const hasUnconnectedNodes = useMemo(() => {
    if (!data || !layoutData) return false
    const connected = new Set<string>()
    layoutData.cappedEdges.forEach(e => {
      connected.add(e.source_id)
      connected.add(e.target_id)
    })
    return data.nodes.some(n => !connected.has(n.id))
  }, [data, layoutData])

  const cappedEdgeCount = layoutData?.cappedEdges.length ?? 0
  const totalEdgeCount  = data?.stats.edge_count ?? 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>

      {/* ── Toolbar ─────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0 14px', flexWrap: 'wrap' }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
          letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-accent)',
        }}>
          Similarity Network
        </div>
        <div style={{ flex: 1, height: 1, background: 'var(--c-border)' }} />

        {data && data.stats.node_count > 0 && (
          <span style={{ fontSize: '0.62rem', color: 'var(--c-text-muted)', fontStyle: 'italic' }}>
            Click node · click again to open
          </span>
        )}

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.72rem', color: 'var(--c-text-muted)' }}>
          Min similarity
          <input type="range" min={0.05} max={0.95} step={0.05} value={minSimilarity}
            onChange={e => setMin(parseFloat(e.target.value))}
            style={{ width: 80, accentColor: 'var(--c-accent)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', minWidth: 30, color: 'var(--c-text)', fontWeight: 600 }}>
            {Math.round(minSimilarity * 100)}%
          </span>
        </label>

        <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={{
          fontSize: '0.72rem', padding: '4px 8px', borderRadius: 6,
          border: '1px solid var(--c-border)', background: 'var(--c-surface-2)', color: 'var(--c-text)',
        }}>
          {[20, 50, 100, 200].map(v => <option key={v} value={v}>{v} nodes</option>)}
        </select>

        <button onClick={load} disabled={isLoading} className="btn-primary"
          style={{ fontSize: '0.72rem', padding: '5px 14px' }}>
          {isLoading ? '…' : '↺ Refresh'}
        </button>

        {data && (
          <span style={{ fontSize: '0.68rem', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)' }}>
            {data.stats.node_count} nodes · {cappedEdgeCount} edges
          </span>
        )}
      </div>

      {error && (
        <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', color: 'var(--c-red)', fontSize: '0.8rem', marginBottom: 8 }}>
          ⚠ {error}
        </div>
      )}

      {data && totalEdgeCount === 0 && (
        <div style={{ padding: '8px 14px', borderRadius: 8, fontSize: '0.78rem', color: 'var(--c-text-muted)', background: 'var(--c-surface)', border: '1px solid var(--c-border)', marginBottom: 8 }}>
          No connections above {Math.round(minSimilarity * 100)}% similarity. Lower the threshold or wait for more investigations.
        </div>
      )}

      {/* ── Graph canvas ─────────────────────────────────────────────── */}
      <div style={{
        height: 540, borderRadius: 14,
        border: '1px solid var(--c-border)',
        overflow: 'hidden',
        background: '#f8fafc',
        boxShadow: 'inset 0 1px 4px rgba(0,0,0,0.04)',
        position: 'relative',
      }}>

        {isLoading && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
            justifyContent: 'center', background: 'rgba(248,250,252,0.9)', zIndex: 20,
            flexDirection: 'column', gap: 12,
          }}>
            <div style={{
              width: 34, height: 34, borderRadius: '50%',
              border: '3px solid rgba(79,70,229,0.15)', borderTopColor: '#4f46e5',
              animation: 'spin 0.8s linear infinite',
            }} />
            <div style={{ fontSize: '0.7rem', color: '#4f46e5', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              Building network…
            </div>
          </div>
        )}

        {!isLoading && data && (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={NODE_TYPES}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            fitView
            fitViewOptions={{ padding: 0.18 }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable
            zoomOnScroll
            panOnDrag
            selectNodesOnDrag={false}
            minZoom={0.2}
            maxZoom={3}
          >
            <Background variant={BackgroundVariant.Dots} gap={28} size={1} color="rgba(100,116,139,0.18)" />
            <Controls
              showInteractive={false}
              style={{
                background: 'rgba(255,255,255,0.95)',
                border: '1px solid #e2e8f0',
                borderRadius: 8,
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              }}
            />
          </ReactFlow>
        )}

        {!isLoading && !data && !error && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            height: '100%', color: 'var(--c-text-muted)', fontSize: '0.82rem',
            flexDirection: 'column', gap: 12,
          }}>
            <div style={{ fontSize: '2rem', opacity: 0.2 }}>⬡</div>
            Click <strong style={{ margin: '0 4px' }}>Refresh</strong> to build the network
          </div>
        )}

        {/* ── Hover / focus card (dark glass on light canvas) ─────────── */}
        {hoveredNode && (() => {
          const theme  = svcTheme(hoveredNode.service_name)
          const pColor = PRIORITY_COLOR[hoveredNode.priority] ?? '#64748b'
          const isFocused = focusedNodeId === hoveredNode.id
          return (
            <div style={{
              position: 'absolute', bottom: 16, right: 16, width: 272,
              background: 'rgba(15,23,42,0.97)',
              border: `1.5px solid ${theme.border}`,
              borderRadius: 12, padding: '14px 16px',
              boxShadow: `0 12px 40px rgba(0,0,0,0.3), 0 0 24px ${theme.glow}`,
              backdropFilter: 'blur(18px)',
              zIndex: 30, pointerEvents: 'none',
              animation: 'fadeIn 0.12s ease',
            }}>
              {/* Header: mini circle + service name + priority */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <div style={{
                  width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                  background: `radial-gradient(circle at 35% 35%, ${theme.fill}, ${theme.border}88)`,
                  border: `2px solid ${theme.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.52rem', fontWeight: 900, color: 'white',
                }}>
                  {svcInitials(hoveredNode.service_name)}
                </div>
                <span style={{
                  fontSize: '0.77rem', fontWeight: 700, flex: 1,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#f1f5f9',
                }}>
                  {hoveredNode.service_name}
                </span>
                <span style={{
                  fontSize: '0.58rem', fontWeight: 800, padding: '2px 7px', borderRadius: 5,
                  background: `${pColor}1e`, color: pColor, border: `1px solid ${pColor}44`,
                }}>
                  {hoveredNode.priority}
                </span>
              </div>

              {/* Date */}
              <div style={{ fontSize: '0.63rem', color: '#94a3b8', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
                {new Date(hoveredNode.created_at).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
              </div>

              {/* Incident label */}
              {hoveredNode.label && (
                <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 8 }}>
                  {hoveredNode.label}
                </div>
              )}

              {/* RCA summary */}
              {hoveredNode.rca_summary && (
                <div style={{
                  fontSize: '0.68rem', color: '#94a3b8', lineHeight: 1.5,
                  borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: 10, marginBottom: 10,
                  display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                }}>
                  {hoveredNode.rca_summary}
                </div>
              )}

              {/* Top connections from capped edges */}
              {hoveredEdges.length > 0 && (
                <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: 9, marginBottom: 8 }}>
                  <div style={{ fontSize: '0.56rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#475569', marginBottom: 7 }}>
                    Top connections
                  </div>
                  {hoveredEdges.map(e => {
                    const peerId = e.source_id === hoveredId ? e.target_id : e.source_id
                    const peer   = data?.nodes.find(n => n.id === peerId)
                    if (!peer) return null
                    const pt = svcTheme(peer.service_name)
                    return (
                      <div key={peerId} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                        <div style={{ width: 7, height: 7, borderRadius: '50%', background: pt.border, flexShrink: 0 }} />
                        <span style={{ fontSize: '0.63rem', color: '#e2e8f0', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {peer.service_name}
                        </span>
                        <div style={{
                          fontSize: '0.6rem', fontFamily: 'var(--font-mono)', fontWeight: 600,
                          padding: '1px 6px', borderRadius: 4,
                          background: 'rgba(79,70,229,0.22)', color: '#818cf8',
                        }}>
                          {Math.round(e.similarity_score * 100)}%
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Action hint */}
              <div style={{
                fontSize: '0.59rem', letterSpacing: '0.04em',
                color: isFocused ? '#818cf8' : '#475569',
                borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 8,
              }}>
                {isFocused
                  ? '↗ Click again to open investigation'
                  : 'Click to highlight connections · click again to open'}
              </div>
            </div>
          )
        })()}
      </div>

      {/* ── Footer: edge info + service legend ───────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 12, flexWrap: 'wrap' }}>
        {layoutData && totalEdgeCount > cappedEdgeCount && (
          <span style={{ fontSize: '0.62rem', color: 'var(--c-text-muted)', fontStyle: 'italic' }}>
            Showing top 3 connections per node ({cappedEdgeCount} of {totalEdgeCount} edges)
          </span>
        )}
        {hasUnconnectedNodes && (
          <span style={{ fontSize: '0.62rem', color: '#ea580c', fontStyle: 'italic', fontWeight: 500 }}>
            ⚠ Some service clusters are unconnected at this threshold — lower the slider to reveal cross-service edges.
          </span>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginLeft: 'auto' }}>
          {services.map(n => {
            const t = svcTheme(n.service_name)
            return (
              <span key={n.service_name} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.7rem',
                padding: '4px 10px', borderRadius: 20,
                background: t.fill, border: `1px solid ${t.border}60`,
                color: t.text, fontWeight: 600,
              }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: t.border, flexShrink: 0 }} />
                {n.service_name}
              </span>
            )
          })}
        </div>
      </div>
    </div>
  )
}
