import MermaidChart from '../common/MermaidChart'

interface FixAction {
  title: string
  risk_level: string
  estimated_impact?: string
}

interface FixStrategyFlowchartProps {
  serviceName: string
  actions: FixAction[]
  rcaConfidence?: string
}

const RISK_LABEL: Record<string, string> = { low: 'LOW', medium: 'MEDIUM', high: 'HIGH' }

/** Word-wrap into Mermaid newline-joined lines (htmlLabels:false uses \n not <br/>) */
function wrapText(text: string, maxLen = 38): string {
  if (text.length <= maxLen) return text
  const words = text.split(' ')
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w
    if (next.length > maxLen) { if (cur) lines.push(cur); cur = w } else cur = next
  }
  if (cur) lines.push(cur)
  return lines.join('\n')
}

/** Escape special Mermaid chars, then wrap */
function safeLabel(raw: string, maxWrap = 38): string {
  const safe = String(raw || '')
    .replace(/"/g, "'")
    .replace(/[\[\]{}]/g, '')
    .replace(/\n/g, ' ')
    .trim()
  return wrapText(safe, maxWrap)
}

/** Extract key clause from a long string (up to first comma or maxChars) */
function digest(raw: string, maxChars = 52): string {
  const t = String(raw || '').trim()
  const ci = t.search(/,/)
  const clause = (ci > 20 && ci <= 72) ? t.slice(0, ci) : t.slice(0, maxChars)
  return safeLabel(clause.trim())
}

export function FixStrategyFlowchart({ serviceName, actions, rcaConfidence }: FixStrategyFlowchartProps) {
  if (!actions || actions.length === 0) return null

  const confSuffix = rcaConfidence ? ` · ${rcaConfidence} confidence` : ''
  const svcLabel = safeLabel(serviceName, 22)

  let chart = 'graph TD\n'
  chart += `  Start["⚠ ${svcLabel}<br/>RCA Confirmed${confSuffix}"] --> A0\n`

  actions.forEach((action, i) => {
    const risk = action.risk_level.toLowerCase()
    const riskTag = RISK_LABEL[risk] ?? risk.toUpperCase()
    const titleLabel = digest(action.title, 50)
    const nextId = i < actions.length - 1 ? `A${i + 1}` : 'Gate'
    chart += `  A${i}["${i + 1}. ${titleLabel}<br/>${riskTag} RISK"] --> ${nextId}\n`
  })

  chart += `  Gate[["Human Approval Required<br/>${actions.length} action${actions.length > 1 ? 's' : ''} need SRE sign-off"]]\n`

  return (
    <div style={{ marginTop: 24, marginBottom: 24 }}>
      <div style={{
        fontSize: '0.8125rem', fontWeight: 600,
        letterSpacing: '0.02em',
        color: 'var(--c-text-muted)', marginBottom: 12,
      }}>
        Fix Execution Plan
      </div>
      <div style={{ borderRadius: 8, border: '1px solid var(--c-border)' }}>
        <MermaidChart chart={chart} />
      </div>
    </div>
  )
}
