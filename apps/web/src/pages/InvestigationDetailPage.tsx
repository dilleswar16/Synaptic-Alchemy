import { useEffect } from 'react'
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
import { IncidentHeroCard } from '../components/investigation/IncidentHeroCard'
import { RunbookUpdatePrompt } from '../components/investigation/RunbookUpdatePrompt'
import { TechnicalHighlighter } from '../components/TechnicalHighlighter'
import { Section } from '../components/Section'
import { BlastRadiusCard } from '../components/BlastRadiusCard'
import { SlaCountdownCard } from '../components/investigation/SlaCountdownCard'
import {
  fetchInvestigation,
  fetchSimilarIncidents,
  fetchReplay,
  type SimilarIncident,
  type ReplayPayload,
} from '../api/client'
import { totalDuration } from '../utils/time'

export default function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()

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
    setSearchParams({ action })
    setTimeout(() => {
      document.getElementById('approval-section')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
  }

  const pendingAndRcaReady = approvalStatus === 'pending' && !!data?.rca && pendingAction === null

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
                fontFamily: 'var(--font-display)', fontSize: '0.7rem', fontWeight: 700,
                letterSpacing: '0.1em', textTransform: 'uppercase',
                color: 'var(--c-text-muted)', textDecoration: 'none',
              }}
            >
              ← Investigations
            </Link>
            {data && (
              <Link
                to={`/investigations?service=${encodeURIComponent(data.request.service_name)}&env=${encodeURIComponent(data.request.environment)}`}
                style={{
                  fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.62rem',
                  letterSpacing: '0.1em', textTransform: 'uppercase',
                  color: 'var(--c-text-faint)', textDecoration: 'none',
                  padding: '4px 10px', borderRadius: 2,
                  border: '1px solid var(--c-border)',
                  background: 'var(--c-surface-2)',
                }}
              >
                All {data.request.service_name.toUpperCase()} →
              </Link>
            )}
          </div>

          <div style={{ marginTop: 14 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: '0.62rem', fontWeight: 700,
              letterSpacing: '0.18em', textTransform: 'uppercase',
              color: 'var(--c-signal)', marginBottom: 6,
            }}>
              Investigation
            </div>
            <h1 style={{
              margin: '0 0 16px',
              fontFamily: 'var(--font-display)', fontWeight: 900,
              fontSize: '2.6rem', letterSpacing: '0.05em',
              color: 'var(--c-text)', lineHeight: 1,
              background: 'linear-gradient(135deg, var(--c-signal) 0%, var(--c-text) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}>
              {data?.request?.service_name?.toUpperCase() ?? (isLoading ? '…' : 'INVESTIGATION')}
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {data?.request?.environment && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  padding: '3px 10px', borderRadius: 2,
                  background: 'rgba(249,115,22,0.08)',
                  border: '1px solid rgba(249,115,22,0.2)',
                  color: 'var(--c-signal)', letterSpacing: '0.04em',
                }}>
                  {data.request.environment}
                </span>
              )}
              {data?.request?.trigger_source && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  padding: '3px 10px', borderRadius: 2,
                  background: 'var(--c-surface-2)',
                  border: '1px solid var(--c-border-hi)',
                  color: 'var(--c-text-dim)', letterSpacing: '0.04em',
                }}>
                  {data.request.trigger_source.replace(/_/g, ' ')}
                </span>
              )}
              {data && <StatusBadge status={approvalStatus} />}
              {data?.request?.id && <CopyableId requestId={data.request.id} />}
              {rcaDuration && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
                  padding: '2px 8px', borderRadius: 2,
                  background: 'rgba(34,197,94,0.08)',
                  border: '1px solid rgba(34,197,94,0.2)',
                  color: 'var(--c-green)', letterSpacing: '0.03em',
                }}>
                  ⏱ RCA in {rcaDuration}
                </span>
              )}
            </div>
          </div>
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
                  background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.02) 50%, transparent 100%)',
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
            <IncidentHeroCard data={data} approvalStatus={approvalStatus} />
            <SlaCountdownCard requestId={id!} status={approvalStatus} />
            <BlastRadiusCard requestId={id!} />
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'minmax(320px, 420px) 1fr', 
              gap: 32, 
              alignItems: 'start' 
            }}>
            {/* Left Column: Context, Evidence, Incidents, Audit Trail */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              {data.request?.description && (
                <div className="animate-fade-up-1">
                  <Section title="Context">
                    <p style={{
                      margin: 0, fontFamily: 'var(--font-body)', fontSize: '0.88rem',
                      color: 'var(--c-text-dim)', lineHeight: 1.75,
                    }}>
                      <TechnicalHighlighter text={data.request.description} />
                    </p>
                  </Section>
                </div>
              )}

              {data.evidence && (
                <div className="animate-fade-up-2">
                  <EvidenceSection evidence={data.evidence} />
                </div>
              )}

              {pastIncidents.length > 0 && (
                <div className="animate-fade-up-3">
                  <SimilarIncidentsSection incidents={pastIncidents} />
                </div>
              )}

              {evidenceReferences.length > 0 && (
                <div className="animate-fade-up-4">
                  <EvidenceReferencesSection references={evidenceReferences} />
                </div>
              )}

              <div className="animate-fade-up-5">
                <AuditTrailSection requestId={id!} defaultOpen={approvalStatus === 'executed'} />
              </div>
            </div>

            {/* Right Column: Stepper, RCA, Approval, Fix Strategy */}
            <div style={{ 
              display: 'flex', 
              flexDirection: 'column', 
              gap: 24,
              position: 'sticky',
              top: 24,
              maxHeight: 'calc(100vh - 48px)',
              overflowY: 'auto',
              paddingRight: 8, // room for inner scrollbar
              paddingBottom: 40,
            }}>
              <WorkflowStepper approvalStatus={approvalStatus} hasEvidence={hasEvidence} hasRca={hasRca} />

              {data.rca && (
                <div className="animate-fade-up-4">
                  <RcaSection data={data} requestId={id!} />
                </div>
              )}

              <div className="animate-fade-up-5" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                <ApprovalSection
                  requestId={id!}
                  status={approvalStatus}
                  pendingAction={pendingAction}
                  onClearPendingAction={clearPendingAction}
                />
                <ExecutionSection requestId={id!} status={approvalStatus} />
                <PostMortemSection requestId={id!} isExecuted={approvalStatus === 'executed'} />
                {approvalStatus === 'executed' && (
                  <RunbookUpdatePrompt
                    requestId={id!}
                    serviceName={data.request?.service_name ?? 'unknown'}
                  />
                )}
              </div>
            </div>
            </div>
          </>
        )}
      </div>
    </Layout>
  )
}
