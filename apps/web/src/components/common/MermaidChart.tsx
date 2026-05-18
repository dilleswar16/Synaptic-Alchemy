import { useState, useEffect, useId } from 'react'
import mermaid from 'mermaid'

// Inject global CSS once to fix Mermaid SVG text clipping and overflow in dark mode
if (typeof document !== 'undefined' && !document.getElementById('corvin-mermaid-css')) {
  const s = document.createElement('style')
  s.id = 'corvin-mermaid-css'
  s.textContent = `
    .corvin-mermaid svg { max-width: 100%; height: auto; overflow: visible; }
    .corvin-mermaid svg .node rect,
    .corvin-mermaid svg .node circle,
    .corvin-mermaid svg .node ellipse,
    .corvin-mermaid svg .node polygon { overflow: visible; }
    .corvin-mermaid svg text { font-family: 'JetBrains Mono', 'Fira Mono', monospace; }
    .corvin-mermaid svg .edgeLabel { font-size: 11px; }
    .corvin-mermaid svg .cluster rect { rx: 8; ry: 8; }
  `
  document.head.appendChild(s)
}

// Corvin Mermaid theme: neutral-dark nodes (legible at any scale) + brand orange on edges only.
// Philosophy: diagrams are engineering artifacts inside the UI, not UI chrome.
// Neutral slate nodes = text always readable. Orange edges = brand presence without noise.
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  securityLevel: 'loose',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    nodeSpacing: 55,
    rankSpacing: 65,
    padding: 14,
  },
  themeVariables: {
    // ── Surfaces (neutral slate — not branded) ──
    background:           '#0d1117',
    mainBkg:              '#161b22',
    secondBkg:            '#1c2333',
    tertiaryBkg:          '#1c2333',
    // ── Borders (subtle, not orange) ──
    nodeBorder:           '#30363d',
    clusterBkg:           'rgba(22,27,34,0.7)',
    clusterBorder:        '#30363d',
    // ── Text (always legible on slate) ──
    nodeTextColor:        '#e6edf3',
    edgeLabelBackground:  '#0d1117',
    labelTextColor:       '#8b949e',
    titleColor:           '#e6edf3',
    // ── Edges: brand orange — the ONE orange touch ──
    lineColor:            '#f97316',
    // ── Node variants (all neutral, different depths) ──
    primaryColor:         '#1c2333',
    primaryBorderColor:   '#30363d',
    primaryTextColor:     '#e6edf3',
    secondaryColor:       '#161b22',
    secondaryBorderColor: '#30363d',
    secondaryTextColor:   '#e6edf3',
    tertiaryColor:        '#21262d',
    tertiaryBorderColor:  '#30363d',
    tertiaryTextColor:    '#e6edf3',
    // ── Misc ──
    labelBoxBkgColor:     '#161b22',
    labelBoxBorderColor:  '#30363d',
    fontFamily:           'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize:             '12px',
  },
})

interface MermaidChartProps {
  chart: string
  background?: string
}

/**
 * Bulletproof Mermaid v11 component for React.
 * Handles high-frequency updates during AI streaming.
 */
export function MermaidChart({ chart, background }: MermaidChartProps) {
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [isRendering, setIsRendering] = useState(false)
  const uniqueId = useId().replace(/:/g, '') // IDs can't contain colons for Mermaid

  useEffect(() => {
    let isMounted = true
    const cleanChart = chart.trim()
    
    if (cleanChart.length < 10) return

    const renderDiagram = async () => {
      setIsRendering(true)
      try {
        // Pre-process common LLM errors:
        // 1. Replace literal \n with <br/> inside quoted strings or labels
        let processedChart = cleanChart.replace(/\\n/g, '<br/>')

        // 2. Mermaid 11 does not support rgba() in classDef — replace with hex equivalents
        processedChart = processedChart.replace(
          /\bclassDef\b([^\n]*)/g,
          (_line: string, rest: string) => {
            const fixed = rest.replace(/rgba?\([^)]+\)/g, (rgba: string) => {
              // Extract r,g,b from rgba/rgb and convert to hex
              const m = rgba.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/)
              if (!m) return '#374151'
              const r = parseInt(m[1]).toString(16).padStart(2, '0')
              const g = parseInt(m[2]).toString(16).padStart(2, '0')
              const b = parseInt(m[3]).toString(16).padStart(2, '0')
              return `#${r}${g}${b}`
            })
            return `classDef${fixed}`
          }
        )

        // v11 render is async and requires a unique ID per call to avoid cache collisions
        const renderId = `mermaid-${uniqueId}-${Math.random().toString(36).slice(2, 6)}`
        
        const { svg: html } = await mermaid.render(renderId, processedChart)
        
        if (isMounted) {
          setSvg(html)
          setError(null)
        }
      } catch (err: any) {
        // If it's a syntax error (expected during streaming), we just wait.
        // If it's been a while and still failing, we record it.
        if (isMounted && cleanChart.length > 100) {
          // Only show error for long, presumably "finished" diagrams
          setError(err.message || 'Invalid diagram syntax')
        }
      } finally {
        if (isMounted) setIsRendering(false)
      }
    }

    // Debounce the render to handle fast streaming tokens
    const timeout = setTimeout(renderDiagram, 150)
    
    return () => {
      isMounted = false
      clearTimeout(timeout)
    }
  }, [chart, uniqueId])

  // If we have a valid SVG, show it (even if we are currently re-rendering)
  if (svg) {
    return (
      <div style={{ position: 'relative', margin: '16px 0', width: '100%' }}>
        {/* Label above diagram */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <div style={{ flex: 1, height: 1, background: 'rgba(249,115,22,0.12)' }} />
          <span style={{ fontFamily: 'monospace', fontSize: '0.65rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(249,115,22,0.45)' }}>diagram</span>
          <div style={{ flex: 1, height: 1, background: 'rgba(249,115,22,0.12)' }} />
        </div>
        <div
          className="corvin-mermaid"
          dangerouslySetInnerHTML={{ __html: svg }}
          style={{
            display: 'flex',
            justifyContent: 'center',
            background: background ?? 'linear-gradient(160deg, #0d0f17 0%, #111420 100%)',
            padding: '20px 16px',
            borderRadius: 10,
            border: '1px solid rgba(249,115,22,0.12)',
            boxShadow: 'inset 0 0 60px rgba(0,0,0,0.3), 0 4px 24px rgba(0,0,0,0.3)',
            overflowX: 'auto',
            transition: 'opacity 0.2s',
            opacity: isRendering ? 0.75 : 1
          }} 
        />
        {isRendering && (
           <div style={{
             position: 'absolute', top: 12, right: 12,
             display: 'flex', alignItems: 'center', gap: 6,
             background: 'rgba(0,0,0,0.5)', padding: '4px 10px', borderRadius: 6,
             fontSize: '0.65rem', color: 'var(--c-signal)', fontFamily: 'var(--font-mono)',
             backdropFilter: 'blur(4px)', border: '1px solid rgba(249,115,22,0.2)'
           }}>
             <div style={{ width: 8, height: 8, borderRadius: '50%', border: '1px solid currentColor', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
             SYNCING
           </div>
        )}
      </div>
    )
  }

  // Fallback: If it's a long block and failing to render, show the raw code
  if (error && chart.length > 50) {
    return (
      <div style={{ margin: '16px 0' }}>
        <pre style={{ 
          margin: 0, padding: '16px', background: 'rgba(239,68,68,0.05)', 
          border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8,
          fontSize: '0.75rem', color: 'var(--c-text-dim)', overflowX: 'auto'
        }}>
          {chart}
        </pre>
        <div style={{ fontSize: '0.65rem', color: 'var(--c-red)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
          ⚠ {error}
        </div>
      </div>
    )
  }

  // Initial loading state
  return (
    <div style={{ 
      margin: '16px 0', 
      padding: '40px 20px', 
      borderRadius: 12, 
      border: '1px solid var(--c-border)', 
      background: 'rgba(249,115,22,0.03)',
      textAlign: 'center',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 16
    }}>
      <div className="animate-pulse-glow" style={{ 
        width: 32, height: 32, borderRadius: '50%', 
        border: '2px solid var(--c-signal)', borderTopColor: 'transparent', 
        animation: 'spin 0.8s linear infinite' 
      }} />
      <div style={{ 
        color: 'var(--c-text-faint)', 
        fontSize: '0.7rem', 
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.1em',
        textTransform: 'uppercase'
      }}>
        Constructing Visual Map...
      </div>
    </div>
  )
}

export default MermaidChart



