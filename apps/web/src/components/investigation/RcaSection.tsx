/**
 * RcaSection — Root Cause Analysis panel with confidence meter,
 * root cause card, analysis summary, contributing factors, and fix strategy preview.
 */
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Section } from '../Section'
import { SemanticMarkdown } from '../SemanticMarkdown'
import { emailRcaPdf, syncAzureBoards, syncServiceNow } from '../../api/client'
import { FixStrategyFlowchart } from './FixStrategyFlowchart'
import { exportRcaPdf } from '../../utils/rcaPdf'
import type { InvestigationResult } from '../../api/client'
import { WarRoomTerminal } from './WarRoomTerminal'

interface RcaSectionProps {
  data: InvestigationResult
  requestId: string
}

export function RcaSection({ data, requestId }: RcaSectionProps) {
  const { rca, fix_strategy, request } = data
  const [syncOutcome, setSyncOutcome] = useState<{ provider: string; id: string | null; ok: boolean; message: string } | null>(null)
  const [showWarRoom, setShowWarRoom] = useState(false)

  if (!rca) return null

  const emailMutation = useMutation({
    mutationFn: () => emailRcaPdf(requestId),
    onSuccess: (resp) => setSyncOutcome({ provider: 'Email', id: null, ok: resp.sent, message: resp.message }),
    onError: (err: Error) => setSyncOutcome({ provider: 'Email', id: null, ok: false, message: err.message }),
  })

  const syncAdoMutation = useMutation({
    mutationFn: () => syncAzureBoards(requestId),
    onSuccess: (resp) => setSyncOutcome({ provider: 'Azure Boards', id: resp.ticket_id, ok: true, message: resp.message }),
    onError: (err: Error) => setSyncOutcome({ provider: 'Azure Boards', id: null, ok: false, message: err.message }),
  })

  const syncSnowMutation = useMutation({
    mutationFn: () => syncServiceNow(requestId),
    onSuccess: (resp) => setSyncOutcome({ provider: 'ServiceNow', id: resp.ticket_id, ok: true, message: resp.message }),
    onError: (err: Error) => setSyncOutcome({ provider: 'ServiceNow', id: null, ok: false, message: err.message }),
  })

  const [pdfLoading, setPdfLoading] = useState(false)

  const handleExportPdf = async () => {
    if (pdfLoading) return
    setPdfLoading(true)
    try { await exportRcaPdf(data) }
    catch (err: unknown) { setSyncOutcome({ provider: 'PDF', id: null, ok: false, message: (err as Error).message }) }
    finally { setPdfLoading(false) }
  }

  const confColor = rca.confidence === 'high' ? 'var(--c-green)'
    : rca.confidence === 'low' ? 'var(--c-red)'
    : 'var(--c-yellow)'

  const confWidth = rca.confidence === 'high' ? '85%'
    : rca.confidence === 'medium' ? '52%'
    : '20%'

  const confClass = rca.confidence === 'high' ? 'badge-approved'
    : rca.confidence === 'low' ? 'badge-rejected'
    : 'badge-pending'

  return (
    <Section
      title="Root Cause Analysis"
      headerRight={
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="btn-ghost" style={{ fontSize: '0.65rem', padding: '3px 8px' }} onClick={() => syncAdoMutation.mutate()} disabled={syncAdoMutation.isPending}>
            {syncAdoMutation.isPending ? 'Syncing…' : 'Azure Boards'}
          </button>
          <button className="btn-ghost" style={{ fontSize: '0.65rem', padding: '3px 8px' }} onClick={() => syncSnowMutation.mutate()} disabled={syncSnowMutation.isPending}>
            {syncSnowMutation.isPending ? 'Syncing…' : 'ServiceNow'}
          </button>
          <div style={{ width: 1, height: 16, background: 'var(--c-border)', margin: '0 4px' }} />
          <button className="btn-ghost" style={{ fontSize: '0.65rem', padding: '3px 8px', color: pdfLoading ? 'var(--c-text-faint)' : undefined }} onClick={handleExportPdf} disabled={pdfLoading}>
            {pdfLoading ? '⏳…' : '📄 Export PDF'}
          </button>
          <button className="btn-ghost" style={{ fontSize: '0.65rem', padding: '3px 8px' }} onClick={() => emailMutation.mutate()} disabled={emailMutation.isPending}>
            {emailMutation.isPending ? '...' : '✉ Mail'}
          </button>
          <button className="btn-primary" style={{ fontSize: '0.65rem', padding: '3px 8px', background: 'var(--c-purple)', color: 'white', border: 'none' }} onClick={() => setShowWarRoom(true)} disabled={showWarRoom}>
            ⚔️ Challenge RCA
          </button>
        </div>
      }
    >
      {syncOutcome && (
        <div style={{
          marginBottom: 16, padding: '10px 14px', borderRadius: 8,
          border: `1px solid ${syncOutcome.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
          background: syncOutcome.ok ? 'rgba(34,197,94,0.05)' : 'rgba(239,68,68,0.05)',
          color: syncOutcome.ok ? 'var(--c-green)' : 'var(--c-red)',
          fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <div>
            <span style={{ fontWeight: 800 }}>{syncOutcome.provider}:</span> {syncOutcome.message}
            {syncOutcome.id && <span style={{ marginLeft: 8, background: 'var(--c-border)', padding: '2px 6px', borderRadius: 4 }}>ID: {syncOutcome.id}</span>}
          </div>
          <button onClick={() => setSyncOutcome(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1rem', padding: '0 5px' }}>×</button>
        </div>
      )}

      {showWarRoom && <WarRoomTerminal requestId={requestId} onClose={() => setShowWarRoom(false)} />}

      {/* Confidence bar */}
      <div style={{ marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: rca.confidence_reasoning ? 10 : 0 }}>
          <span className={`badge ${confClass}`}>{rca.confidence} confidence</span>
          <div style={{ flex: 1, height: 3, background: 'var(--c-surface-3)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%', width: confWidth,
              background: confColor, borderRadius: 2,
              transition: 'width 0.8s ease',
            }} />
          </div>
        </div>
        {rca.confidence_reasoning && (
          <details style={{
            background: 'var(--c-surface-2)',
            border: '1px solid var(--c-border)',
            borderRadius: 6,
            overflow: 'hidden',
          }}>
            <summary style={{
              padding: '10px 14px',
              fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
              letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--c-signal)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
              listStyle: 'none', userSelect: 'none',
              background: 'var(--c-signal-glow)',
            }}>
              <span style={{ fontSize: '0.9rem' }}>🧠</span> What Would a Senior SRE Do? · Corvin's Rationale
            </summary>
            <div style={{
              padding: '12px 14px 14px',
              borderTop: '1px solid var(--c-border)',
              fontFamily: 'var(--font-body)', fontSize: '0.85rem',
              color: 'var(--c-text-dim)', lineHeight: 1.6,
            }}>
              {rca.confidence_reasoning}
            </div>
          </details>
        )}
      </div>

      {/* Executive Overview Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 24 }}>
        <div style={{ padding: '16px', background: 'var(--c-error-bg)', border: '1px solid var(--c-error-border)', borderRadius: 10 }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 800, color: 'var(--c-red)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Primary Root Cause</div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--c-text)', lineHeight: 1.4 }}>{rca.root_cause}</div>
        </div>
        <div style={{ padding: '16px', background: 'var(--c-signal-light)', border: '1px solid var(--c-signal-dim)', borderRadius: 10 }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 800, color: 'var(--c-signal)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Service Context</div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--c-text)', lineHeight: 1.4 }}>
            {request.service_name} <span style={{ opacity: 0.5, fontWeight: 400 }}>in</span> {request.environment}
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', marginTop: 4 }}>Trigger: {request.trigger_source}</div>
        </div>
      </div>

      {/* Analysis summary */}
      <div style={{ marginBottom: 24 }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
          letterSpacing: '0.14em', textTransform: 'uppercase',
          color: 'var(--c-text-muted)', marginBottom: 12,
        }}>
          Detailed Analysis
        </div>
        <div className="pm-prose" style={{ color: 'var(--c-text-dim)', fontSize: '0.88rem' }}>
          <SemanticMarkdown>{rca.summary}</SemanticMarkdown>
        </div>
      </div>

      {/* Decision Flowchart */}
      {fix_strategy && <FixStrategyFlowchart serviceName={request.service_name} actions={fix_strategy.actions} rcaConfidence={rca.confidence} />}

      {/* Contributing factors */}
      {rca.contributing_factors?.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
            letterSpacing: '0.14em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)', marginBottom: 12,
          }}>
            Contributing Factors
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {rca.contributing_factors.map((f: string, i: number) => {
              const fl = f.toLowerCase()
              const chipLabel = (fl.includes('no ') || fl.includes('not ') || fl.includes('healthy') || fl.includes('no issue'))
                ? 'no issue'
                : (fl.includes('pod') || fl.includes('node') || fl.includes('cluster') || fl.includes('aks') || fl.includes('memory') || fl.includes('cpu') || fl.includes('network') || fl.includes('disk'))
                ? 'infra'
                : (fl.includes('deploy') || fl.includes('config') || fl.includes('change') || fl.includes('release'))
                ? 'change'
                : 'app'

              const chipColor = chipLabel === 'no issue' ? 'var(--c-text-faint)'
                : chipLabel === 'infra' ? 'var(--c-yellow)'
                : chipLabel === 'change' ? 'var(--c-signal)'
                : 'var(--c-text-muted)'

              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10,
                  padding: '12px',
                  background: 'var(--c-surface-2)',
                  border: '1px solid var(--c-border)',
                  borderRadius: 8,
                }}>
                  <span style={{ fontSize: '0.8rem', marginTop: 2 }}>{chipLabel === 'no issue' ? '✅' : '🔴'}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                      fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase',
                      color: chipColor, marginBottom: 4
                    }}>
                      {chipLabel}
                    </div>
                    <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem', color: 'var(--c-text-dim)', lineHeight: 1.4 }}>
                      {f}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Fix strategy preview (inline at bottom of RCA) */}
      <div style={{ paddingTop: 20, borderTop: '1px solid var(--c-border)' }}>
        {fix_strategy && fix_strategy.actions?.length > 0 ? (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16,
            padding: '16px',
            background: 'linear-gradient(135deg, var(--c-signal-light), rgba(0,0,0,0))',
            border: '1px solid var(--c-signal-dim)',
            borderRadius: 12,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontSize: '0.68rem', fontWeight: 800,
                letterSpacing: '0.14em', textTransform: 'uppercase',
                color: 'var(--c-signal)', marginBottom: 4,
              }}>
                Proposed Fix Strategy
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.85rem', color: 'var(--c-text)', fontWeight: 500 }}>
                {fix_strategy.summary}
              </p>
            </div>
            <Link
              to={`/investigations/${requestId}/fix-strategy`}
              style={{
                flexShrink: 0,
                fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '0.65rem',
                letterSpacing: '0.08em', textTransform: 'uppercase',
                color: 'white', textDecoration: 'none',
                padding: '8px 16px', borderRadius: 6,
                background: 'var(--c-signal)',
                boxShadow: '0 1px 4px rgba(0,0,0,0.2)',
                whiteSpace: 'nowrap',
              }}
            >
              Review Actions →
            </Link>
          </div>
        ) : fix_strategy ? (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 14px',
            borderRadius: 10,
            background: 'var(--c-success-bg)',
            border: '1px solid var(--c-success-border)',
            color: 'var(--c-green)',
            fontFamily: 'var(--font-body)',
            fontSize: '0.82rem',
            lineHeight: 1.45,
          }}>
            <span style={{ fontWeight: 800 }}>✓ No action needed.</span>
            <span style={{ color: 'var(--c-text-dim)' }}>
              RCA indicates this was a healthy/informational check, so no remediation actions are required.
            </span>
          </div>
        ) : (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)',
          }}>
            Fix strategy not yet available.
          </div>
        )}
      </div>
    </Section>
  )
}
