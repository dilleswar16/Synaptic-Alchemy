import { useState, useEffect, useId } from 'react'
import mermaid from 'mermaid'
import { useTheme } from '../../context/ThemeContext'

// Inject global CSS. Force-replace on HMR reloads so changes take effect immediately.
// SVG spec: CSS properties always beat SVG presentation attributes (fill="...").
// So one blanket rect rule is sufficient — no class-name guessing needed.
if (typeof document !== 'undefined') {
  const existing = document.getElementById('corvin-mermaid-css')
  const css = `
    .corvin-mermaid svg { max-width: 100%; height: auto; overflow: visible; }

    /* ── Dark mode (default): dark elevated nodes, light text ── */
    .corvin-mermaid svg rect {
      fill: #1e2433 !important;
      stroke: #3a4558 !important;
    }

    .corvin-mermaid svg .cluster rect {
      fill: #111827 !important;
      stroke: #2d3748 !important;
    }

    .corvin-mermaid svg .edgeLabel rect {
      fill: #1a2e2d !important;
      stroke: rgba(13,148,136,0.4) !important;
    }

    .corvin-mermaid svg text, .corvin-mermaid svg tspan {
      fill: #e2e8f0 !important;
      font-family: 'JetBrains Mono', 'Fira Mono', monospace;
    }

    .corvin-mermaid svg .cluster text, .corvin-mermaid svg .cluster tspan {
      fill: #94a3b8 !important;
    }

    .corvin-mermaid svg .edgeLabel text, .corvin-mermaid svg .edgeLabel tspan {
      fill: #0d9488 !important;
    }

    /* ── Light mode: white nodes on subtle gray canvas ── */
    [data-theme="light"] .corvin-mermaid svg rect {
      fill: #ffffff !important;
      stroke: #64748b !important;
    }
    [data-theme="light"] .corvin-mermaid svg .cluster rect {
      fill: #f8fafc !important;
      stroke: #64748b !important;
    }
    [data-theme="light"] .corvin-mermaid svg .edgeLabel rect {
      fill: #f0fdfa !important;
      stroke: rgba(15,118,110,0.4) !important;
    }
    [data-theme="light"] .corvin-mermaid svg text, [data-theme="light"] .corvin-mermaid svg tspan {
      fill: #0f172a !important;
    }
    [data-theme="light"] .corvin-mermaid svg foreignObject span,
    [data-theme="light"] .corvin-mermaid svg foreignObject div,
    [data-theme="light"] .corvin-mermaid svg foreignObject p {
      color: #0f172a !important;
    }
    [data-theme="light"] .corvin-mermaid svg .cluster text, [data-theme="light"] .corvin-mermaid svg .cluster tspan {
      fill: #334155 !important;
    }
    [data-theme="light"] .corvin-mermaid svg .cluster foreignObject span,
    [data-theme="light"] .corvin-mermaid svg .cluster foreignObject div {
      color: #334155 !important;
    }
    [data-theme="light"] .corvin-mermaid svg .edgeLabel text, [data-theme="light"] .corvin-mermaid svg .edgeLabel tspan {
      fill: #115e59 !important;
    }
    [data-theme="light"] .corvin-mermaid svg .edgeLabel foreignObject span,
    [data-theme="light"] .corvin-mermaid svg .edgeLabel foreignObject div {
      color: #115e59 !important;
    }
    [data-theme="light"] .corvin-mermaid svg .edgePaths path {
      stroke: #0f766e !important;
    }
    [data-theme="light"] .corvin-mermaid svg path.flowchart-link {
      stroke: #0f766e !important;
    }

    /* Light-mode container: slate-tinted canvas so white nodes pop */
    [data-theme="light"] .corvin-mermaid {
      background: linear-gradient(160deg, #f1f5f9 0%, #e2e8f0 100%) !important;
      border-color: #cbd5e1 !important;
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
 * Patch Mermaid SVG using DOM parsing — regex is unreliable on complex SVG.
 * Sets theme-correct fills/strokes on every element directly.
 */
function setFillStroke(el: Element, fill: string, stroke?: string) {
  el.setAttribute('fill', fill)
  ;(el as HTMLElement).style?.setProperty?.('fill', fill, 'important')
  // Also set directly on style attribute string for SVG elements without style object
  const existingStyle = el.getAttribute('style') || ''
  const cleaned = existingStyle
    .replace(/fill\s*:\s*[^;]+;?/gi, '')
    .replace(/stroke\s*:\s*[^;]+;?/gi, '')
    .trim()
  let newStyle = `fill: ${fill} !important;`
  if (stroke) {
    el.setAttribute('stroke', stroke)
    newStyle += ` stroke: ${stroke} !important;`
  }
  el.setAttribute('style', cleaned ? `${cleaned}; ${newStyle}` : newStyle)
}

function sanitizeSvg(raw: string, isLight: boolean): string {
  const textColor   = isLight ? '#0f172a' : '#e2e8f0'
  const nodeFill    = isLight ? '#ffffff' : '#1e2433'
  const nodeStroke  = isLight ? '#64748b' : '#3a4558'
  const clusterFill = isLight ? '#f8fafc' : '#111827'
  const clusterStroke = isLight ? '#64748b' : '#2d3748'
  const edgeLabelBg   = isLight ? '#f0fdfa' : '#1a2e2d'
  const edgeLabelText = isLight ? '#115e59' : '#0d9488'
  const clusterText   = isLight ? '#334155' : '#94a3b8'
  const edgeColor     = isLight ? '#0f766e' : '#0d9488'

  const wrapper = document.createElement('div')
  wrapper.innerHTML = raw
  const svg = wrapper.querySelector('svg')
  if (!svg) return raw

  // Remove gradients and patterns that cause url() fill issues
  svg.querySelectorAll('linearGradient, pattern').forEach(el => el.remove())

  // --- Edge labels (specific — must come before general) ---
  svg.querySelectorAll('.edgeLabel rect').forEach(r => setFillStroke(r, edgeLabelBg, 'rgba(13,148,136,0.4)'))
  svg.querySelectorAll('.edgeLabel text, .edgeLabel tspan').forEach(t => setFillStroke(t, edgeLabelText))

  // --- Clusters ---
  svg.querySelectorAll('.cluster rect').forEach(r => setFillStroke(r, clusterFill, clusterStroke))
  svg.querySelectorAll('.cluster text, .cluster tspan').forEach(t => setFillStroke(t, clusterText))

  // --- General rects (nodes) — skip those already handled ---
  svg.querySelectorAll('rect').forEach(r => {
    if (r.closest('.edgeLabel') || r.closest('.cluster')) return
    setFillStroke(r, nodeFill, nodeStroke)
  })

  // --- All text/tspan NOT in edgeLabel or cluster ---
  svg.querySelectorAll('text, tspan').forEach(t => {
    if (t.closest('.edgeLabel') || t.closest('.cluster')) return
    setFillStroke(t, textColor)
  })

  // --- foreignObject HTML labels (span, div, p) ---
  svg.querySelectorAll('foreignObject span, foreignObject div, foreignObject p').forEach(el => {
    let color = textColor
    if (el.closest('.edgeLabel')) color = edgeLabelText
    else if (el.closest('.cluster')) color = clusterText
    ;(el as HTMLElement).style.setProperty('color', color, 'important')
  })

  // --- Polygons (diamond/decision shapes) ---
  svg.querySelectorAll('polygon').forEach(p => {
    if (p.closest('.edgeLabel') || p.closest('.cluster')) return
    setFillStroke(p, nodeFill, nodeStroke)
  })

  // --- Circles (for circular/stadium nodes) ---
  svg.querySelectorAll('circle').forEach(c => {
    if (c.closest('.edgeLabel') || c.closest('.cluster') || c.closest('marker')) return
    setFillStroke(c, nodeFill, nodeStroke)
  })

  // --- Edge paths ---
  svg.querySelectorAll('.edgePaths path, path.flowchart-link').forEach(p => {
    p.setAttribute('stroke', edgeColor)
    const s = p.getAttribute('style') || ''
    p.setAttribute('style', s.replace(/stroke\s*:[^;]+;?/gi, '') + `; stroke: ${edgeColor} !important;`)
  })

  // --- Arrowhead markers ---
  svg.querySelectorAll('marker path').forEach(p => setFillStroke(p, edgeColor, edgeColor))

  return wrapper.innerHTML
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
    mainBkg:              '#1e2433',
    primaryColor:         '#1e2433',
    secondaryColor:       '#1e2433',
    tertiaryColor:        '#1e2433',
    nodeBorder:           '#3a4558',
    primaryBorderColor:   '#3a4558',
    secondaryBorderColor: '#3a4558',
    tertiaryBorderColor:  '#3a4558',
    primaryTextColor:     '#e2e8f0',
    secondaryTextColor:   '#e2e8f0',
    tertiaryTextColor:    '#e2e8f0',
    nodeTextColor:        '#e2e8f0',
    lineColor:            '#0d9488',
    edgeLabelBackground:  '#1a2e2d',
    labelTextColor:       '#e2e8f0',
    clusterBkg:           '#111827',
    clusterBorder:        '#2d3748',
    titleColor:           '#94a3b8',
    labelBoxBkgColor:     '#1e2433',
    labelBoxBorderColor:  '#3a4558',
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
  const { theme } = useTheme()
  const isLight = theme === 'light'
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

        // 2. Sanitize node labels: parentheses inside ["..."] labels break Mermaid parsing
        //    e.g. ["chad-fundsso (SSO)"] → ["chad-fundsso - SSO"]
        //    Also strip escaped quotes inside labels
        processedChart = processedChart.replace(
          /\["([^"]*?)"\]/g,
          (_match: string, label: string) => {
            const safe = label
              .replace(/\\"/g, "'")              // escaped quotes → apostrophe
              .replace(/\(([^)]*)\)/g, '- $1')   // (SSO) → - SSO
            return `["${safe}"]`
          }
        )

        // 3. Mermaid 11 does not support rgba() in classDef — replace with hex equivalents
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
          setSvg(sanitizeSvg(rawSvg, isLight))
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
  }, [chart, uniqueId, isLight])

  // If we have a valid SVG, show it (even if we are currently re-rendering)
  if (svg) {
    return (
      <div style={{ position: 'relative', margin: '16px 0', width: '100%' }}>
        {/* Label above diagram */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <div style={{ flex: 1, height: 1, background: 'var(--c-border)' }} />
          <span style={{ fontFamily: 'monospace', fontSize: '0.6875rem', letterSpacing: '0.03em', textTransform: 'uppercase', color: 'var(--c-text-faint)' }}>diagram</span>
          <div style={{ flex: 1, height: 1, background: 'var(--c-border)' }} />
        </div>
        <div
          className="corvin-mermaid"
          dangerouslySetInnerHTML={{ __html: svg }}
          style={{
            display: 'flex',
            justifyContent: 'center',
            background: background ?? (isLight
              ? 'linear-gradient(160deg, #f1f5f9 0%, #e2e8f0 100%)'
              : 'linear-gradient(160deg, var(--c-surface) 0%, var(--c-surface-2) 100%)'),
            padding: '24px 20px',
            borderRadius: 10,
            border: isLight ? '1px solid #cbd5e1' : '1px solid var(--c-border-hi)',
            boxShadow: isLight ? '0 2px 12px rgba(0,0,0,0.08)' : 'var(--shadow-md, 0 4px 24px rgba(0,0,0,0.3))',
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
             backdropFilter: 'blur(4px)', border: '1px solid var(--c-border)'
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
          margin: 0, padding: '16px', background: 'var(--c-error-bg)', 
          border: '1px solid var(--c-error-border)', borderRadius: 8,
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
      background: 'var(--c-surface-2)',
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



