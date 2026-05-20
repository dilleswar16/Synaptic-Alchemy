export const HTTP_CODES = new Set(['200', '201', '400', '401', '403', '404', '500', '502', '503', '504'])
export const HTTP_METHODS = new Set(['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
export const KEYWORDS = new Set(['OTLP', 'JWT', 'APIM', 'Envoy', 'CrashLoopBackOff', 'OOMKilled', 'Running', 'Failed', 'Pending'])

export function TechnicalHighlighter({ text }: { text: string }) {
  if (typeof text !== 'string') return <>{text}</>
  
  const tokens = text.split(/(\b(?:200|201|400|401|403|404|500|502|503|504)\b|\b(?:GET|POST|PUT|DELETE|PATCH)\b|\b[a-z0-9]+(?:-[a-z0-9]+){2,}\b|\b(?:OTLP|JWT|APIM|Envoy|CrashLoopBackOff|OOMKilled|Running|Failed|Pending)\b)/g)

  return (
    <>
      {tokens.map((token, i) => {
        if (HTTP_CODES.has(token)) {
          const color = token.startsWith('5') || token.startsWith('4') ? 'var(--c-red)' : 'var(--c-green)'
          const bg = token.startsWith('5') || token.startsWith('4') ? 'var(--c-red-bg)' : 'var(--c-green-bg)'
          return <span key={i} style={{ color, fontWeight: 700, background: bg, padding: '1px 5px', borderRadius: 3, border: `1px solid ${color}40` }}>{token}</span>
        }
        if (HTTP_METHODS.has(token)) {
          return <span key={i} style={{ color: 'var(--c-signal)', fontWeight: 700, background: 'var(--c-signal-glow)', padding: '1px 5px', borderRadius: 4 }}>{token}</span>
        }
        if (KEYWORDS.has(token)) {
          const isBad = token === 'Failed' || token === 'CrashLoopBackOff' || token === 'OOMKilled'
          const isGood = token === 'Running'
          let color = 'var(--c-text)'
          if (isBad) color = 'var(--c-red)'
          if (isGood) color = 'var(--c-green)'
          return <span key={i} style={{ color, fontWeight: 700 }}>{token}</span>
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
