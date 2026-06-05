import { Section } from '../Section'
import { TechnicalHighlighter } from '../TechnicalHighlighter'

interface EvidenceReferencesSectionProps {
  references: string[]
}

function getSourceBadge(text: string) {
  const t = text.toLowerCase()
  if (t.includes('elastic')) return { label: 'ELASTIC', color: '#00bfb3' }
  if (t.includes('apim') || t.includes('api management')) return { label: 'APIM', color: '#0078d4' }
  if (t.includes('aks') || t.includes('pod ') || t.includes('container ')) return { label: 'AKS', color: '#326ce5' }
  if (t.includes('azure') || t.includes('activity')) return { label: 'AZURE', color: '#0078d4' }
  return { label: 'SYSTEM', color: 'var(--c-text-muted)' }
}

export function EvidenceReferencesSection({ references }: EvidenceReferencesSectionProps) {
  if (!references || references.length === 0) return null

  return (
    <Section title="Evidence References" info="The specific telemetry data points that directly informed the root cause conclusion. Corvin cites its sources so engineers can verify which evidence drove each inference.">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {references.map((ref: string, i: number) => {
          const badge = getSourceBadge(ref)
          return (
            <div key={i} style={{
              display: 'flex', flexDirection: 'column', gap: 6,
              padding: '12px 16px',
              background: 'var(--c-surface-2)',
              border: '1px solid var(--c-border-hi)',
              borderRadius: 6,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  fontWeight: 600, fontSize: '0.75rem',
                  letterSpacing: '0.02em',
                  padding: '2px 6px', borderRadius: 4,
                  background: `color-mix(in srgb, ${badge.color} 15%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${badge.color} 30%, transparent)`,
                  color: badge.color,
                }}>
                  {badge.label}
                </span>
              </div>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
                color: 'var(--c-text-dim)', lineHeight: 1.7,
              }}>
                <TechnicalHighlighter text={ref} />
              </div>
            </div>
          )
        })}
      </div>
    </Section>
  )
}
