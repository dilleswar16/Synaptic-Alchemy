import { useCallback, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  type ReactFlowInstance,
  type NodeTypes,
  type Node,
  type Edge,
  BackgroundVariant,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { fetchTopology, fetchTopologyLive, type ServiceTopology, type TopologyNode } from '../api/client'

// ── Status → accent colour ────────────────────────────────────────────────────

const STATUS_HEX: Record<string, string> = {
  hot:        '#ef4444',
  recovering: '#f59e0b',
  high:       '#22c55e',
  medium:     '#f97316',
  low:        '#94a3b8',
  observed:   '#3b82f6',
  supporting: '#60a5fa',  // steel-blue — visible on dark bg unlike slate-500
  engine:     '#f97316',  // brand orange for Corvin Engine node
}

// ── Custom node components ─────────────────────────────────────────────────────

function ServiceNode({ data }: { data: { label: string; status: string; sublabel?: string; onClick: () => void } }) {
  const accent = STATUS_HEX[data.status] ?? '#6b7280'
  return (
    <div
      onClick={data.onClick}
      style={{
        padding: '12px 18px', minWidth: 140, borderRadius: 14, cursor: 'pointer',
        background: `linear-gradient(135deg, color-mix(in srgb, ${accent} 18%, var(--c-surface)) 0%, var(--c-surface-2) 100%)`,
        border: `1.5px solid color-mix(in srgb, ${accent} 55%, var(--c-border-hi))`,
        boxShadow: `0 0 28px color-mix(in srgb, ${accent} 30%, transparent), 0 4px 16px rgba(0,0,0,0.35)`,
        textAlign: 'center',
        transition: 'box-shadow 0.2s',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: accent, borderColor: accent, width: 8, height: 8 }} />
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: accent, marginBottom: 4 }}>
        {data.sublabel ?? 'SERVICE'}
      </div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '0.88rem', color: 'var(--c-text)', letterSpacing: '0.02em' }}>
        {data.label}
      </div>
      {data.status !== 'engine' && (
        <div style={{ marginTop: 6, display: 'flex', justifyContent: 'center', gap: 4 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', padding: '2px 7px', borderRadius: 999, background: `color-mix(in srgb, ${accent} 20%, transparent)`, color: accent, border: `1px solid color-mix(in srgb, ${accent} 40%, transparent)` }}>
            {data.status}
          </span>
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: accent, borderColor: accent, width: 8, height: 8 }} />
    </div>
  )
}

// Split a k8s pod name into [deploymentBase, hashSuffix]
// e.g. "fundapis-7d9b4c8d6-xk2vq" → ["fundapis", "7d9b4c8d6-xk2vq"]
function splitPodName(name: string): [string, string] {
  const parts = name.split('-')
  // A k8s hash segment is short (≤10 chars), all lowercase alphanumeric
  const isHash = (s: string) => s.length <= 10 && /^[a-z0-9]+$/.test(s)
  let splitIdx = parts.length
  let hashCount = 0
  for (let i = parts.length - 1; i >= 0 && hashCount < 2; i--) {
    if (isHash(parts[i])) { hashCount++; splitIdx = i } else break
  }
  if (splitIdx === 0 || splitIdx === parts.length) return [name, '']
  return [parts.slice(0, splitIdx).join('-'), parts.slice(splitIdx).join('-')]
}

function PodNode({ data }: { data: { label: string; status: string; sublabel?: string } }) {
  const accent = STATUS_HEX[data.status] ?? '#6b7280'
  const [base, suffix] = splitPodName(data.label)
  const typeLabel = data.sublabel ?? 'pod'
  return (
    <div style={{
      padding: '8px 12px', minWidth: 200, borderRadius: 8,
      background: `color-mix(in srgb, ${accent} 14%, #0c0e18)`,
      border: `1px solid color-mix(in srgb, ${accent} 50%, transparent)`,
      boxShadow: `0 0 16px color-mix(in srgb, ${accent} 25%, transparent)`,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: accent, borderColor: accent, width: 6, height: 6 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: accent, boxShadow: `0 0 8px ${accent}`, flexShrink: 0 }} />
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: accent, textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 1, opacity: 0.85 }}>{typeLabel}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', fontWeight: 700, color: '#e2e8f0', lineHeight: 1.3 }}>{base}</div>
          {suffix && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: '#93c5fd', lineHeight: 1.25, marginTop: 1 }}>
              {suffix}
            </div>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: accent, borderColor: accent, width: 6, height: 6 }} />
    </div>
  )
}

function ApiNode({ data }: { data: { label: string; sublabel?: string } }) {
  return (
    <div style={{
      padding: '10px 14px', borderRadius: 10,
      background: 'linear-gradient(135deg, color-mix(in srgb, #8b5cf6 22%, var(--c-surface)) 0%, var(--c-surface-2) 100%)',
      border: '1.5px solid color-mix(in srgb, #8b5cf6 45%, var(--c-border-hi))',
      boxShadow: '0 0 20px color-mix(in srgb, #8b5cf6 22%, transparent), 0 4px 14px rgba(0,0,0,0.3)',
      textAlign: 'center', minWidth: 110,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#8b5cf6', borderColor: '#8b5cf6', width: 7, height: 7 }} />
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: '#a78bfa', marginBottom: 3 }}>{data.sublabel ?? 'API ROUTE'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '0.82rem', color: 'var(--c-text)' }}>{data.label}</div>
      <Handle type="source" position={Position.Right} style={{ background: '#8b5cf6', borderColor: '#8b5cf6', width: 7, height: 7 }} />
    </div>
  )
}

function GatewayNode({ data }: { data: { label: string; sublabel?: string } }) {
  return (
    <div style={{
      padding: '14px 20px', borderRadius: 14,
      background: 'linear-gradient(135deg, color-mix(in srgb, #0ea5e9 22%, var(--c-surface)) 0%, var(--c-surface-2) 100%)',
      border: '2px solid color-mix(in srgb, #0ea5e9 60%, var(--c-border-hi))',
      boxShadow: '0 0 36px color-mix(in srgb, #0ea5e9 32%, transparent), 0 4px 18px rgba(0,0,0,0.35)',
      textAlign: 'center', minWidth: 130,
    }}>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: '#38bdf8', marginBottom: 5 }}>{data.sublabel ?? 'APIM'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '0.9rem', color: 'var(--c-text)', letterSpacing: '0.01em' }}>{data.label}</div>
      <Handle type="source" position={Position.Right} style={{ background: '#0ea5e9', borderColor: '#0ea5e9', width: 9, height: 9 }} />
    </div>
  )
}

function BackendNode({ data }: { data: { label: string; sublabel?: string } }) {
  return (
    <div style={{
      padding: '9px 14px', borderRadius: 10,
      background: 'linear-gradient(135deg, color-mix(in srgb, #10b981 16%, var(--c-surface)) 0%, var(--c-surface-2) 100%)',
      border: '1.5px solid color-mix(in srgb, #10b981 40%, var(--c-border-hi))',
      boxShadow: '0 0 18px color-mix(in srgb, #10b981 18%, transparent), 0 4px 12px rgba(0,0,0,0.3)',
      textAlign: 'center', minWidth: 160,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#10b981', borderColor: '#10b981', width: 7, height: 7 }} />
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: '#34d399', marginBottom: 3 }}>{data.sublabel ?? 'FUNCTION APP'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem', color: 'var(--c-text)' }}>{data.label}</div>
      <Handle type="source" position={Position.Right} style={{ background: '#10b981', borderColor: '#10b981', width: 7, height: 7 }} />
    </div>
  )
}

const NODE_TYPES: NodeTypes = {
  service: ServiceNode as NodeTypes[string],
  pod:     PodNode     as NodeTypes[string],
  api:     ApiNode     as NodeTypes[string],
  gateway: GatewayNode as NodeTypes[string],
  backend: BackendNode as NodeTypes[string],
}

// ── Smart layout ──────────────────────────────────────────────────────────────
// Pods are grouped near their parent service rather than stacked as one block.
// API nodes are vertically aligned to their target services.
// Gateway is centred on all API nodes.
// Backend sits below the service column.

const SVC_X = 440
const API_X = 230
const GW_X  = 20
const POD_X = 710
const SVC_GAP = 160
const POD_GAP = 96
const CENTER_Y = 260

function buildFlowElements(topology: ServiceTopology, onServiceClick: (label: string) => void) {
  const nodeMap = new Map(topology.nodes.map(n => [n.id, n]))

  // Outbound adjacency: source → [target ids]
  const outEdges = new Map<string, string[]>()
  for (const e of topology.edges) {
    const t = outEdges.get(e.source) ?? []
    t.push(e.target)
    outEdges.set(e.source, t)
  }

  const services = topology.nodes.filter(n => n.kind === 'service')
  const apis     = topology.nodes.filter(n => n.kind === 'api')
  const gateway  = topology.nodes.find(n => n.kind === 'gateway')
  const backends = topology.nodes.filter(n => n.kind === 'backend')

  const posMap = new Map<string, { x: number; y: number }>()
  const nodes: Node[] = []

  // 1. Services — vertical stack centred
  const svcStartY = CENTER_Y - ((services.length - 1) * SVC_GAP) / 2
  services.forEach((svc, i) => {
    const y = svcStartY + i * SVC_GAP
    posMap.set(svc.id, { x: SVC_X, y })
    nodes.push({
      id: svc.id, type: 'service',
      position: { x: SVC_X, y },
      data: { label: svc.label, status: svc.status, onClick: () => onServiceClick(svc.label) },
    })
  })

  // 2. Pods — each group centred on its parent service Y, with GROUP_PAD between groups
  for (const svc of services) {
    const podIds = (outEdges.get(svc.id) ?? []).filter(id => nodeMap.get(id)?.kind === 'pod')
    if (podIds.length === 0) continue
    const svcY = posMap.get(svc.id)!.y
    const groupH = (podIds.length - 1) * POD_GAP
    const groupStartY = svcY - groupH / 2
    podIds.forEach((podId, i) => {
      const pod = nodeMap.get(podId)!
      const y = groupStartY + i * POD_GAP
      posMap.set(podId, { x: POD_X, y })
      nodes.push({ id: podId, type: 'pod', position: { x: POD_X, y }, data: { label: pod.label, status: pod.status } })
    })
  }

  // 3. API nodes — y aligned to their target service
  apis.forEach((api, i) => {
    const targetSvcIds = (outEdges.get(api.id) ?? []).filter(id => nodeMap.get(id)?.kind === 'service')
    const avgY = targetSvcIds.length > 0
      ? targetSvcIds.reduce((s, id) => s + (posMap.get(id)?.y ?? CENTER_Y), 0) / targetSvcIds.length
      : svcStartY + i * SVC_GAP
    posMap.set(api.id, { x: API_X, y: avgY })
    nodes.push({ id: api.id, type: 'api', position: { x: API_X, y: avgY }, data: { label: api.label, status: api.status } })
  })

  // 4. Gateway — centred on all API nodes
  if (gateway) {
    const apiYs = apis.map(a => posMap.get(a.id)?.y ?? CENTER_Y)
    const avgY = apiYs.length > 0 ? apiYs.reduce((a, b) => a + b, 0) / apiYs.length : CENTER_Y
    posMap.set(gateway.id, { x: GW_X, y: avgY })
    nodes.push({ id: gateway.id, type: 'gateway', position: { x: GW_X, y: avgY }, data: { label: gateway.label, status: gateway.status } })
  }

  // 5. Backend — below service column, centred between the two dependent services
  if (backends.length > 0) {
    const depSvcYs = services
      .filter(s => (outEdges.get(s.id) ?? []).some(id => nodeMap.get(id)?.kind === 'backend'))
      .map(s => posMap.get(s.id)?.y ?? CENTER_Y)
    const backendCenterY = depSvcYs.length > 0
      ? depSvcYs.reduce((a, b) => a + b, 0) / depSvcYs.length
      : CENTER_Y
    backends.forEach((backend, i) => {
      const y = backendCenterY + 180 + i * 100
      posMap.set(backend.id, { x: SVC_X, y })
      nodes.push({ id: backend.id, type: 'backend', position: { x: SVC_X, y }, data: { label: backend.label, status: backend.status } })
    })
  }

  // Edge colouring by relationship type
  const EDGE_COLOURS: Record<string, string> = {
    routes:      'rgba(139,92,246,0.65)',  // purple — APIM routing
    runs:        'rgba(249,115,22,0.55)',  // orange — service → pod
    'depends-on':'rgba(16,185,129,0.55)', // green  — service → backend
  }

  const edges: Edge[] = topology.edges.map((e, i) => {
    const colour = EDGE_COLOURS[e.label ?? ''] ?? 'rgba(249,115,22,0.55)'
    return {
      id: `e-${i}`,
      source: e.source, target: e.target,
      label: e.label ?? undefined,
      animated: true,
      style: { stroke: colour, strokeWidth: 1.8 },
      markerEnd: { type: MarkerType.ArrowClosed, color: colour, width: 16, height: 16 },
    }
  })

  return { nodes, edges }
}

// ── Corvin-flow static graph ──────────────────────────────────────────────────
// Shows HOW Corvin works, not what it monitors.
// Column order: Trigger → Evidence → Engine → Output → Action

const CORVIN_NODES: Node[] = [
  // col 0 — Trigger
  { id: 'trigger', type: 'gateway', position: { x: 20, y: 260 },
    data: { label: 'Azure Alert', sublabel: 'TRIGGER' } },

  // col 1 — Evidence adapters
  { id: 'ev-apim', type: 'api', position: { x: 220, y: 80 },
    data: { label: 'APIM Logs', sublabel: 'ADAPTER' } },
  { id: 'ev-aks', type: 'api', position: { x: 220, y: 210 },
    data: { label: 'AKS Pods', sublabel: 'ADAPTER' } },
  { id: 'ev-logs', type: 'api', position: { x: 220, y: 340 },
    data: { label: 'Container Logs', sublabel: 'ADAPTER' } },
  { id: 'ev-activity', type: 'api', position: { x: 220, y: 470 },
    data: { label: 'Activity Log', sublabel: 'ADAPTER' } },

  // col 2 — Engine (brand orange)
  { id: 'engine', type: 'service', position: { x: 440, y: 265 },
    data: { label: 'Corvin Engine', status: 'engine', sublabel: 'ENGINE', onClick: () => {} } },

  // col 3 — LLM output
  { id: 'rca', type: 'pod', position: { x: 650, y: 185 },
    data: { label: 'RCA · GPT-5.1', status: 'high', sublabel: 'OUTPUT' } },
  { id: 'fix', type: 'pod', position: { x: 650, y: 325 },
    data: { label: 'Fix Strategy', status: 'high', sublabel: 'OUTPUT' } },

  // col 4 — Human approval gate
  { id: 'approval', type: 'backend', position: { x: 860, y: 255 },
    data: { label: 'Human Approval', sublabel: 'TEAMS / UI' } },

  // col 5 — Execution + delivery
  { id: 'execute', type: 'service', position: { x: 1060, y: 185 },
    data: { label: 'Execute Fix', status: 'high', sublabel: 'AKS · kubectl', onClick: () => {} } },
  { id: 'notify', type: 'gateway', position: { x: 1060, y: 330 },
    data: { label: 'Teams + Email', sublabel: 'DELIVERY' } },
]

const CORVIN_EDGES: Edge[] = [
  // trigger → evidence (cyan)
  { id: 'ce1', source: 'trigger', target: 'ev-apim', animated: true, label: 'fires',
    style: { stroke: 'rgba(14,165,233,0.65)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(14,165,233,0.65)', width: 15, height: 15 } },
  { id: 'ce2', source: 'trigger', target: 'ev-aks', animated: true,
    style: { stroke: 'rgba(14,165,233,0.65)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(14,165,233,0.65)', width: 15, height: 15 } },
  { id: 'ce3', source: 'trigger', target: 'ev-logs', animated: true,
    style: { stroke: 'rgba(14,165,233,0.65)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(14,165,233,0.65)', width: 15, height: 15 } },
  { id: 'ce4', source: 'trigger', target: 'ev-activity', animated: true,
    style: { stroke: 'rgba(14,165,233,0.65)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(14,165,233,0.65)', width: 15, height: 15 } },
  // evidence → engine (orange)
  { id: 'ce5', source: 'ev-apim', target: 'engine', animated: true, label: 'enrich',
    style: { stroke: 'rgba(249,115,22,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(249,115,22,0.55)', width: 15, height: 15 } },
  { id: 'ce6', source: 'ev-aks', target: 'engine', animated: true,
    style: { stroke: 'rgba(249,115,22,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(249,115,22,0.55)', width: 15, height: 15 } },
  { id: 'ce7', source: 'ev-logs', target: 'engine', animated: true,
    style: { stroke: 'rgba(249,115,22,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(249,115,22,0.55)', width: 15, height: 15 } },
  { id: 'ce8', source: 'ev-activity', target: 'engine', animated: true,
    style: { stroke: 'rgba(249,115,22,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(249,115,22,0.55)', width: 15, height: 15 } },
  // engine → output (green)
  { id: 'ce9', source: 'engine', target: 'rca', animated: true, label: 'generates',
    style: { stroke: 'rgba(34,197,94,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(34,197,94,0.6)', width: 15, height: 15 } },
  { id: 'ce10', source: 'engine', target: 'fix', animated: true,
    style: { stroke: 'rgba(34,197,94,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(34,197,94,0.6)', width: 15, height: 15 } },
  // output → approval (purple)
  { id: 'ce11', source: 'rca', target: 'approval', animated: true, label: 'awaits',
    style: { stroke: 'rgba(139,92,246,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(139,92,246,0.6)', width: 15, height: 15 } },
  { id: 'ce12', source: 'fix', target: 'approval', animated: true,
    style: { stroke: 'rgba(139,92,246,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(139,92,246,0.6)', width: 15, height: 15 } },
  // approval → execution (amber)
  { id: 'ce13', source: 'approval', target: 'execute', animated: true, label: 'approved',
    style: { stroke: 'rgba(245,158,11,0.7)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(245,158,11,0.7)', width: 15, height: 15 } },
  { id: 'ce14', source: 'approval', target: 'notify', animated: true,
    style: { stroke: 'rgba(245,158,11,0.7)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(245,158,11,0.7)', width: 15, height: 15 } },
]

// ── Inner flow ────────────────────────────────────────────────────────────────

function TopologyFlow({ appNodes, appEdges }: { appNodes: Node[]; appEdges: Edge[] }) {
  const [nodes, , onNodesChange] = useNodesState(appNodes)
  const [edges, , onEdgesChange] = useEdgesState(appEdges)

  const handleInit = useCallback((instance: ReactFlowInstance) => {
    setTimeout(() => instance.fitView({ padding: 0.1, duration: 700 }), 300)
  }, [])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={NODE_TYPES}
      colorMode="dark"
      fitView
      fitViewOptions={{ padding: 0.1 }}
      onInit={handleInit}
      minZoom={0.25}
      maxZoom={2.5}
      proOptions={{ hideAttribution: true }}
      style={{ background: 'transparent' }}
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={22}
        size={1.2}
        color="rgba(249,115,22,0.14)"
      />
      <Controls
        showInteractive={false}
        style={{
          background: 'rgba(15,17,24,0.85)',
          border: '1px solid rgba(249,115,22,0.2)',
          borderRadius: 8,
          overflow: 'hidden',
          backdropFilter: 'blur(8px)',
        }}
      />
    </ReactFlow>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

type ViewMode = 'app' | 'corvin'

export function TopologyRadar() {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<ViewMode>('app')

  // Live AKS pods — used for CHAD App Topology view
  const { data: liveData, isLoading: liveLoading } = useQuery({
    queryKey: ['topology-live'],
    queryFn: fetchTopologyLive,
    refetchInterval: 30_000,  // refresh every 30s so pods reflect current state
  })

  // DB-backed topology — used for Corvin Investigation Flow view
  const { data, isLoading } = useQuery({
    queryKey: ['topology'],
    queryFn: fetchTopology,
    refetchInterval: 60_000,
  })

  const onServiceClick = useCallback((label: string) => {
    navigate(`/investigations?service=${encodeURIComponent(label)}`)
  }, [navigate])

  // App view: live pods from AKS. Corvin view: DB-backed investigation graph.
  const activeSource = viewMode === 'app' ? liveData : data

  const { nodes: appNodes, edges: appEdges } = useMemo(
    () => activeSource ? buildFlowElements(activeSource, onServiceClick) : { nodes: [], edges: [] },
    [activeSource, onServiceClick],
  )

  const serviceNodes = activeSource?.nodes.filter(n => n.kind === 'service') ?? []
  const activeNodes = viewMode === 'app' ? appNodes : CORVIN_NODES
  const activeEdges = viewMode === 'app' ? appEdges : CORVIN_EDGES

  const currentlyLoading = viewMode === 'app' ? liveLoading : isLoading
  if (currentlyLoading && !activeSource) {
    return (
      <div className="panel animate-fade-up" style={{ padding: '18px 20px', overflow: 'hidden' }}>
        {/* Header skeleton */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.72rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 5 }}>
              Dependency Visualizer
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.2rem', color: 'var(--c-text)' }}>
              {viewMode === 'app' ? 'CHAD App Topology' : 'Corvin Investigation Flow'}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 10, padding: 3 }}>
            {(['app', 'corvin'] as ViewMode[]).map(mode => (
              <button key={mode} onClick={() => setViewMode(mode)} style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 700,
                padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                letterSpacing: '0.06em', textTransform: 'uppercase', transition: 'all 0.18s',
                background: viewMode === mode ? (mode === 'app' ? '#f97316' : '#f59e0b') : 'transparent',
                color: viewMode === mode ? '#0d0f17' : 'var(--c-text-dim)',
              }}>
                {mode === 'app' ? 'App Architecture' : 'Corvin Flow'}
              </button>
            ))}
          </div>
        </div>
        {/* Canvas loading state */}
        <div style={{
          height: 500, borderRadius: 12, border: '1px solid var(--c-border)',
          background: 'linear-gradient(160deg, #0d0f17 0%, #111420 100%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 18,
        }}>
          {/* Pulsing ring */}
          <div style={{ position: 'relative', width: 64, height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '2px solid rgba(249,115,22,0.15)', animation: 'signal-pulse 2s ease-in-out infinite' }} />
            <div style={{ position: 'absolute', inset: 8, borderRadius: '50%', border: '2px solid rgba(249,115,22,0.25)', animation: 'signal-pulse 2s ease-in-out infinite 0.3s' }} />
            <span style={{ width: 28, height: 28, borderRadius: '50%', border: '2.5px solid rgba(249,115,22,0.3)', borderTopColor: '#f97316', display: 'inline-block', animation: 'spin 0.85s linear infinite' }} />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.72rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 6 }}>
              {viewMode === 'app' ? 'Connecting to AKS Cluster' : 'Loading Graph'}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', lineHeight: 1.8 }}>
              {viewMode === 'app'
                ? <>Querying live pod state · namespace <span style={{ color: 'var(--c-text-dim)' }}>chad</span></>
                : 'Loading investigation topology…'}
            </div>
            {viewMode === 'app' && (
              <div style={{ marginTop: 14, display: 'flex', gap: 8, justifyContent: 'center' }}>
                {['fundapis', 'fundsso', 'partnerapis'].map((s, i) => (
                  <span key={s} style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '3px 9px',
                    borderRadius: 999, border: '1px solid rgba(249,115,22,0.2)',
                    background: 'rgba(249,115,22,0.06)', color: 'var(--c-text-faint)',
                    animation: `signal-pulse 1.8s ease-in-out ${i * 0.25}s infinite`,
                  }}>{s}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="panel animate-fade-up" style={{ padding: '18px 20px', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.72rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 5 }}>
            Dependency Visualizer
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '1.2rem', color: 'var(--c-text)' }}>
            {viewMode === 'app' ? 'CHAD App Topology' : 'Corvin Investigation Flow'}
          </div>
        </div>

        {/* Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 10, padding: 3 }}>
          {(['app', 'corvin'] as ViewMode[]).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 700,
                padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                letterSpacing: '0.06em', textTransform: 'uppercase',
                transition: 'all 0.18s',
                background: viewMode === mode ? (mode === 'app' ? '#f97316' : '#f59e0b') : 'transparent',
                color: viewMode === mode ? '#0d0f17' : 'var(--c-text-dim)',
                boxShadow: viewMode === mode ? `0 0 18px ${mode === 'app' ? 'rgba(249,115,22,0.5)' : 'rgba(245,158,11,0.5)'}` : 'none',
              }}
            >
              {mode === 'app' ? 'App Architecture' : 'Corvin Flow'}
            </button>
          ))}
        </div>
      </div>

      {/* React Flow canvas */}
      <div style={{
        height: 500, borderRadius: 12, overflow: 'hidden',
        border: '1px solid var(--c-border)',
        background: 'linear-gradient(160deg, #0d0f17 0%, #111420 100%)',
        position: 'relative',
      }}>
        {/* Loading overlay — shown while fetching */}
        {currentlyLoading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 10, background: 'rgba(13,15,23,0.85)', backdropFilter: 'blur(4px)' }}>
            <span style={{ width: 32, height: 32, borderRadius: '50%', border: '2.5px solid rgba(249,115,22,0.3)', borderTopColor: '#f97316', display: 'inline-block', animation: 'spin 0.9s linear infinite', marginBottom: 12 }} />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-signal)', letterSpacing: '0.1em' }}>
              {viewMode === 'app' ? 'QUERYING AKS CLUSTER…' : 'LOADING GRAPH…'}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', marginTop: 4 }}>
              {viewMode === 'app' ? 'Fetching live pod state from chad namespace' : ''}
            </div>
          </div>
        )}
        {/* Empty state — data loaded but no nodes (AKS unreachable, kubeconfig missing) */}
        {!currentlyLoading && activeNodes.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', textAlign: 'center', lineHeight: 2 }}>
              {viewMode === 'app'
                ? <>No live pod data available.<br /><span style={{ fontSize: '0.65rem' }}>AKS cluster unreachable — check kubeconfig or cluster access.</span></>
                : <>No investigation data yet.<br /><span style={{ fontSize: '0.65rem' }}>Run an investigation to populate this graph.</span></>}
            </div>
          </div>
        )}
        <ReactFlowProvider>
          <TopologyFlow key={viewMode} appNodes={activeNodes} appEdges={activeEdges} />
        </ReactFlowProvider>
      </div>

      {/* Footer — service chips for app view, legend for corvin view */}
      {viewMode === 'app' ? (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
          {serviceNodes.map((node: TopologyNode) => (
            <Link key={node.id} to={`/investigations?service=${encodeURIComponent(node.label)}`} style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '5px 10px', borderRadius: 999,
              border: '1px solid var(--c-border)', background: 'var(--c-surface-2)', color: 'var(--c-text-dim)', textDecoration: 'none',
            }}>
              {node.label}
            </Link>
          ))}
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 14 }}>
          {[
            { colour: 'rgba(14,165,233,0.8)',  label: 'Alert fires evidence gathering' },
            { colour: 'rgba(249,115,22,0.8)',  label: 'Evidence enriches engine' },
            { colour: 'rgba(34,197,94,0.8)',   label: 'Engine generates RCA + Fix' },
            { colour: 'rgba(139,92,246,0.8)',  label: 'Awaits human approval' },
            { colour: 'rgba(245,158,11,0.9)',  label: 'Approved → Execute + Notify' },
          ].map(({ colour, label }) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 24, height: 2, background: colour, borderRadius: 2, display: 'inline-block' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-dim)' }}>{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}