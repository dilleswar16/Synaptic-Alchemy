/**
 * StreamingProgress — displays live stage events from an investigation stream.
 *
 * Shows a compact progress list where each stage transitions through:
 *   ⏳ started  →  ✅ complete  or  ❌ error
 *
 * When the stream ends with 'complete', a "View Results" link is shown so the
 * user can navigate to the full investigation detail page.
 */

import { useNavigate } from 'react-router-dom'
import type { StageEvent } from '../hooks/useInvestigationStream'

// ── Helpers ───────────────────────────────────────────────────────────────────

const STAGE_LABEL: Record<string, string> = {
  evidence: 'Collecting evidence',
  rca: 'Generating root cause analysis',
  fix_strategy: 'Building fix strategy',
  complete: 'Complete',
  error: 'Error',
}

const STATUS_ICON: Record<string, string> = {
  started: '⏳',
  complete: '✅',
  error: '❌',
}

const STATUS_COLOR: Record<string, string> = {
  started: '#d46b08',
  complete: '#389e0d',
  error: '#cf1322',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface StreamingProgressProps {
  stages: StageEvent[]
  streamText: Record<string, string>
  isStreaming: boolean
  isComplete: boolean
  error: string | null
  requestId: string | null
  onReset: () => void
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** Monospace scrolling box showing raw LLM output as it streams in. */
function TokenTextBox({ text }: { text: string }) {
  return (
    <pre
      style={{
        margin: '6px 0 2px',
        padding: '8px 10px',
        background: '#1a1a2e',
        color: '#a8ff78',
        fontSize: '0.72rem',
        borderRadius: '4px',
        maxHeight: '140px',
        overflowY: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontFamily: '"Cascadia Code", "Fira Mono", monospace',
      }}
    >
      {text}
      <span style={{ opacity: 0.6, animation: 'blink 0.8s step-start infinite' }}>▋</span>
    </pre>
  )
}

/** Structured card shown after RCA complete. */
function RCAContent({ s }: { s: StageEvent }) {
  const factors = Array.isArray(s.contributing_factors) ? (s.contributing_factors as string[]) : []
  return (
    <div style={{ margin: '6px 0 2px', padding: '10px 12px', background: '#f6ffed', borderRadius: '4px', border: '1px solid #b7eb8f' }}>
      {typeof s.summary === 'string' && (
        <p style={{ margin: '0 0 4px', fontSize: '0.82rem' }}><strong>Summary:</strong> {s.summary}</p>
      )}
      {typeof s.root_cause === 'string' && (
        <p style={{ margin: '0 0 4px', fontSize: '0.82rem' }}><strong>Root Cause:</strong> {s.root_cause}</p>
      )}
      {factors.length > 0 && (
        <div style={{ fontSize: '0.82rem' }}>
          <strong>Factors:</strong>
          <ul style={{ margin: '2px 0 0', paddingLeft: '1.2rem' }}>
            {factors.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Structured card shown after fix strategy complete. */
function FixStrategyContent({ s }: { s: StageEvent }) {
  const actions = Array.isArray(s.action_summaries) ? (s.action_summaries as string[]) : []
  return (
    <div style={{ margin: '6px 0 2px', padding: '10px 12px', background: '#e6f4ff', borderRadius: '4px', border: '1px solid #91caff' }}>
      {typeof s.summary === 'string' && (
        <p style={{ margin: '0 0 4px', fontSize: '0.82rem' }}><strong>Strategy:</strong> {s.summary}</p>
      )}
      {actions.length > 0 && (
        <div style={{ fontSize: '0.82rem' }}>
          <strong>Actions:</strong>
          <ul style={{ margin: '2px 0 0', paddingLeft: '1.2rem' }}>
            {actions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function StreamingProgress({
  stages,
  streamText,
  isStreaming,
  isComplete,
  error,
  requestId,
  onReset,
}: StreamingProgressProps) {
  const navigate = useNavigate()

  if (!isStreaming && !isComplete && stages.length === 0) {
    return null
  }

  // Determine which stage is currently generating (for live token box)
  const activeStage = isStreaming
    ? (stages.filter((s) => s.stage !== 'complete' && s.stage !== 'error').at(-1)?.stage ?? null)
    : null

  return (
    <section
      style={{
        marginTop: '2rem',
        padding: '1.2rem 1.5rem',
        border: '1px solid #e8e8e8',
        borderRadius: '8px',
        background: '#fafafa',
        fontFamily: 'sans-serif',
      }}
    >
      <style>{`
        @keyframes blink { 50% { opacity: 0 } }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <h3 style={{ margin: 0, fontSize: '1rem' }}>
          {isStreaming ? '🔍 Investigation in progress…' : isComplete && !error ? '✅ Investigation complete' : '❌ Investigation failed'}
        </h3>
        <button
          onClick={onReset}
          style={{
            padding: '3px 10px',
            fontSize: '0.8rem',
            cursor: 'pointer',
            border: '1px solid #d9d9d9',
            borderRadius: '4px',
            background: '#fff',
            color: '#666',
          }}
        >
          Clear
        </button>
      </div>

      {/* Stage list */}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {stages
          .filter((s) => s.stage !== 'complete' && s.stage !== 'error')
          .map((s, i) => (
            <li
              key={i}
              style={{
                padding: '4px 0',
                borderBottom: '1px solid #f0f0f0',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                <span style={{ fontSize: '1rem', marginTop: '1px' }}>
                  {STATUS_ICON[s.status] ?? '•'}
                </span>
                <div style={{ flex: 1 }}>
                  <span
                    style={{
                      fontWeight: 600,
                      color: STATUS_COLOR[s.status] ?? '#333',
                      fontSize: '0.9rem',
                    }}
                  >
                    {STAGE_LABEL[s.stage] ?? s.stage}
                  </span>
                  {s.status === 'complete' && s.stage === 'rca' && typeof s.confidence === 'string' && (
                    <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: '#888' }}>
                      (confidence: {s.confidence})
                    </span>
                  )}
                  {s.status === 'complete' && s.stage === 'fix_strategy' && typeof s.action_count === 'number' && (
                    <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: '#888' }}>
                      ({s.action_count} action{s.action_count !== 1 ? 's' : ''})
                    </span>
                  )}
                  <p style={{ margin: '1px 0 0', fontSize: '0.8rem', color: '#888' }}>
                    {s.message}
                  </p>

                  {/* Live token stream — shown while this stage is actively generating */}
                  {s.status === 'started' && activeStage === s.stage && streamText[s.stage] && (
                    <TokenTextBox text={streamText[s.stage]} />
                  )}

                  {/* Structured RCA content after complete */}
                  {s.status === 'complete' && s.stage === 'rca' && (
                    <RCAContent s={s} />
                  )}

                  {/* Structured fix strategy content after complete */}
                  {s.status === 'complete' && s.stage === 'fix_strategy' && (
                    <FixStrategyContent s={s} />
                  )}
                </div>
              </div>
            </li>
          ))}
      </ul>

      {/* Error message */}
      {error && (
        <p
          style={{
            margin: '0.75rem 0 0',
            padding: '8px 12px',
            background: '#fff1f0',
            color: '#cf1322',
            borderRadius: '6px',
            fontSize: '0.9rem',
          }}
        >
          {error}
        </p>
      )}

      {/* Success: View Results link */}
      {isComplete && !error && requestId && (
        <div style={{ marginTop: '1rem' }}>
          <button
            onClick={() => navigate(`/investigations/${requestId}`)}
            style={{
              padding: '8px 18px',
              background: '#1677ff',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.9rem',
            }}
          >
            View Full Results →
          </button>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </section>
  )
}
