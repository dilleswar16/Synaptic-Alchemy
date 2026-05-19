import MermaidChart from '../common/MermaidChart'
import { Section } from '../Section'

interface TransparencyTraceProps {
  rca: any
  serviceName: string
  environment?: string
}

/** Word-wrap into Mermaid newline-joined lines (htmlLabels:false uses \n not <br/>) */
function wrapText(text: string, maxLen = 34): string {
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
function safeLabel(raw: string, maxWrap = 34): string {
  const safe = String(raw || '')
    .replace(/"/g, "'")
    .replace(/[\[\]{}]/g, '')
    .replace(/\n/g, ' ')
    .trim()
  return wrapText(safe, maxWrap)
}

/** Extract the key clause from a long factor sentence (up to first comma or maxChars) */
function digest(raw: string, maxChars = 52): string {
  const t = String(raw || '').trim()
  const ci = t.search(/,/)
  const clause = (ci > 20 && ci <= 72) ? t.slice(0, ci) : t.slice(0, maxChars)
  return safeLabel(clause.trim())
}

/** Derive evidence source type from a reference string */
function refToSource(ref: string): string | null {
  const r = ref.toLowerCase()
  if (r.startsWith('aks')) return 'AKS'
  if (r.startsWith('elastic')) return 'Elastic'
  if (r.includes('log_analytics') || r.includes('log analytics')) return 'Log Analytics'
  if (r.includes('apim')) return 'APIM'
  if (r.includes('azure_activity')) return 'Azure Activity'
  return null
}

/** Pick the best matching source node ID for a factor string */
function bestSrcId(factorText: string, srcMap: Record<string, string>): string {
  const t = factorText.toLowerCase()
  if (srcMap['AKS'] && /\b(pod|deployment|replica|restart|container|namespace)\b/.test(t)) return srcMap['AKS']
  if (srcMap['APIM'] && /\b(apim|jwt|gateway|validate.jwt|401|403)\b/.test(t)) return srcMap['APIM']
  if (srcMap['Elastic'] && /\b(elastic|otlp|trace|metric|exporter|okhttp|log|health)\b/.test(t)) return srcMap['Elastic']
  if (srcMap['Log Analytics'] && /\b(workspace|gateway|apim|log analytics)\b/.test(t)) return srcMap['Log Analytics']
  if (srcMap['Azure Activity'] && /\b(activity|change|deploy)\b/.test(t)) return srcMap['Azure Activity']
  return Object.values(srcMap)[0] || 'Gather'
}

export function TransparencyTrace({ rca, serviceName, environment }: TransparencyTraceProps) {
  if (!rca) return null

  const factors: string[] = (rca.contributing_factors || []).slice(0, 4)
  const refs: string[] = rca.evidence_references || []

  // Collect unique evidence sources in order of appearance
  const seen = new Set<string>()
  const sources: string[] = []
  for (const ref of refs) {
    const s = refToSource(ref)
    if (s && !seen.has(s)) { seen.add(s); sources.push(s) }
  }
  if (sources.length === 0) sources.push('AKS')
  const topSources = sources.slice(0, 3)

  // node ID map: source name → Mermaid ID
  const srcMap: Record<string, string> = {}
  topSources.forEach((s, i) => { srcMap[s] = `Src${i}` })

  const envSuffix = environment ? ` · ${environment}` : ''
  const confLabel = rca.confidence ? ` · ${rca.confidence} confidence` : ''

  let chart = 'graph LR\n'

  // Layer 1: Alert → Gather
  chart += `  Alert["⚠ ${safeLabel(serviceName, 20)}${envSuffix}<br/>Alert Triggered"] --> Gather["${topSources.length} Evidence Source${topSources.length > 1 ? 's' : ''}<br/>Queried${confLabel}"]\n`

  // Layer 2: Gather → Source nodes
  topSources.forEach((s, i) => {
    chart += `  Gather --> Src${i}["${s}"]\n`
  })

  // Layer 3: Source → Factor nodes (each factor wired to best matching source)
  factors.forEach((f, i) => {
    const srcId = bestSrcId(f, srcMap)
    chart += `  ${srcId} --> Fac${i}["${digest(f)}"]\n`
  })

  // Layer 4: All factors converge on Root Cause
  const rcLabel = digest(rca.root_cause || 'Root cause identified', 55)
  factors.forEach((_, i) => {
    chart += `  Fac${i} --> RC\n`
  })
  chart += `  RC["Root Cause:<br/>${rcLabel}"]\n`

  return (
    <div className="animate-fade-up-3">
      <Section title="Investigation Trace">
        <div style={{ marginBottom: 10, fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
          How Corvin traced evidence across {topSources.join(', ')} to reach this conclusion.
        </div>
        <MermaidChart chart={chart} background="transparent" />
      </Section>
    </div>
  )
}
