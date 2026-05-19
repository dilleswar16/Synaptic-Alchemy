import { useState, useEffect, useId } from 'react'
import mermaid from 'mermaid'

// Inject global CSS. Force-replace on HMR reloads so changes take effect immediately.
// SVG spec: CSS properties always beat SVG presentation attributes (fill="...").
// So one blanket rect rule is sufficient — no class-name guessing needed.
if (typeof document !== 'undefined') {
  const existing = document.getElementById('corvin-mermaid-css')
  const css = `
    .corvin-mermaid svg { max-width: 100%; height: auto; overflow: visible; }

    /* ALL rects → white. Covers node boxes, edge label pills, everything.
       Specificity: (0,1,2). Beats any SVG fill attribute. */
    .corvin-mermaid svg rect {
      fill: #ffffff;
      stroke: #94a3b8;
    }

    /* Cluster/subgraph rects → dark navy. Specificity (0,2,1) beats rule above. */
    .corvin-mermaid svg .cluster rect {
      fill: #131c2e;
      stroke: #475569;
    }

    /* Edge label pills — subtle orange tint to tie them to their arrow */
    .corvin-mermaid svg .edgeLabel rect {
      fill: #1c1a14;
      stroke: rgba(249,115,22,0.3);
    }

    /* ALL text → dark (#1e293b). White rects everywhere means dark text everywhere. */
    .corvin-mermaid svg text {
      fill: #1e293b;
      font-family: 'JetBrains Mono', 'Fira Mono', monospace;
    }

    /* Cluster title text → light (cluster bg is dark). Specificity (0,2,1). */
    .corvin-mermaid svg .cluster text {
      fill: #94a3b8;
    }
  `
  if (existing) {
    existing.textContent = css
  } else {
    const s = document.createElement('style')
    s.id = 'corvin-mermaid-css'
    s.textContent = css
    document.head.appendChild(s)
  }
}

/**
 * Patch Mermaid SVG string: strip gradient defs and replace url() fill refs.
 * With htmlLabels:false there is no foreignObject, so no CSS gradient pattern issue.
 */
function sanitizeSvg(raw: string): string {
  let out = raw
    // Remove gradient/pattern defs
    .replace(/<linearGradient[\s\S]*?<\/linearGradient>/g, '')
    .replace(/<pattern[\s\S]*?<\/pattern>/g, '')
    // Replace url() fill refs on rects with white (node boxes)
    .replace(/(<rect(?:[^>]*?))fill="url\([^)]*\)"([^>]*?>)/g, '$1fill="#ffffff"$2')
    .replace(/fill="url\([^)]*\)"/g, 'fill="#ffffff"')
    // Stamp node text fill as dark so it wins over the global light default
    // Works by targeting text elements that are siblings of rects with white fill
    // Mermaid sets fill as a presentation attribute; CSS overrides it, so this is belt-and-suspenders
    .replace(/(<text[^>]*class="[^"]*(?:nodeLabel|label)[^"]*"[^>]*)>/g,
      (_m, prefix) => prefix.includes('fill=') ? `${prefix}>` : `${prefix} fill="#1e293b">`)
  return out
}

// htmlLabels: false — pure SVG <text>/<tspan> rendering.
// Eliminates <foreignObject> and its HTML/CSS gradient background entirely.
// This is the only reliable way to get clean white nodes with no line artifacts.
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  securityLevel: 'loose',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  flowchart: {
    htmlLabels: false,
    curve: 'basis',
    nodeSpacing: 55,
    rankSpacing: 65,
    padding: 14,
  },
  themeVariables: {
    background:           '#0d1117',
    mainBkg:              '#ffffff',
    primaryColor:         '#ffffff',
    secondaryColor:       '#ffffff',
    tertiaryColor:        '#ffffff',
    nodeBorder:           '#94a3b8',
    primaryBorderColor:   '#94a3b8',
    secondaryBorderColor: '#94a3b8',
    tertiaryBorderColor:  '#94a3b8',
    primaryTextColor:     '#1e293b',
    secondaryTextColor:   '#1e293b',
    tertiaryTextColor:    '#1e293b',
    nodeTextColor:        '#1e293b',
    lineColor:            '#f97316',
    edgeLabelBackground:  '#ffffff',
    labelTextColor:       '#1e293b',
    clusterBkg:           '#131c2e',
    clusterBorder:        '#475569',
    titleColor:           '#e2e8f0',
    labelBoxBkgColor:     '#ffffff',
    labelBoxBorderColor:  '#94a3b8',
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
        // 1. With htmlLabels:false, replace literal \n and <br/> with actual newlines
        //    Mermaid SVG text mode uses \n for multi-line tspan rendering
        let processedChart = cleanChart
          .replace(/\\n/g, '\n')
          .replace(/<br\s*\/?>/gi, '\n')

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
        
        const { svg: rawSvg } = await mermaid.render(renderId, processedChart)
        
        if (isMounted) {
          setSvg(sanitizeSvg(rawSvg))
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
            padding: '24px 20px',
            borderRadius: 10,
            border: '1px solid rgba(249,115,22,0.1)',
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



