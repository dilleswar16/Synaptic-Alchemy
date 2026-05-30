import { useQuery } from '@tanstack/react-query'
import { fetchChaosExperiments, type ChaosExperiment, type ChaosExperimentPlan } from '../../api/client'

const TYPE_ICONS: Record<string, string> = {
  'pod-kill': '💀',
  'network-delay': '🌐',
  'resource-exhaust': '📈',
  'dependency-failure': '🔗',
  'dns-failure': '🌍',
}

const BLAST_COLORS: Record<string, { bg: string; text: string }> = {
  limited: { bg: '#dcfce7', text: '#16a34a' },
  moderate: { bg: '#fef3c7', text: '#d97706' },
  wide: { bg: '#fee2e2', text: '#dc2626' },
}

export function ChaosExperimentsSection({ requestId }: { requestId: string }) {
  const { data: plan, isLoading, refetch, isFetched } = useQuery({
    queryKey: ['chaos-experiments', requestId],
    queryFn: () => fetchChaosExperiments(requestId),
    enabled: false,
  })

  return (
    <section style={{ marginTop: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Chaos Experiments</h3>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          style={{
            padding: '0.25rem 0.75rem',
            fontSize: '0.8rem',
            borderRadius: '4px',
            border: '1px solid #ef4444',
            background: isLoading ? '#fee2e2' : '#fff',
            color: '#ef4444',
            cursor: isLoading ? 'wait' : 'pointer',
          }}
        >
          {isLoading ? 'Generating…' : 'Generate Chaos Plan'}
        </button>
      </div>

      {plan && <ChaosExperimentPlanView plan={plan} />}
      {isFetched && !plan && (
        <p style={{ fontSize: '0.8rem', color: '#64748b' }}>No experiments generated.</p>
      )}
    </section>
  )
}

function ChaosExperimentPlanView({ plan }: { plan: ChaosExperimentPlan }) {
  return (
    <div style={{ background: '#fef2f2', borderRadius: '8px', padding: '1rem', border: '1px solid #fecaca' }}>
      <div style={{ marginBottom: '0.75rem', fontSize: '0.8rem', color: '#64748b' }}>
        <strong>{plan.experiment_count}</strong> experiments for <strong>{plan.service_name}</strong>
      </div>
      <p style={{ fontSize: '0.8rem', color: '#475569', marginBottom: '0.75rem' }}>{plan.rationale}</p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {plan.experiments.map((exp) => (
          <ChaosExperimentCard key={exp.id} experiment={exp} />
        ))}
      </div>

      {plan.risk_assessment && (
        <div style={{ marginTop: '0.75rem', padding: '0.5rem', background: '#fff', borderRadius: '4px', border: '1px solid #fecaca' }}>
          <strong style={{ fontSize: '0.75rem', color: '#dc2626' }}>Risk Assessment:</strong>
          <p style={{ fontSize: '0.8rem', margin: '0.25rem 0 0', color: '#475569' }}>{plan.risk_assessment}</p>
        </div>
      )}
    </div>
  )
}

function ChaosExperimentCard({ experiment: exp }: { experiment: ChaosExperiment }) {
  const blastStyle = BLAST_COLORS[exp.blast_radius] ?? BLAST_COLORS.limited

  return (
    <div style={{ background: '#fff', borderRadius: '6px', padding: '0.75rem', border: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '1.1rem' }}>{TYPE_ICONS[exp.experiment_type] ?? '⚡'}</span>
        <strong style={{ fontSize: '0.85rem' }}>{exp.name}</strong>
        <span style={{
          fontSize: '0.65rem',
          padding: '0.1rem 0.4rem',
          borderRadius: '3px',
          background: blastStyle.bg,
          color: blastStyle.text,
          fontWeight: 600,
        }}>
          {exp.blast_radius}
        </span>
        <span style={{ fontSize: '0.7rem', color: '#64748b', marginLeft: 'auto' }}>
          {exp.duration_seconds}s
        </span>
      </div>

      <p style={{ fontSize: '0.8rem', color: '#475569', margin: '0 0 0.4rem' }}>{exp.hypothesis}</p>

      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
        <span>Target: <strong>{exp.target_service}</strong></span>
        {exp.prerequisites.length > 0 && (
          <span style={{ marginLeft: '1rem' }}>
            Prerequisites: {exp.prerequisites.join(', ')}
          </span>
        )}
      </div>
    </div>
  )
}
