/**
 * AuditTrailSection — collapsible 6-stage timeline showing the full investigation lifecycle.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchReplay, type ReplayPayload } from '../../api/client'
import { totalDuration, deltaLabel } from '../../utils/time'

// ── helpers ───────────────────────────────────────────────────────────────────

function _fmtTime(iso: string): string { return iso.slice(11, 19) + 'Z' }

function _evidenceMeta(ev: ReplayPayload['evidence_summary']): string {
  const parts: string[] = []
  if (ev.elastic_log_count > 0)       parts.push(`${ev.elastic_log_count} elastic logs`)
  if (ev.elastic_metric_count > 0)    parts.push(`${ev.elastic_metric_count} metrics`)
  if (ev.log_analytics_apim_count > 0) parts.push(`${ev.log_analytics_apim_count} APIM events`)
  if (ev.aks_context_keys.length > 0)  parts.push(`AKS context (${ev.aks_context_keys.join(', ')})`)
  if (ev.azure_activity_count > 0)    parts.push(`${ev.azure_activity_count} activity changes`)
  return parts.length > 0 ? parts.join(' · ') : 'No evidence collected'
}

function _approvalMeta(approval: ReplayPayload['approval']): string {
  const st = approval.status ?? 'pending'
  if (st === 'pending')  return 'Awaiting human decision'
  const by = approval.approved_by ? ` by ${approval.approved_by}` : ''
  if (st === 'approved') return `Approved${by}`
  if (st === 'rejected') return `Rejected${by}`
  if (st === 'executed') return `Executed${by}`
  return st
}

// ── AuditTimeline ─────────────────────────────────────────────────────────────

interface TimelineStage {
  label: string
  dotColor: string
  isCheck: boolean
  meta: string
  sub?: string
  chip?: string
  chipColor?: string
  timestamp: string
  delta: string
}

function AuditTimeline({ replay }: { replay: ReplayPayload }) {
  const t0 = replay.trigger.created_at
  const confColor = { high: 'var(--c-green)', medium: 'var(--c-yellow)', low: 'var(--c-red)' }[replay.rca.confidence] ?? 'var(--c-signal)'
  const approvalStatus = replay.approval.status ?? 'pending'
  const approvalColor = { pending: 'var(--c-yellow)', approved: 'var(--c-green)', rejected: 'var(--c-red)', executed: 'var(--c-green)' }[approvalStatus] ?? 'var(--c-yellow)'

  const stages: TimelineStage[] = [
    {
      label: 'Triggered',
      dotColor: 'var(--c-signal)', isCheck: false,
      meta: `${replay.trigger.service_name} / ${replay.trigger.environment} · ${replay.trigger.trigger_source.replace(/_/g, ' ')}`,
      sub: replay.trigger.description ? replay.trigger.description.slice(0, 140) + (replay.trigger.description.length > 140 ? '…' : '') : undefined,
      timestamp: _fmtTime(t0), delta: '',
    },
    {
      label: 'Evidence Collected',
      dotColor: 'var(--c-signal)', isCheck: false,
      meta: _evidenceMeta(replay.evidence_summary),
      sub: `Lookback window: ${replay.trigger.lookback_minutes} min`,
      timestamp: _fmtTime(replay.evidence_summary.collected_at),
      delta: deltaLabel(t0, replay.evidence_summary.collected_at),
    },
    {
      label: 'Root Cause Analysis',
      dotColor: confColor, isCheck: false,
      meta: replay.rca.root_cause.length > 130 ? replay.rca.root_cause.slice(0, 130) + '…' : replay.rca.root_cause,
      chip: replay.rca.confidence + ' confidence', chipColor: confColor,
      timestamp: _fmtTime(replay.rca.generated_at),
      delta: deltaLabel(t0, replay.rca.generated_at),
    },
    {
      label: 'Fix Strategy',
      dotColor: 'var(--c-signal)', isCheck: false,
      meta: replay.fix_strategy.summary.length > 130 ? replay.fix_strategy.summary.slice(0, 130) + '…' : replay.fix_strategy.summary,
      sub: `${replay.fix_strategy.action_count} action${replay.fix_strategy.action_count !== 1 ? 's' : ''}`,
      timestamp: _fmtTime(replay.fix_strategy.generated_at),
      delta: deltaLabel(t0, replay.fix_strategy.generated_at),
    },
    {
      label: 'Approval',
      dotColor: approvalColor,
      isCheck: approvalStatus === 'approved' || approvalStatus === 'executed',
      meta: _approvalMeta(replay.approval),
      chip: approvalStatus, chipColor: approvalColor,
      timestamp: replay.approval.approved_at ? _fmtTime(replay.approval.approved_at) : '—',
      delta: replay.approval.approved_at ? deltaLabel(t0, replay.approval.approved_at) : '',
    },
    {
      label: 'Complete',
      dotColor: 'var(--c-green)', isCheck: true,
      meta: `Total investigation time: ${totalDuration(t0, replay.completed_at)}`,
      timestamp: _fmtTime(replay.completed_at),
      delta: deltaLabel(t0, replay.completed_at),
    },
  ]

  return (
    <div style={{ position: 'relative', paddingLeft: 36 }}>
      <div 
        className="animate-vertical-flow"
        style={{
          position: 'absolute', left: 6, top: 8, bottom: 8, width: 2,
          background: 'linear-gradient(180deg, var(--c-signal) 0%, rgba(249,115,22,0.1) 50%, var(--c-green) 100%)',
          opacity: 0.8, borderRadius: 1,
        }} 
      />

      {stages.map((stage, i) => (
        <div key={i} style={{ position: 'relative', marginBottom: i < stages.length - 1 ? 26 : 0 }}>
          {/* dot */}
          <div style={{
            position: 'absolute', left: -30, top: 3,
            width: 14, height: 14, borderRadius: '50%',
            background: stage.dotColor,
            border: '2.5px solid var(--c-bg)',
            boxShadow: `0 0 10px ${stage.dotColor}55`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {stage.isCheck && (
              <svg width="7" height="7" viewBox="0 0 8 8" fill="none">
                <polyline points="1,4 3,6.5 7,1.5" stroke="var(--c-bg)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                <span style={{
                  fontWeight: 600, fontSize: '0.75rem',
                  letterSpacing: '0.02em', color: stage.dotColor,
                }}>
                  {stage.label}
                </span>
                {stage.chip && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.68rem', fontWeight: 700,
                    letterSpacing: '0.07em', textTransform: 'uppercase',
                    padding: '2px 7px', borderRadius: 3,
                    background: `color-mix(in srgb, ${stage.chipColor} 10%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${stage.chipColor} 27%, transparent)`,
                    color: stage.chipColor,
                  }}>
                    {stage.chip}
                  </span>
                )}
              </div>
              <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.8rem', color: 'var(--c-text-dim)', lineHeight: 1.5, marginBottom: stage.sub ? 4 : 0 }}>
                {stage.meta}
              </div>
              {stage.sub && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-muted)', letterSpacing: '0.02em' }}>
                  {stage.sub}
                </div>
              )}
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0, paddingTop: 1 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--c-text-dim)' }}>
                {stage.timestamp}
              </div>
              {stage.delta && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-signal)', marginTop: 3, letterSpacing: '0.04em' }}>
                  {stage.delta}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── AuditTrailSection ─────────────────────────────────────────────────────────

export function AuditTrailSection({ requestId, defaultOpen = false }: { requestId: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)

  const { data: replay, isLoading } = useQuery<ReplayPayload>({
    queryKey: ['replay', requestId],
    queryFn: () => fetchReplay(requestId),
    staleTime: 300_000,
    retry: false,
  })

  const duration = replay ? totalDuration(replay.trigger.created_at, replay.completed_at) : null

  return (
    <section style={{ marginTop: 20 }}>
      <div className="panel" style={{ overflow: 'hidden' }}>
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '11px 18px',
            background: 'var(--c-surface-2)',
            border: 'none',
            borderBottom: open ? '1px solid var(--c-border)' : 'none',
            cursor: 'pointer', textAlign: 'left',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{
              fontWeight: 600, fontSize: '0.75rem',
              letterSpacing: '0.02em', color: 'var(--c-text-muted)',
            }}>
              Audit Trail
            </span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
               <span style={{ 
                 fontFamily: 'var(--font-mono)', fontSize: '0.68rem', fontWeight: 800, 
                 background: 'var(--c-surface-3)', padding: '2px 6px', borderRadius: 4,
                 color: 'var(--c-text-faint)', border: '1px solid var(--c-border)'
               }}>
                 6 STAGES
               </span>
               {duration && (
                 <span style={{ 
                   fontFamily: 'var(--font-mono)', fontSize: '0.68rem', fontWeight: 800, 
                   background: 'rgba(34,197,94,0.1)', padding: '2px 6px', borderRadius: 4,
                   color: 'var(--c-green)', border: '1px solid rgba(34,197,94,0.3)'
                 }}>
                   {duration.toUpperCase()} RESOLUTION
                 </span>
               )}
            </div>
          </div>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--c-text-muted)',
            display: 'inline-block', transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s ease', lineHeight: 1,
          }}>
            ▾
          </span>
        </button>

        {open && (
          <div style={{ padding: '22px 24px 20px' }}>
            {isLoading && (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)', letterSpacing: '0.06em' }}>
                Loading audit trail…
              </div>
            )}
            {replay && <AuditTimeline replay={replay} />}
            {!isLoading && !replay && (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
                Audit data not available for this investigation.
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
