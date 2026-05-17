import React, { useState, useEffect, useId } from 'react'
import mermaid from 'mermaid'

// Global configuration
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'var(--font-mono)',
})

interface MermaidChartProps {
  chart: string
  background?: string
}

/**
 * Bulletproof Mermaid v11 component for React.
 * Handles high-frequency updates during AI streaming.
 */
export function MermaidChart({ chart, background = 'rgba(0,0,0,0.2)' }: MermaidChartProps) {
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
        
        // 2. Try to wrap unquoted labels that contain special chars (advanced, but let's stick to basics first)

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
        <div 
          dangerouslySetInnerHTML={{ __html: svg }} 
          style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            background, 
            padding: '24px', 
            borderRadius: 12, 
            border: '1px solid var(--c-border-hi)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
            overflowX: 'auto',
            transition: 'opacity 0.2s',
            opacity: isRendering ? 0.8 : 1
          }} 
        />
        {isRendering && (
           <div style={{
             position: 'absolute', top: 12, right: 12,
             display: 'flex', alignItems: 'center', gap: 6,
             background: 'rgba(0,0,0,0.5)', padding: '4px 10px', borderRadius: 6,
             fontSize: '0.6rem', color: 'var(--c-signal)', fontFamily: 'var(--font-mono)',
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



