import { useEffect, useState } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Layout from '../components/Layout'
import { StatusBadge } from '../components/StatusBadge'
import { CopyableId } from '../components/CopyableId'
import { WorkflowStepper } from '../components/investigation/WorkflowStepper'
import { EvidenceSection } from '../components/investigation/EvidenceSection'
import { EvidenceReferencesSection } from '../components/investigation/EvidenceReferencesSection'
import { SimilarIncidentsSection } from '../components/investigation/SimilarIncidentsSection'
import { RcaSection } from '../components/investigation/RcaSection'
import { ApprovalSection, type ApprovalAction } from '../components/investigation/ApprovalSection'
import { ExecutionSection } from '../components/investigation/ExecutionSection'
import { AuditTrailSection } from '../components/investigation/AuditTrailSection'
import { PostMortemSection } from '../components/investigation/PostMortemSection'
import { TransparencyTrace } from '../components/investigation/TransparencyTrace'
import { IncidentHeroCard } from '../components/investigation/IncidentHeroCard'
import { RunbookUpdatePrompt } from '../components/investigation/RunbookUpdatePrompt'
import { CopilotChatWidget } from '../components/investigation/CopilotChatWidget'
import { CausalChainSection } from '../components/investigation/CausalChainSection'
import { CommsDraftSection } from '../components/investigation/CommsDraftSection'
import { TechnicalHighlighter } from '../components/TechnicalHighlighter'
import { Section } from '../components/Section'
import { BlastRadiusCard } from '../components/BlastRadiusCard'
import { SlaCountdownCard } from '../components/investigation/SlaCountdownCard'
import WarRoomBanner from '../components/WarRoomBanner'
import RunbookBuilderChat from '../components/RunbookBuilderChat'
import HypothesisDebatePanel from '../components/investigation/HypothesisDebatePanel'
import { useThreeAmMode } from '../hooks/useThreeAmMode'
import {
  fetchInvestigation,
  fetchSimilarIncidents,
  fetchReplay,
  downloadCompliancePack,
  type SimilarIncident,
  type ReplayPayload,
} from '../api/client'
import { totalDuration } from '../utils/time'

type TabId = 'rca' | 'evidence' | 'history'

export default function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  useThreeAmMode()
  const [packDownloading, setPackDownloading] = useState<false | 'pdf' | 'zip'>(false)

  const rawAction = searchParams.get('action')
  const pendingAction: ApprovalAction | null =
    rawAction === 'approve' || rawAction === 'reject' ? rawAction : null
  const clearPendingAction = () => setSearchParams({})

  const { data, isLoading, isError } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => fetchInvestigation(id!),
    enabled: !!id,
  })

  const { data: similarIncidents } = useQuery({
    queryKey: ['similar-incidents', data?.request?.service_name, data?.request?.environment],
    queryFn: () => fetchSimilarIncidents(data!.request.service_name, data!.request.environment),
    enabled: !!data?.request?.service_name,
    staleTime: 60_000,
  })

  const pastIncidents: SimilarIncident[] = (similarIncidents ?? []).filter(
    (inc) => inc.request_id !== id,
  )

  const approvalStatus = data?.request?.approval_status ?? 'pending'

  // Detect "informational" investigations: service is healthy, no real fixes needed.
  // True when every fix action is low-risk (informational review, no cluster changes).
  // We intentionally do NOT check requires_approval here — the backend forces that flag
  // via review_only policy even on harmless actions for pre-existing investigations.
  const isInformational = !!data?.fix_strategy && (
    data.fix_strategy.actions.length === 0
    || data.fix_strategy.actions.every((a) => a.risk_level === 'low')
  )
  const [activeTab, setActiveTab] = useState<TabId>('rca')

  const { data: replay } = useQuery<ReplayPayload>({
    queryKey: ['replay', id],
    queryFn: () => fetchReplay(id!),
    enabled: !!id,
    staleTime: 300_000,
    retry: false,
  })
  const rcaDuration = replay
    ? totalDuration(replay.trigger.created_at, replay.rca.generated_at)
    : null

  const hasEvidence = data
    ? (data.evidence.elastic_logs.length > 0 ||
       data.evidence.elastic_metrics.length > 0 ||
       data.evidence.log_analytics_apim.length > 0 ||
       Object.keys(data.evidence.aks_context).length > 0 ||
       data.evidence.azure_activity_changes.length > 0)
    : false
  const hasRca = !!data?.rca
  const evidenceReferences = data?.rca?.evidence_references ?? []

  const scrollAndAct = (action: ApprovalAction) => {
    setActiveTab('rca')
    setSearchParams({ action })
    setTimeout(() => {
      document.getElementById('approval-section')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
  }

  const pendingAndRcaReady = approvalStatus === 'pending' && !!data?.rca && pendingAction === null && !isInformational

  useEffect(() => {
    if (!pendingAndRcaReady) return
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'a' || e.key === 'A') scrollAndAct('approve')
      if (e.key === 'r' || e.key === 'R') scrollAndAct('reject')
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAndRcaReady])

  return (
    <Layout>
      <div style={{ maxWidth: 1200, paddingBottom: 0, width: '100%' }}>

        {/* Page header */}
        <div className="animate-fade-up" style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <Link
              to="/investigations"
              style={{
                fontFamily: 'var(--font-display)', fontSize: '0.8125rem', fontWeight: 500,
                color: 'var(--c-text-muted)', textDecoration: 'none',
              }}
            >
              ← Investigations
            </Link>
            {data && (
              <Link
                to={`/investigations?service=${encodeURIComponent(data.request.service_name)}&env=${encodeURIComponent(data.request.environment)}`}
                style={{
                  fontSize: '0.75rem', fontWeight: 500,
                  color: 'var(--c-text-muted)', textDecoration: 'none',
                  padding: '4px 10px', borderRadius: 6,
                  border: '1px solid var(--c-border)',
                  background: 'var(--c-surface-2)',
                }}
              >
                All {data.request.service_name} →
              </Link>
            )}
          </div>

          <div style={{ marginTop: 14 }}>
            <div style={{
              fontSize: '0.75rem', fontWeight: 500,
              letterSpacing: '0.03em', textTransform: 'uppercase',
              color: 'var(--c-signal)', marginBottom: 4,
            }}>
              Investigation
            </div>
            <h1 style={{
              margin: '0 0 14px',
              fontFamily: 'var(--font-display)', fontWeight: 800,
              fontSize: '1.75rem', letterSpacing: '-0.03em',
              color: 'var(--c-text)',
              lineHeight: 1.2,
            }}>
              {data?.request?.service_name ?? (isLoading ? '…' : 'Investigation')}
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {data?.request?.incident_priority && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 800,
                  padding: '3px 10px', borderRadius: 4,
                  background: data.request.incident_priority === 'P1' ? 'var(--c-error-bg)' : data.request.incident_priority === 'P2' ? 'var(--c-signal-light)' : 'var(--c-surface-2)',
                  border: data.request.incident_priority === 'P1' ? '1px solid var(--c-error-border)' : data.request.incident_priority === 'P2' ? '1px solid var(--c-signal-dim)' : '1px solid var(--c-border)',
                  color: data.request.incident_priority === 'P1' ? 'var(--c-red)' : data.request.incident_priority === 'P2' ? 'var(--c-signal)' : 'var(--c-text-muted)',
                }}>
                  {data.request.incident_priority}
                </span>
              )}
              {data?.request?.environment && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                  padding: '3px 10px', borderRadius: 6,
                  background: 'var(--c-signal-glow)',
                  border: '1px solid var(--c-border-glow)',
                  color: 'var(--c-signal)',
                }}>
                  {data.request.environment}
                </span>
              )}
              {data?.request?.trigger_source && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  padding: '3px 10px', borderRadius: 6,
                  background: 'var(--c-surface-2)',
                  border: '1px solid var(--c-border-hi)',
                  color: 'var(--c-text-dim)', letterSpacing: '0.04em',
                }}>
                  {data.request.trigger_source.replace(/_/g, ' ')}
                </span>
              )}
              {data && <StatusBadge status={approvalStatus} />}
              {data?.request?.id && <CopyableId requestId={data.request.id} />}
              {data?.ado_work_item_id && (
                <a
                  href={data.ado_url ?? '#'}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
                    padding: '3px 10px', borderRadius: 6, textDecoration: 'none',
                    background: 'var(--c-info-bg)',
                    border: '1px solid var(--c-info-border)',
                    color: 'var(--c-info)',
                  }}
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
                  </svg>
                  Azure Boards #{data.ado_work_item_id}
                </a>
              )}
              {data?.wiki_url && (
                <a
                  href={data.wiki_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
                    padding: '3px 10px', borderRadius: 6, textDecoration: 'none',
                    background: 'var(--c-warning-bg)',
                    border: '1px solid var(--c-warning-border)',
                    color: 'var(--c-amber)',
                  }}
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
                    <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
                  </svg>
                  Wiki
                </a>
              )}
              {data?.sharepoint_url && (
                <a
                  href={data.sharepoint_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
                    padding: '3px 10px', borderRadius: 6, textDecoration: 'none',
                    background: '#1a3a5c20',
                    border: '1px solid #1a3a5c40',
                    color: '#0078d4',
                  }}
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
                    <path d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.18l7 3.5v7.64l-7 3.5-7-3.5V7.68l7-3.5z"/>
                  </svg>
                  SharePoint
                </a>
              )}
              {data?.fix_strategy && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
                  padding: '3px 10px', borderRadius: 6,
                  letterSpacing: '0.03em',
                  background: isInformational ? 'var(--c-success-bg)' : 'var(--c-error-bg)',
                  border: `1px solid ${isInformational ? 'var(--c-success-border)' : 'var(--c-error-border)'}`,
                  color: isInformational ? 'var(--c-green)' : 'var(--c-red)',
                }}>
                  {isInformational ? '✓ No Action Needed' : '⚠ Fix Required'}
                </span>
              )}
              {rcaDuration && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  padding: '2px 8px', borderRadius: 6,
                  background: 'var(--c-success-bg)',
                  border: '1px solid var(--c-success-border)',
                  color: 'var(--c-green)', letterSpacing: '0.03em',
                }}>
                  ⏱ RCA in {rcaDuration}
                </span>
              )}
            </div>
          </div>

          {/* Compliance pack download button */}
          {data && (
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              {(['pdf', 'zip'] as const).map(fmt => (
                <button
                  key={fmt}
                  id={`compliance-pack-${fmt}-btn`}
                  disabled={packDownloading !== false}
                  onClick={async () => {
                    setPackDownloading(fmt)
                    try { await downloadCompliancePack(id!, fmt) }
                    catch (e) { console.error(e) }
                    finally { setPackDownloading(false) }
                  }}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700,
                    padding: '4px 11px', borderRadius: 6, border: '1px solid var(--c-border)',
                    background: 'var(--c-surface-2)', color: 'var(--c-text-muted)',
                    cursor: packDownloading ? 'wait' : 'pointer',
                    opacity: packDownloading && packDownloading !== fmt ? 0.5 : 1,
                  }}
                >
                  {packDownloading === fmt ? '⏳' : '📦'} Evidence Pack .{fmt.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Loading skeletons */}
        {isLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[260, 180, 220].map((h, i) => (
              <div key={i} style={{
                height: h, borderRadius: 4, overflow: 'hidden',
                background: 'var(--c-surface)',
                border: '1px solid var(--c-border)',
              }}>
                <div style={{ height: 36, background: 'var(--c-surface-2)', borderBottom: '1px solid var(--c-border)' }} />
                <div style={{
                  height: '100%',
                  background: 'linear-gradient(90deg, transparent 0%, var(--c-surface-2) 50%, transparent 100%)',
                  backgroundSize: '200% 100%',
                  animation: 'skeleton-sweep 1.5s ease-in-out infinite',
                }} />
              </div>
            ))}
          </div>
        )}

        {isError && (
          <div style={{
            padding: '16px 20px',
            background: 'var(--c-red-bg)', border: '1px solid var(--c-red-border)', borderRadius: 4,
            fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-red)',
          }}>
            ✗ Could not load investigation. The ID may be invalid or the server is unavailable.
          </div>
        )}

        {/* Main content */}
        {data && (
          <>
            {/* Always-visible: hero + SLA + stepper */}
            {approvalStatus === 'pending' && (
              <WarRoomBanner
                serviceName={data.request.service_name}
                environment={data.request.environment}
              />
            )}
            <IncidentHeroCard data={data} approvalStatus={approvalStatus} />
            <SlaCountdownCard requestId={id!} status={approvalStatus} />
            <div className="three-am-hide" style={{ marginTop: 4 }}>
              <WorkflowStepper approvalStatus={approvalStatus} hasEvidence={hasEvidence} hasRca={hasRca} />
            </div>

            {/* ── Tab bar ─────────────────────────────────────────────── */}
            <div style={{
              display: 'flex', gap: 0,
              borderBottom: '2px solid var(--c-border)',
              marginTop: 24, marginBottom: 28,
            }}>
              {([
                { id: 'rca'      as TabId, label: 'RCA & Action' },
                { id: 'evidence' as TabId, label: 'Evidence'      },
                { id: 'history'  as TabId, label: 'History'       },
              ]).map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    padding: '10px 22px', background: 'none', border: 'none',
                    borderBottom: `2px solid ${activeTab === tab.id ? 'var(--c-signal)' : 'transparent'}`,
                    marginBottom: -2,
                    color: activeTab === tab.id ? 'var(--c-text)' : 'var(--c-text-muted)',
                    fontWeight: 500, fontSize: '0.8125rem',
                    cursor: 'pointer',
                    transition: 'color 0.15s',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  {tab.label}
                  {tab.id === 'rca' && approvalStatus === 'pending' && hasRca && (
                    <span className="animate-pulse-glow" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-yellow)', display: 'inline-block', flexShrink: 0 }} />
                  )}
                </button>
              ))}
            </div>

            {/* ── Tab panels ──────────────────────────────────────────── */}
            <div style={{ maxWidth: 960, margin: '0 auto', paddingBottom: approvalStatus === 'pending' && !!data.rca && !isInformational ? 72 : 0 }}>

              {/* TAB 1: RCA & Action */}
              {activeTab === 'rca' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                  <div className="three-am-hide">
                    <BlastRadiusCard requestId={id!} />
                  </div>
                  {data.rca ? (
                    <>
                      <div className="animate-fade-up-2">
                        <RcaSection data={data} requestId={id!} />
                      </div>
                      <div className="animate-fade-up-3 three-am-hide">
                        <TransparencyTrace rca={data.rca} serviceName={data.request?.service_name ?? 'service'} environment={data.request?.environment} />
                      </div>
                    </>
                  ) : (
                    <div style={{
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
                      padding: '40px 20px', textAlign: 'center',
                      background: 'var(--c-surface)', border: '1px solid var(--c-border)',
                      borderRadius: 8,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{
                          width: 10, height: 10, borderRadius: '50%',
                          border: '1.5px solid var(--c-signal)', borderTopColor: 'transparent',
                          display: 'inline-block', animation: 'skeleton-sweep 0.7s linear infinite',
                        }} />
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-signal)', letterSpacing: '0.08em' }}>
                          RCA IN PROGRESS…
                        </span>
                      </div>
                      <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.82rem', color: 'var(--c-text-faint)', lineHeight: 1.6, maxWidth: 380 }}>
                        Corvin is enriching evidence and generating the root cause analysis.
                        This page refreshes automatically.
                      </p>
                    </div>
                  )}
                  <div className="animate-fade-up-4" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                    <ApprovalSection
                      requestId={id!}
                      status={approvalStatus}
                      pendingAction={pendingAction}
                      onClearPendingAction={clearPendingAction}
                      isInformational={isInformational}
                      confidence={
                        data?.rca?.confidence === 'high' ? 85
                        : data?.rca?.confidence === 'medium' ? 55
                        : data?.rca?.confidence === 'low' ? 25
                        : 75
                      }
                    />
                    <ExecutionSection
                      requestId={id!}
                      status={approvalStatus}
                      actions={data?.fix_strategy?.actions?.map(a => ({
                        title: a.title,
                        action_type: a.action_type,
                        target_service: a.target_service,
                        target_namespace: a.target_namespace,
                        risk_level: a.risk_level,
                      })) ?? []}
                    />
                  </div>
                  <CausalChainSection requestId={id!} />
                  <CommsDraftSection requestId={id!} />
                  {/* Feature 8 — Root Cause Debate Mode */}
                  <HypothesisDebatePanel
                    investigationId={id!}
                    onHypothesisSelected={(_hid) => {
                      // When a hypothesis is selected, the fix strategy is re-generated.
                      // Invalidate the investigation query so the RcaSection reflects the new fix.
                      // The query client is not imported here; we rely on the 30s stale time + re-fetch.
                    }}
                  />
                </div>
              )}

              {/* TAB 2: Evidence */}
              {activeTab === 'evidence' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                  {data.request?.description && (
                    <Section title="Context">
                      <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.88rem', color: 'var(--c-text-dim)', lineHeight: 1.75 }}>
                        <TechnicalHighlighter text={data.request.description} />
                      </p>
                    </Section>
                  )}
                  {data.evidence && <EvidenceSection evidence={data.evidence} />}
                  {pastIncidents.length > 0 && <SimilarIncidentsSection incidents={pastIncidents} />}
                  {evidenceReferences.length > 0 && <EvidenceReferencesSection references={evidenceReferences} />}
                </div>
              )}

              {/* TAB 3: History */}
              {activeTab === 'history' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                  <PostMortemSection
                    requestId={id!}
                    isExecuted={approvalStatus === 'executed'}
                    hasRca={hasRca}
                    serviceName={data.request?.service_name ?? 'service'}
                    duration={totalDuration(data.request.created_at, data.completed_at)}
                  />
                  {approvalStatus === 'executed' && (
                    <RunbookUpdatePrompt
                      requestId={id!}
                      serviceName={data.request?.service_name ?? 'unknown'}
                    />
                  )}
                  {approvalStatus === 'executed' && (
                    <RunbookBuilderChat
                      requestId={id!}
                      serviceName={data.request?.service_name ?? 'unknown'}
                      environment={data.request?.environment ?? 'production'}
                    />
                  )}
                  <AuditTrailSection requestId={id!} defaultOpen={true} />
                </div>
              )}

            </div>

            {/* ── Sticky decision bar — only when approval is pending ── */}
            {approvalStatus === 'pending' && !!data.rca && !isInformational && (
              <div style={{
                position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 10000,
                padding: '10px 32px',
                background: 'var(--c-surface)',
                borderTop: '1px solid var(--c-border)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16,
                boxShadow: 'var(--shadow-lg)',
              }}>
                <span className="animate-pulse-glow" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--c-yellow)', display: 'inline-block', flexShrink: 0 }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-yellow)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  Decision Required
                </span>
                <div style={{ width: 1, height: 16, background: 'var(--c-border)', flexShrink: 0 }} />
                <button
                  className="btn-success"
                  onClick={() => { setActiveTab('rca'); setTimeout(() => scrollAndAct('approve'), 60) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                >
                  ✓ Approve
                  <kbd style={{ padding: '1px 5px', borderRadius: 3, background: 'var(--c-surface-3)', border: '1px solid var(--c-border-hi)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontStyle: 'normal', fontWeight: 400 }}>A</kbd>
                </button>
                <button
                  className="btn-danger"
                  onClick={() => { setActiveTab('rca'); setTimeout(() => scrollAndAct('reject'), 60) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                >
                  ✗ Reject
                  <kbd style={{ padding: '1px 5px', borderRadius: 3, background: 'var(--c-surface-3)', border: '1px solid var(--c-border-hi)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontStyle: 'normal', fontWeight: 400 }}>R</kbd>
                </button>
              </div>
            )}
          </>
        )}
      </div>
      <CopilotChatWidget requestId={id!} />
    </Layout>
  )
}
