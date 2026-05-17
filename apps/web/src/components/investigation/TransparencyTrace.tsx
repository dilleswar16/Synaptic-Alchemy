import MermaidChart from '../common/MermaidChart'
import { Section } from '../Section'

interface TransparencyTraceProps {
  rca: any
  serviceName: string
}

export function TransparencyTrace({ rca, serviceName }: TransparencyTraceProps) {
  if (!rca) return null

  // Build a simple trace diagram from RCA data
  const factors = rca.contributing_factors || []
  const summary = rca.summary || 'No summary available'
  
  // Safe escaping and string conversion for Mermaid labels
  const esc = (val: any) => {
    const str = String(val || '')
    return str.replace(/"/g, "'").replace(/\n/g, '<br/>').replace(/[\[\](){}]/g, '')
  }

  let chart = 'graph TD\n'
  chart += `  Trigger["Trigger: ${esc(serviceName)} Alert"] --> RCA["AI Analysis"]\n`
  
  factors.forEach((f: string, i: number) => {
    const label = f.length > 40 ? f.slice(0, 40) + '...' : f
    chart += `  RCA --> Factor${i}["${esc(label)}"]\n`
  })

  chart += `  RCA --> Result["${esc(summary.slice(0, 50))}..."]\n`
  
  // Style
  chart += '  classDef default fill:rgba(255,255,255,0.05),stroke:rgba(255,255,255,0.2),color:#fff,font-size:10px\n'
  chart += '  classDef trigger fill:rgba(239,68,68,0.1),stroke:#ef4444,color:#ef4444\n'
  chart += '  classDef rca fill:rgba(249,115,22,0.1),stroke:#f97316,color:#f97316\n'
  chart += '  class Trigger trigger\n'
  chart += '  class RCA rca\n'

  return (
    <div className="animate-fade-up-3">
      <Section title="Investigation Trace">
        <div style={{ marginBottom: 10, fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
          How Corvin connected the dots across your platform telemetry.
        </div>
        <MermaidChart chart={chart} background="transparent" />
      </Section>
    </div>
  )
}
