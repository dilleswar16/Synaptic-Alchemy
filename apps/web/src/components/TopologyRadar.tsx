import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { useTheme } from '../context/ThemeContext'

// ── Status → accent colour ────────────────────────────────────────────────────

const STATUS_HEX: Record<string, string> = {
  hot:        'var(--c-red)',
  recovering: 'var(--c-warning)',
  high:       'var(--c-green)',
  medium:     'var(--c-signal)',
  low:        'var(--c-text-faint)',
  observed:   'var(--c-info)',
  supporting: 'var(--c-info)',
  engine:     'var(--c-signal)',
}

const STATUS_LABEL: Record<string, string> = {
  high: 'healthy',
  hot: 'unhealthy',
  recovering: 'degraded',
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

// ── Custom node components ─────────────────────────────────────────────────────

function ServiceNode({ data }: { data: { label: string; status: string; sublabel?: string; cpu_mcores?: number | null; cpu_request_mcores?: number | null; cpu_limit_mcores?: number | null; cpu_utilization_pct?: number | null; memory_mib?: number | null; memory_request_mib?: number | null; memory_limit_mib?: number | null; memory_utilization_pct?: number | null; onClick: () => void } }) {
  const accent = STATUS_HEX[data.status] ?? 'var(--c-text-faint)'
  const serviceHealthLabel = statusLabel(data.status)
  const showMetrics =
    typeof data.cpu_mcores === 'number'
    || typeof data.memory_mib === 'number'
    || typeof data.cpu_limit_mcores === 'number'
    || typeof data.memory_limit_mib === 'number'
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
            {serviceHealthLabel}
          </span>
        </div>
      )}
      {showMetrics && (
        <div style={{ marginTop: 6, display: 'grid', justifyItems: 'center', gap: 2 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-dim)' }}>
            CPU {typeof data.cpu_mcores === 'number' ? data.cpu_mcores : '-'} / {typeof data.cpu_limit_mcores === 'number' ? data.cpu_limit_mcores : '-'} mC
            {typeof data.cpu_utilization_pct === 'number' ? ` (${data.cpu_utilization_pct}%)` : ''}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-dim)' }}>
            Memory {typeof data.memory_mib === 'number' ? data.memory_mib : '-'} / {typeof data.memory_limit_mib === 'number' ? data.memory_limit_mib : '-'} MiB
            {typeof data.memory_utilization_pct === 'number' ? ` (${data.memory_utilization_pct}%)` : ''}
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

function PodNode({ data }: { data: { label: string; status: string; sublabel?: string; cpu_mcores?: number | null; cpu_request_mcores?: number | null; cpu_limit_mcores?: number | null; cpu_utilization_pct?: number | null; memory_mib?: number | null; memory_request_mib?: number | null; memory_limit_mib?: number | null; memory_utilization_pct?: number | null; phase?: string | null; ready_containers?: number | null; total_containers?: number | null; restart_count?: number | null; unhealthy_containers?: number | null } }) {
  const accent = STATUS_HEX[data.status] ?? 'var(--c-text-faint)'
  const healthLabel = statusLabel(data.status)
  const [base, suffix] = splitPodName(data.label)
  const typeLabel = data.sublabel ?? 'pod'
  const ready = typeof data.ready_containers === 'number' ? data.ready_containers : 0
  const total = typeof data.total_containers === 'number' ? data.total_containers : 0
  const restarts = typeof data.restart_count === 'number' ? data.restart_count : 0
  const cpu = typeof data.cpu_mcores === 'number' ? data.cpu_mcores : null
  const cpuLimit = typeof data.cpu_limit_mcores === 'number' ? data.cpu_limit_mcores : null
  const cpuPct = typeof data.cpu_utilization_pct === 'number' ? data.cpu_utilization_pct : null
  const memory = typeof data.memory_mib === 'number' ? data.memory_mib : null
  const memoryLimit = typeof data.memory_limit_mib === 'number' ? data.memory_limit_mib : null
  const memoryPct = typeof data.memory_utilization_pct === 'number' ? data.memory_utilization_pct : null
  const phase = data.phase ?? 'Unknown'
  const showRuntimeMetrics = true
  const healthBadgeLabel = healthLabel.charAt(0).toUpperCase() + healthLabel.slice(1)
  const healthTooltip = `Health: ${healthLabel}. Phase: ${phase}. Ready: ${ready}/${total}. Restarts: ${restarts}.`

  const metricPill = (label: string, value: string) => (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      fontFamily: 'var(--font-mono)',
      fontSize: '0.61rem',
      color: 'var(--c-text-dim)',
      padding: '2px 7px',
      borderRadius: 999,
      border: `1px solid color-mix(in srgb, ${accent} 36%, transparent)`,
      background: `color-mix(in srgb, ${accent} 10%, transparent)`,
    }}>
      <span>{label} {value}</span>
    </span>
  )

  return (
    <div style={{
      padding: '8px 12px', minWidth: 200, borderRadius: 8,
      background: `color-mix(in srgb, ${accent} 14%, var(--c-surface))`,  
      border: `1px solid color-mix(in srgb, ${accent} 50%, transparent)`,
      boxShadow: `0 0 16px color-mix(in srgb, ${accent} 25%, transparent)`,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: accent, borderColor: accent, width: 6, height: 6 }} />
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: accent, boxShadow: `0 0 8px ${accent}`, flexShrink: 0 }} />
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: accent, textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 1, opacity: 0.85 }}>{typeLabel}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', fontWeight: 700, color: accent, lineHeight: 1.3 }}>{base}</div>
            {suffix && (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: accent, lineHeight: 1.25, marginTop: 1, opacity: 0.9 }}>
                {suffix}
              </div>
            )}
          </div>
        </div>
        <span
          title={healthTooltip}
          aria-label={healthTooltip}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.62rem',
            fontWeight: 800,
            padding: '2px 8px',
            borderRadius: 999,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: `1px solid color-mix(in srgb, ${accent} 48%, transparent)`,
            color: accent,
            background: `color-mix(in srgb, ${accent} 14%, transparent)`,
            cursor: 'help',
            flexShrink: 0,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          {healthBadgeLabel}
        </span>
      </div>
      {showRuntimeMetrics && (
        <div style={{ display: 'grid', gap: 6, marginTop: 7 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-dim)' }}>
              phase: {phase}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-dim)' }}>
              ready: {ready}/{total}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: restarts > 0 ? 'var(--c-warning)' : 'var(--c-text-dim)' }}>
              restarts: {restarts}
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {cpu !== null && metricPill('CPU', `${cpu}${cpuLimit !== null ? `/${cpuLimit}` : ''} mC${cpuPct !== null ? ` (${cpuPct}%)` : ''}`)}
            {memory !== null && metricPill('Memory', `${memory}${memoryLimit !== null ? `/${memoryLimit}` : ''} MiB${memoryPct !== null ? ` (${memoryPct}%)` : ''}`)}
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: accent, borderColor: accent, width: 6, height: 6 }} />
    </div>
  )
}

function ApiNode({ data }: { data: { label: string; sublabel?: string } }) {
  return (
    <div style={{
      padding: '10px 14px', borderRadius: 10,
      background: 'linear-gradient(135deg, color-mix(in srgb, var(--c-purple) 22%, var(--c-surface)) 0%, var(--c-surface-2) 100%)',
      border: '1.5px solid color-mix(in srgb, var(--c-purple) 45%, var(--c-border-hi))',
      boxShadow: '0 0 20px color-mix(in srgb, var(--c-purple) 22%, transparent), 0 4px 14px rgba(0,0,0,0.3)',
      textAlign: 'center', minWidth: 110,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: 'var(--c-purple)', borderColor: 'var(--c-purple)', width: 7, height: 7 }} />
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--c-purple)', marginBottom: 3 }}>{data.sublabel ?? 'API ROUTE'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '0.82rem', color: 'var(--c-text)' }}>{data.label}</div>
      <Handle type="source" position={Position.Right} style={{ background: 'var(--c-purple)', borderColor: 'var(--c-purple)', width: 7, height: 7 }} />
    </div>
  )
}

function GatewayNode({ data }: { data: { label: string; sublabel?: string } }) {
  return (
    <div style={{
      padding: '14px 20px', borderRadius: 14,
      background: 'linear-gradient(135deg, color-mix(in srgb, var(--c-info) 22%, var(--c-surface)) 0%, var(--c-surface-2) 100%)',
      border: '2px solid color-mix(in srgb, var(--c-info) 60%, var(--c-border-hi))',
      boxShadow: '0 0 36px color-mix(in srgb, var(--c-info) 32%, transparent), 0 4px 18px rgba(0,0,0,0.35)',
      textAlign: 'center', minWidth: 130,
    }}>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--c-info)', marginBottom: 5 }}>{data.sublabel ?? 'APIM'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 900, fontSize: '0.9rem', color: 'var(--c-text)', letterSpacing: '0.01em' }}>{data.label}</div>
      <Handle type="source" position={Position.Right} style={{ background: 'var(--c-info)', borderColor: 'var(--c-info)', width: 9, height: 9 }} />
    </div>
  )
}

function BackendNode({ data }: { data: { label: string; sublabel?: string } }) {
  return (
    <div style={{
      padding: '9px 14px', borderRadius: 10,
      background: 'linear-gradient(135deg, color-mix(in srgb, var(--c-green) 16%, var(--c-surface)) 0%, var(--c-surface-2) 100%)',
      border: '1.5px solid color-mix(in srgb, var(--c-green) 40%, var(--c-border-hi))',
      boxShadow: '0 0 18px color-mix(in srgb, var(--c-green) 18%, transparent), 0 4px 12px rgba(0,0,0,0.3)',
      textAlign: 'center', minWidth: 160,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: 'var(--c-green)', borderColor: 'var(--c-green)', width: 7, height: 7 }} />
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--c-green)', marginBottom: 3 }}>{data.sublabel ?? 'FUNCTION APP'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem', color: 'var(--c-text)' }}>{data.label}</div>
      <Handle type="source" position={Position.Right} style={{ background: 'var(--c-green)', borderColor: 'var(--c-green)', width: 7, height: 7 }} />
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
const POD_GAP = 148
const POD_CARD_HEIGHT = 92
const SERVICE_CARD_HEIGHT = 126
const SERVICE_GROUP_GAP = 58
const CENTER_Y = 320

function buildFlowElements(
  topology: ServiceTopology,
  onServiceClick: (label: string) => void,
  opts?: { runtimePodsOnly?: boolean },
) {
  if (opts?.runtimePodsOnly) {
    const pods = topology.nodes.filter((n) => n.kind === 'pod')
    const baseY = 140
    const stepY = 118
    const podNodes: Node[] = pods.map((pod, i) => ({
      id: pod.id,
      type: 'pod',
      position: { x: 420, y: baseY + i * stepY },
      data: {
        label: pod.label,
        status: pod.status,
        sublabel: [pod.cluster_name, pod.namespace].filter(Boolean).join(' • ') || undefined,
        phase: pod.phase,
        cpu_mcores: pod.cpu_mcores,
        cpu_request_mcores: pod.cpu_request_mcores,
        cpu_limit_mcores: pod.cpu_limit_mcores,
        cpu_utilization_pct: pod.cpu_utilization_pct,
        memory_mib: pod.memory_mib,
        memory_request_mib: pod.memory_request_mib,
        memory_limit_mib: pod.memory_limit_mib,
        memory_utilization_pct: pod.memory_utilization_pct,
        ready_containers: pod.ready_containers,
        total_containers: pod.total_containers,
        restart_count: pod.restart_count,
        unhealthy_containers: pod.unhealthy_containers,
      },
    }))

    const estimatedHeight = Math.max(560, 220 + Math.max(0, pods.length - 1) * stepY)
    return { nodes: podNodes, edges: [], estimatedHeight }
  }

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

  const podIdsByService = new Map<string, string[]>()
  for (const svc of services) {
    podIdsByService.set(
      svc.id,
      (outEdges.get(svc.id) ?? []).filter(id => nodeMap.get(id)?.kind === 'pod'),
    )
  }

  // 1. Services — adaptive stack centred by service/pod footprint.
  const footprints = services.map((svc) => {
    const podIds = podIdsByService.get(svc.id) ?? []
    const podGroupHeight = podIds.length > 0
      ? POD_CARD_HEIGHT + Math.max(0, (podIds.length - 1) * POD_GAP)
      : 0
    return Math.max(SERVICE_CARD_HEIGHT, podGroupHeight)
  })
  const stackHeight = footprints.reduce((sum, h) => sum + h, 0)
    + Math.max(0, (services.length - 1) * SERVICE_GROUP_GAP)
  let cursorY = CENTER_Y - stackHeight / 2

  services.forEach((svc, i) => {
    const y = cursorY + footprints[i] / 2
    cursorY += footprints[i] + SERVICE_GROUP_GAP
    posMap.set(svc.id, { x: SVC_X, y })
    nodes.push({
      id: svc.id, type: 'service',
      position: { x: SVC_X, y },
      data: {
        label: svc.label,
        status: svc.status,
        cpu_mcores: svc.cpu_mcores,
        cpu_request_mcores: svc.cpu_request_mcores,
        cpu_limit_mcores: svc.cpu_limit_mcores,
        cpu_utilization_pct: svc.cpu_utilization_pct,
        memory_mib: svc.memory_mib,
        memory_request_mib: svc.memory_request_mib,
        memory_limit_mib: svc.memory_limit_mib,
        memory_utilization_pct: svc.memory_utilization_pct,
        onClick: () => onServiceClick(svc.label),
      },
    })
  })

  // 2. Pods — each group centred on its parent service Y, with GROUP_PAD between groups
  for (const svc of services) {
    const podIds = podIdsByService.get(svc.id) ?? []
    if (podIds.length === 0) continue
    const svcY = posMap.get(svc.id)!.y
    const groupH = (podIds.length - 1) * POD_GAP
    const groupStartY = svcY - groupH / 2
    podIds.forEach((podId, i) => {
      const pod = nodeMap.get(podId)!
      const y = groupStartY + i * POD_GAP
      posMap.set(podId, { x: POD_X, y })
      nodes.push({
        id: podId,
        type: 'pod',
        position: { x: POD_X, y },
        data: {
          label: pod.label,
          status: pod.status,
          sublabel: [pod.cluster_name, pod.namespace].filter(Boolean).join(' • ') || undefined,
          phase: pod.phase,
          cpu_mcores: pod.cpu_mcores,
          cpu_request_mcores: pod.cpu_request_mcores,
          cpu_limit_mcores: pod.cpu_limit_mcores,
          cpu_utilization_pct: pod.cpu_utilization_pct,
          memory_mib: pod.memory_mib,
          memory_request_mib: pod.memory_request_mib,
          memory_limit_mib: pod.memory_limit_mib,
          memory_utilization_pct: pod.memory_utilization_pct,
          ready_containers: pod.ready_containers,
          total_containers: pod.total_containers,
          restart_count: pod.restart_count,
          unhealthy_containers: pod.unhealthy_containers,
        },
      })
    })
  }

  // 3. API nodes — y aligned to their target service
  apis.forEach((api, i) => {
    const targetSvcIds = (outEdges.get(api.id) ?? []).filter(id => nodeMap.get(id)?.kind === 'service')
    const firstServiceY = services.length > 0 ? (posMap.get(services[0].id)?.y ?? CENTER_Y) : CENTER_Y
    const avgY = targetSvcIds.length > 0
      ? targetSvcIds.reduce((s, id) => s + (posMap.get(id)?.y ?? CENTER_Y), 0) / targetSvcIds.length
      : firstServiceY + i * (SERVICE_CARD_HEIGHT + SERVICE_GROUP_GAP)
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
    const allServiceAndPodYs = nodes
      .filter(n => n.type === 'service' || n.type === 'pod')
      .map(n => n.position.y)
    const contentBottomY = allServiceAndPodYs.length > 0 ? Math.max(...allServiceAndPodYs) : CENTER_Y
    const backendCenterY = depSvcYs.length > 0
      ? depSvcYs.reduce((a, b) => a + b, 0) / depSvcYs.length
      : contentBottomY
    backends.forEach((backend, i) => {
      const y = Math.max(contentBottomY + 160, backendCenterY + 180) + i * 100
      posMap.set(backend.id, { x: SVC_X, y })
      nodes.push({ id: backend.id, type: 'backend', position: { x: SVC_X, y }, data: { label: backend.label, status: backend.status } })
    })
  }

  // Edge colouring by relationship type
  const EDGE_COLOURS: Record<string, string> = {
    routes:      'rgba(45,212,191,0.65)',   // teal — APIM routing
    runs:        'rgba(13,148,136,0.55)',   // teal — service → pod
    'depends-on':'rgba(16,185,129,0.55)', // green  — service → backend
  }

  const edges: Edge[] = topology.edges.map((e, i) => {
    const colour = EDGE_COLOURS[e.label ?? ''] ?? 'rgba(13,148,136,0.55)'
    return {
      id: `e-${i}`,
      source: e.source, target: e.target,
      label: e.label ?? undefined,
      animated: true,
      style: { stroke: colour, strokeWidth: 1.8 },
      markerEnd: { type: MarkerType.ArrowClosed, color: colour, width: 16, height: 16 },
    }
  })

  const verticalPoints = nodes.map(n => n.position.y)
  const minY = verticalPoints.length ? Math.min(...verticalPoints) : 0
  const maxY = verticalPoints.length ? Math.max(...verticalPoints) : 500
  const estimatedHeight = Math.max(620, Math.min(1300, Math.round((maxY - minY) + 420)))

  return { nodes, edges, estimatedHeight }
}

// ── Corvin-flow static graph ──────────────────────────────────────────────────
// Shows HOW Corvin works, not what it monitors.
// Column order: Trigger → Evidence → Engine → Output → Action

const CORVIN_NODES: Node[] = [
  // col 0 — Trigger
  { id: 'trigger', type: 'gateway', position: { x: 20, y: 260 },
    data: { label: 'Azure Alert', sublabel: 'TRIGGER' } },

  // col 1 — Evidence adapters
  { id: 'ev-apim', type: 'api', position: { x: 220, y: 140 },
    data: { label: 'APIM Gateway', sublabel: 'REQUESTS • ERRORS' } },
  { id: 'ev-aks', type: 'api', position: { x: 220, y: 300 },
    data: { label: 'Kubernetes', sublabel: 'CPU • MEMORY • PODS' } },
  { id: 'ev-logs', type: 'api', position: { x: 220, y: 460 },
    data: { label: 'App Logs', sublabel: 'EXCEPTIONS • LATENCY' } },

  // col 2 — Engine (brand orange)
  { id: 'engine', type: 'service', position: { x: 440, y: 265 },
    data: { label: 'Corvin Engine', status: 'engine', sublabel: 'ENGINE', onClick: () => {} } },

  // col 3 — LLM output
  { id: 'rca', type: 'pod', position: { x: 640, y: 185 },
    data: { label: 'RCA · GPT-5.1', status: 'high', sublabel: 'OUTPUT' } },
  { id: 'fix', type: 'pod', position: { x: 640, y: 325 },
    data: { label: 'Fix Strategy', status: 'high', sublabel: 'OUTPUT' } },

  // col 4 — Human approval gate
  { id: 'approval', type: 'backend', position: { x: 960, y: 255 },
    data: { label: 'Human Approval', sublabel: 'TEAMS / UI' } },

  // col 5 — Execution + delivery
  { id: 'execute', type: 'service', position: { x: 1180, y: 185 },
    data: { label: 'Execute Fix', status: 'high', sublabel: 'AKS · kubectl', onClick: () => {} } },
  { id: 'notify', type: 'gateway', position: { x: 1180, y: 330 },
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
  // evidence → engine (teal)
  { id: 'ce5', source: 'ev-apim', target: 'engine', animated: true, label: 'enrich',
    style: { stroke: 'rgba(13,148,136,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(13,148,136,0.55)', width: 15, height: 15 } },
  { id: 'ce6', source: 'ev-aks', target: 'engine', animated: true,
    style: { stroke: 'rgba(13,148,136,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(13,148,136,0.55)', width: 15, height: 15 } },
  { id: 'ce7', source: 'ev-logs', target: 'engine', animated: true,
    style: { stroke: 'rgba(13,148,136,0.55)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(13,148,136,0.55)', width: 15, height: 15 } },
  // engine → output (green)
  { id: 'ce9', source: 'engine', target: 'rca', animated: true, label: 'generates',
    style: { stroke: 'rgba(34,197,94,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(34,197,94,0.6)', width: 15, height: 15 } },
  { id: 'ce10', source: 'engine', target: 'fix', animated: true,
    style: { stroke: 'rgba(34,197,94,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(34,197,94,0.6)', width: 15, height: 15 } },
  // output → approval (slate)
  { id: 'ce11', source: 'rca', target: 'approval', animated: true, label: 'awaits',
    style: { stroke: 'rgba(100,116,139,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(100,116,139,0.6)', width: 15, height: 15 } },
  { id: 'ce12', source: 'fix', target: 'approval', animated: true,
    style: { stroke: 'rgba(100,116,139,0.6)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(100,116,139,0.6)', width: 15, height: 15 } },
  // approval → execution (amber)
  { id: 'ce13', source: 'approval', target: 'execute', animated: true, label: 'approved',
    style: { stroke: 'rgba(245,158,11,0.7)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(245,158,11,0.7)', width: 15, height: 15 } },
  { id: 'ce14', source: 'approval', target: 'notify', animated: true,
    style: { stroke: 'rgba(245,158,11,0.7)', strokeWidth: 1.8 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(245,158,11,0.7)', width: 15, height: 15 } },
]

// ── Inner flow ────────────────────────────────────────────────────────────────

function TopologyFlow({ appNodes, appEdges, colorMode }: { appNodes: Node[]; appEdges: Edge[]; colorMode: 'dark' | 'light' }) {
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
      colorMode={colorMode}
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
        color={colorMode === 'light' ? 'rgba(15,118,110,0.12)' : 'rgba(13,148,136,0.10)'}
      />
      <Controls
        showInteractive={false}
        style={{
          background: 'color-mix(in srgb, var(--c-surface) 85%, transparent)',
          border: '1px solid var(--c-border-glow)',
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

export function TopologyRadar({
  applicationId,
  appTitle,
  appOnly = false,
}: {
  applicationId?: string
  appTitle?: string
  appOnly?: boolean
}) {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<ViewMode>('app')
  const [selectedCluster, setSelectedCluster] = useState<string>('')
  const [selectedNamespace, setSelectedNamespace] = useState<string>('')
  const [reloadToken, setReloadToken] = useState(0)
  const { theme } = useTheme()
  const currentViewMode: ViewMode = appOnly ? 'app' : viewMode
  const appHeading = appTitle ? `${appTitle} Topology` : 'Application Topology'

  const { data: liveData, isLoading: liveLoading } = useQuery({
    queryKey: [
      'topology-live',
      applicationId ?? 'global',
      selectedCluster,
      selectedNamespace,
      reloadToken,
    ],
    queryFn: () => fetchTopologyLive({
      applicationId,
      clusters: selectedCluster ? [selectedCluster] : [],
      namespaces: selectedNamespace ? [selectedNamespace] : [],
    }),
    refetchInterval: 30_000,  // refresh every 30s so pods reflect current state
  })

  const { data, isLoading } = useQuery({
    queryKey: ['topology', applicationId ?? 'global'],
    queryFn: () => fetchTopology(applicationId),
    refetchInterval: 60_000,
    enabled: !appOnly,
  })

  const onServiceClick = useCallback((label: string) => {
    navigate(`/investigations?service=${encodeURIComponent(label)}`)
  }, [navigate])

  const activeSource = currentViewMode === 'app' ? liveData : data
  const metadata = liveData?.metadata
  const runtimePodsOnly = Boolean(metadata?.runtime_unmapped_pods_only && currentViewMode === 'app')

  const { nodes: appNodes, edges: appEdges, estimatedHeight: appHeight } = useMemo(
    () => activeSource ? buildFlowElements(activeSource, onServiceClick, { runtimePodsOnly }) : { nodes: [], edges: [], estimatedHeight: 560 },
    [activeSource, onServiceClick, runtimePodsOnly],
  )

  const graphHeight = currentViewMode === 'app' ? appHeight : 560

  const serviceNodes = activeSource?.nodes.filter(n => n.kind === 'service') ?? []
  const allNodes = activeSource?.nodes ?? []
  const metricsAvailableFromNodes = serviceNodes.some((n: TopologyNode) =>
    typeof n.cpu_mcores === 'number'
    || typeof n.memory_mib === 'number'
    || typeof n.cpu_limit_mcores === 'number'
    || typeof n.memory_limit_mib === 'number',
  )
  const podDataAvailableFromNodes = allNodes.some((n: TopologyNode) => n.kind === 'pod')
  const metricsAvailable = metadata?.metrics_source_ok ?? metricsAvailableFromNodes
  const podDataAvailable = metadata?.pod_source_ok ?? podDataAvailableFromNodes
  const availableClusters = metadata?.available_clusters ?? []
  const clusterNamespaces = metadata?.cluster_namespaces ?? {}
  const availableNamespaces = useMemo(() => {
    if (selectedCluster) {
      const forCluster = clusterNamespaces[selectedCluster]
      if (Array.isArray(forCluster) && forCluster.length > 0) {
        return forCluster
      }
    }
    return metadata?.available_namespaces ?? []
  }, [clusterNamespaces, metadata?.available_namespaces, selectedCluster])
  const namespaceStatus = metadata?.namespace_status ?? {}
  const activeNodes = currentViewMode === 'app' ? appNodes : CORVIN_NODES
  const activeEdges = currentViewMode === 'app' ? appEdges : CORVIN_EDGES

  useEffect(() => {
    if (selectedCluster) return
    const serverSelected = metadata?.selected_clusters?.[0]
    if (serverSelected) {
      setSelectedCluster(serverSelected)
      return
    }
  }, [metadata?.selected_clusters, selectedCluster])

  useEffect(() => {
    if (selectedNamespace) return
    const serverSelected = metadata?.selected_namespaces?.[0]
    if (serverSelected) {
      setSelectedNamespace(serverSelected)
      return
    }
  }, [metadata?.selected_namespaces, selectedNamespace])

  useEffect(() => {
    if (selectedCluster) return
    if (availableClusters.length === 1) {
      setSelectedCluster(availableClusters[0])
    }
  }, [availableClusters, selectedCluster])

  useEffect(() => {
    if (selectedNamespace) return
    if (!selectedCluster) return
    if (availableNamespaces.length === 1) {
      setSelectedNamespace(availableNamespaces[0])
    }
  }, [availableNamespaces, selectedCluster, selectedNamespace])

  const currentlyLoading = currentViewMode === 'app' ? liveLoading : isLoading
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
              {currentViewMode === 'app' ? appHeading : 'Corvin Investigation Flow'}
            </div>
          </div>
          {!appOnly && <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 10, padding: 3 }}>
            {(['app', 'corvin'] as ViewMode[]).map(mode => (
              <button key={mode} onClick={() => setViewMode(mode)} style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 700,
                padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                letterSpacing: '0.06em', textTransform: 'uppercase', transition: 'all 0.18s',
                background: viewMode === mode ? (mode === 'app' ? 'var(--c-signal)' : 'var(--c-warning)') : 'transparent',
                color: viewMode === mode ? 'var(--c-bg)' : 'var(--c-text-dim)',
              }}>
                {mode === 'app' ? 'App Architecture' : 'Corvin Flow'}
              </button>
            ))}
          </div>}
        </div>
        {/* Canvas loading state */}
        <div style={{
          height: 500, borderRadius: 12, border: '1px solid var(--c-border)',
          background: 'linear-gradient(160deg, var(--c-surface) 0%, var(--c-surface-2) 100%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 18,
        }}>
          {/* Pulsing ring */}
          <div style={{ position: 'relative', width: 64, height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '2px solid var(--c-signal-glow)', animation: 'signal-pulse 2s ease-in-out infinite' }} />
            <div style={{ position: 'absolute', inset: 8, borderRadius: '50%', border: '2px solid var(--c-border-glow)', animation: 'signal-pulse 2s ease-in-out infinite 0.3s' }} />
            <span style={{ width: 28, height: 28, borderRadius: '50%', border: '2.5px solid var(--c-border-glow)', borderTopColor: 'var(--c-signal)', display: 'inline-block', animation: 'spin 0.85s linear infinite' }} />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.72rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-signal)', marginBottom: 6 }}>
              {currentViewMode === 'app' ? 'Connecting to AKS Cluster' : 'Loading Graph'}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', lineHeight: 1.8 }}>
              {currentViewMode === 'app'
                ? <>Querying live pod state for the selected application</>
                : 'Loading investigation topology…'}
            </div>
            {currentViewMode === 'app' && serviceNodes.length > 0 && (
              <div style={{ marginTop: 14, display: 'flex', gap: 8, justifyContent: 'center' }}>
                {serviceNodes.slice(0, 4).map((s, i) => (
                  <span key={s.id ?? `${s.label}-${i}`} style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '3px 9px',
                    borderRadius: 999, border: '1px solid var(--c-signal-dim)',
                    background: 'var(--c-signal-light)', color: 'var(--c-text-faint)',
                    animation: `signal-pulse 1.8s ease-in-out ${i * 0.25}s infinite`,
                  }}>{s.label}</span>
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
            {currentViewMode === 'app' ? appHeading : 'Corvin Investigation Flow'}
          </div>
        </div>

        {!appOnly && <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 10, padding: 3 }}>
          {(['app', 'corvin'] as ViewMode[]).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 700,
                padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                letterSpacing: '0.06em', textTransform: 'uppercase',
                transition: 'all 0.18s',
                background: viewMode === mode ? (mode === 'app' ? 'var(--c-signal)' : 'var(--c-warning)') : 'transparent',
                color: viewMode === mode ? 'var(--c-bg)' : 'var(--c-text-dim)',
                boxShadow: viewMode === mode ? `0 0 18px ${mode === 'app' ? 'var(--c-signal-glow)' : 'var(--c-warning-bg)'}` : 'none',
              }}
            >
              {mode === 'app' ? 'App Architecture' : 'Corvin Flow'}
            </button>
          ))}
        </div>}
      </div>

      {currentViewMode === 'app' && (
        <div style={{ display: 'grid', gap: 10, marginBottom: 10 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            <label style={{ display: 'grid', gap: 4, minWidth: 210 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Clusters</span>
              <select
                value={selectedCluster}
                onChange={(e) => {
                  setSelectedCluster(e.currentTarget.value)
                }}
                style={{ height: 34, background: 'var(--c-surface-2)', color: 'var(--c-text)', border: '1px solid var(--c-border)', borderRadius: 8, padding: 6, fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}
              >
                <option value="">All Clusters</option>
                {availableClusters.map((cluster) => (
                  <option key={cluster} value={cluster}>{cluster}</option>
                ))}
              </select>
            </label>

            <label style={{ display: 'grid', gap: 4, minWidth: 220 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--c-text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Namespaces</span>
              <select
                value={selectedNamespace}
                onChange={(e) => {
                  setSelectedNamespace(e.currentTarget.value)
                }}
                style={{ height: 34, background: 'var(--c-surface-2)', color: 'var(--c-text)', border: '1px solid var(--c-border)', borderRadius: 8, padding: 6, fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}
              >
                <option value="">All Namespaces</option>
                {selectedNamespace && !availableNamespaces.includes(selectedNamespace) && (
                  <option value={selectedNamespace}>{selectedNamespace}</option>
                )}
                {availableNamespaces.map((ns) => (
                  <option key={ns} value={ns}>{ns}</option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={() => setReloadToken((v) => v + 1)}
              style={{
                alignSelf: 'end',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.66rem',
                fontWeight: 700,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                border: '1px solid var(--c-border-hi)',
                background: 'var(--c-surface-2)',
                color: 'var(--c-text)',
                borderRadius: 8,
                padding: '8px 12px',
                cursor: 'pointer',
              }}
            >
              Reload Topology
            </button>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.64rem',
              padding: '4px 9px',
              borderRadius: 999,
              border: '1px solid var(--c-border)',
              background: 'var(--c-surface)',
              color: 'var(--c-text-dim)',
              letterSpacing: '0.04em',
            }}>
              Active filter: {selectedCluster || 'all clusters'} / {selectedNamespace || 'all namespaces'}
            </span>
            <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.64rem',
            padding: '4px 9px',
            borderRadius: 999,
            border: `1px solid ${metricsAvailable ? 'color-mix(in srgb, var(--c-green) 55%, transparent)' : 'color-mix(in srgb, var(--c-warning) 55%, transparent)'}`,
            background: metricsAvailable ? 'color-mix(in srgb, var(--c-green) 14%, var(--c-surface))' : 'color-mix(in srgb, var(--c-warning) 14%, var(--c-surface))',
            color: metricsAvailable ? 'var(--c-green)' : 'var(--c-warning)',
            letterSpacing: '0.04em',
          }}>
            Metrics source: {metricsAvailable ? 'Container Insights data available' : 'Container Insights data unavailable'}
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.64rem',
            padding: '4px 9px',
            borderRadius: 999,
            border: `1px solid ${podDataAvailable ? 'color-mix(in srgb, var(--c-green) 55%, transparent)' : 'color-mix(in srgb, var(--c-warning) 55%, transparent)'}`,
            background: podDataAvailable ? 'color-mix(in srgb, var(--c-green) 14%, var(--c-surface))' : 'color-mix(in srgb, var(--c-warning) 14%, var(--c-surface))',
            color: podDataAvailable ? 'var(--c-green)' : 'var(--c-warning)',
            letterSpacing: '0.04em',
          }}>
            Pod source: {podDataAvailable ? 'AKS pod data available' : 'AKS pod data unavailable'}
          </span>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(namespaceStatus).map(([ns, state]) => {
              const status = String(state.status || 'high')
              const accent = STATUS_HEX[status] ?? 'var(--c-text-faint)'
              return (
                <span
                  key={ns}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.62rem',
                    padding: '4px 9px',
                    borderRadius: 999,
                    border: `1px solid color-mix(in srgb, ${accent} 55%, transparent)`,
                    background: `color-mix(in srgb, ${accent} 15%, var(--c-surface))`,
                    color: accent,
                    letterSpacing: '0.03em',
                  }}
                >
                  ns:{ns} {status} ({state.services})
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* React Flow canvas */}
      <div style={{
        height: graphHeight, borderRadius: 12, overflow: 'hidden',
        border: '1px solid var(--c-border)',
        background: 'linear-gradient(160deg, var(--c-surface) 0%, var(--c-surface-2) 100%)',
        position: 'relative',
      }}>
        {/* Loading overlay — shown while fetching */}
        {currentlyLoading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 10, background: 'color-mix(in srgb, var(--c-bg) 85%, transparent)', backdropFilter: 'blur(4px)' }}>
            <span style={{ width: 32, height: 32, borderRadius: '50%', border: '2.5px solid var(--c-border-glow)', borderTopColor: 'var(--c-signal)', display: 'inline-block', animation: 'spin 0.9s linear infinite', marginBottom: 12 }} />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-signal)', letterSpacing: '0.1em' }}>
              {currentViewMode === 'app' ? 'QUERYING AKS CLUSTER…' : 'LOADING GRAPH…'}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', marginTop: 4 }}>
              {currentViewMode === 'app' ? 'Fetching live pod state for the selected application' : ''}
            </div>
          </div>
        )}
        {/* Empty state — data loaded but no nodes (AKS unreachable, kubeconfig missing) */}
        {!currentlyLoading && activeNodes.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', textAlign: 'center', lineHeight: 2 }}>
              {currentViewMode === 'app'
                ? <>No live pod data available.<br /><span style={{ fontSize: '0.65rem' }}>AKS cluster unreachable — check kubeconfig or cluster access.</span></>
                : <>No investigation data yet.<br /><span style={{ fontSize: '0.65rem' }}>Run an investigation to populate this graph.</span></>}
            </div>
          </div>
        )}
        <ReactFlowProvider>
          <TopologyFlow key={`${currentViewMode}-${applicationId ?? 'global'}-${selectedCluster}-${selectedNamespace}-${reloadToken}-${theme}`} appNodes={activeNodes} appEdges={activeEdges} colorMode={theme} />
        </ReactFlowProvider>
      </div>

      {/* Footer — service chips for app view, legend for corvin view */}
      {viewMode === 'app' ? (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
          {serviceNodes.map((node: TopologyNode) => (
            <Link key={node.id} to={`/investigations?service=${encodeURIComponent(node.label)}`} style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '5px 10px', borderRadius: 999,
              border: '1px solid var(--c-border)', background: `color-mix(in srgb, ${STATUS_HEX[node.status] ?? 'var(--c-text-faint)'} 14%, var(--c-surface-2))`, color: STATUS_HEX[node.status] ?? 'var(--c-text-dim)', textDecoration: 'none',
            }}>
              {node.label}
            </Link>
          ))}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', marginLeft: 4 }}>
            Pod health: green=healthy, red=unhealthy, amber=degraded (restarts)
          </span>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 14 }}>
          {[
            { colour: 'rgba(14,165,233,0.8)',  label: 'Alert fires evidence gathering' },
            { colour: 'rgba(13,148,136,0.8)',  label: 'Evidence enriches engine' },
            { colour: 'rgba(34,197,94,0.8)',   label: 'Engine generates RCA + Fix' },
            { colour: 'rgba(100,116,139,0.8)',  label: 'Awaits human approval' },
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