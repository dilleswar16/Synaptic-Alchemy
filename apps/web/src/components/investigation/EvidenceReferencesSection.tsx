import { Section } from '../Section'

interface EvidenceReferencesSectionProps {
  references: string[]
}

const HTTP_CODES = new Set(['200', '201', '400', '401', '403', '404', '500', '502', '503', '504'])
const HTTP_METHODS = new Set(['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
const KEYWORDS = new Set(['OTLP', 'JWT', 'APIM', 'Envoy', 'CrashLoopBackOff', 'OOMKilled'])

function TechnicalHighlighter({ text }: { text: string }) {
  const tokens = text.split(/(\b(?:200|201|400|401|403|404|500|502|503|504)\b|\b(?:GET|POST|PUT|DELETE|PATCH)\b|\b[a-z0-9]+(?:-[a-z0-9]+){2,}\b|\b(?:OTLP|JWT|APIM|Envoy|CrashLoopBackOff|OOMKilled)\b)/g)

  return (
    <>
      {tokens.map((token, i) => {
        if (HTTP_CODES.has(token)) {
          const color = token.startsWith('5') || token.startsWith('4') ? 'var(--c-red)' : 'var(--c-green)'
          const bg = token.startsWith('5') || token.startsWith('4') ? 'var(--c-red-bg)' : 'var(--c-green-bg)'
          return <span key={i} style={{ color, fontWeight: 700, background: bg, padding: '1px 5px', borderRadius: 3, border: `1px solid ${color}40` }}>{token}</span>
        }
        if (HTTP_METHODS.has(token)) {
          return <span key={i} style={{ color: 'var(--c-signal)', fontWeight: 700, background: 'rgba(249,115,22,0.1)', padding: '1px 5px', borderRadius: 3 }}>{token}</span>
        }
        if (KEYWORDS.has(token)) {
          return <span key={i} style={{ color: 'var(--c-text)', fontWeight: 700 }}>{token}</span>
        }
        if (/^[a-z0-9]+(?:-[a-z0-9]+){2,}$/.test(token)) {
          // pod name or correlation id
          return <span key={i} style={{ color: 'var(--c-text)', background: 'var(--c-surface-3)', padding: '1px 4px', borderRadius: 3, border: '1px solid var(--c-border)' }}>{token}</span>
        }
        return <span key={i}>{token}</span>
      })}
    </>
  )
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
    <Section title="Evidence References">
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
                  fontFamily: 'var(--font-display)', fontSize: '0.55rem', fontWeight: 800,
                  letterSpacing: '0.12em', textTransform: 'uppercase',
                  padding: '2px 6px', borderRadius: 2,
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
