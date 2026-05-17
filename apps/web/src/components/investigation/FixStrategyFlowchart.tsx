import React from 'react'
import MermaidChart from '../common/MermaidChart'

interface FixStrategyFlowchartProps {
  serviceName: string
  actions: Array<{ title: string; risk_level: string }>
}

export function FixStrategyFlowchart({ serviceName, actions }: FixStrategyFlowchartProps) {
  if (!actions || actions.length === 0) return null

  // Safe escaping for Mermaid labels
  const esc = (str: string) => str.replace(/"/g, "'").replace(/\n/g, '<br/>')

  let chart = 'graph TD\n'
  chart += `  Start(["Trigger: ${esc(serviceName)} Alert"]) --> Analysis{"Analyze Evidence"}\n`
  chart += `  Analysis --> Detect{"Root Cause Detected"}\n`
  
  actions.forEach((action, i) => {
    const risk = action.risk_level.toLowerCase()
    const style = risk === 'high' ? 'critical' : risk === 'medium' ? 'warn' : 'safe'
    const nodeId = `Action${i}`
    chart += `  Detect --> ${nodeId}["${esc(action.title)}"]:::${style}\n`
  })
  
  chart += '  Detect --> Manual["Manual SRE Review"]:::warn\n'
  
  // Styles
  chart += '  classDef critical fill:rgba(239,68,68,0.1),stroke:#ef4444,color:#ef4444,stroke-width:2px\n'
  chart += '  classDef warn fill:rgba(249,115,22,0.1),stroke:#f97316,color:#f97316\n'
  chart += '  classDef safe fill:rgba(34,197,94,0.1),stroke:#22c55e,color:#22c55e\n'
  chart += '  classDef default fill:rgba(255,255,255,0.05),stroke:rgba(255,255,255,0.2),color:#fff\n'

  return (
    <div style={{ marginTop: 24, marginBottom: 24 }}>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: '0.6rem', fontWeight: 700,
        letterSpacing: '0.14em', textTransform: 'uppercase',
        color: 'var(--c-text-muted)', marginBottom: 12,
      }}>
        Fix Decision Tree
      </div>
      <div style={{ background: 'rgba(0,0,0,0.15)', borderRadius: 8, border: '1px solid var(--c-border)' }}>
        <MermaidChart chart={chart} background="transparent" />
      </div>
    </div>
  )
}
