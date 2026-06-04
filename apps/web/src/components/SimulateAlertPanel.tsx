/**
 * SimulateAlertPanel — V3.5+
 *
 * Chaos Engineering Console. Loads simulation presets from the API
 * (managed in the Application Panel → Simulator Presets tab) so that
 * any onboarded application's services and scenarios are available
 * without hardcoding anything in source.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { simulateAlert } from '../api/client'
import { useApplicationPresets } from '../hooks/useApplicationData'

const ICON_MAP: Record<string, React.ReactNode> = {
  hpa: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>,
  thunder: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
  lock: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  memory: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>,
  custom: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
}

const ACCENT_FALLBACKS = [
  'var(--c-signal)',
  'var(--c-red)',
  'var(--c-purple)',
  'var(--c-info)',
  'var(--c-green)',
]

export function SimulateAlertPanel() {
  const navigate = useNavigate()
  const { data: presets, loading, error: loadError } = useApplicationPresets()
  const [selected, setSelected] = useState<string | null>(null)
  const [customDesc, setCustomDesc] = useState('')
  const [firing, setFiring] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activePreset = presets.find(p => p.id === selected)

  async function fire() {
    if (!activePreset) return
    setFiring(true)
    setError(null)
    try {
      const result = await simulateAlert({
        service_name: activePreset.service_name,
        environment: activePreset.environment,
        scenario: activePreset.scenario_id,
        description: customDesc.trim() || undefined,
      })
      navigate(`/investigations/${result.request_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Simulation failed')
      setFiring(false)
    }
  }

  return (
    <div style={{
      background: 'var(--c-error-bg)',
      border: '1px solid var(--c-error-border)',
      borderRadius: 12,
      padding: '24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 16,
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Hazard stripes top border */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 4,
        background: 'repeating-linear-gradient(45deg, var(--c-red), var(--c-red) 10px, transparent 10px, transparent 20px)'
      }} />

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1.4rem' }}>☣️</span>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--c-text)' }}>
              Chaos Engineering Console
            </div>
            <p style={{ margin: '2px 0 0', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)' }}>
              Select experiment — fires the full investigation pipeline
            </p>
          </div>
        </div>
        <div style={{
          background: 'var(--c-error-bg)', border: '1px solid var(--c-error-border)',
          padding: '2px 8px', borderRadius: 6, color: 'var(--c-red)', fontSize: '0.6875rem',
          fontFamily: 'var(--font-mono)', fontWeight: 600
        }}>
          RED TEAM MODE
        </div>
      </div>

      {/* Loading / empty state */}
      {loading && (
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
          Loading scenarios…
        </p>
      )}

      {!loading && presets.length === 0 && (
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)' }}>
          No presets configured. Add scenarios in the Application Panel → Simulator Presets tab.
        </p>
      )}

      {/* Preset grid */}
      {!loading && presets.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {presets.map((preset, idx) => {
            const isSelected = selected === preset.id
            const accent = preset.accent_color || ACCENT_FALLBACKS[idx % ACCENT_FALLBACKS.length]
            const icon = ICON_MAP[preset.icon_key ?? 'custom'] ?? ICON_MAP.custom
            return (
              <button
                key={preset.id}
                onClick={() => setSelected(isSelected ? null : preset.id)}
                style={{
                  position: 'relative',
                  padding: '10px 12px',
                  borderRadius: 6,
                  background: isSelected ? `color-mix(in srgb, ${accent} 15%, transparent)` : 'var(--c-surface-2)',
                  border: `1px solid ${isSelected ? accent : 'var(--c-border)'}`,
                  boxShadow: isSelected ? `0 4px 20px color-mix(in srgb, ${accent} 15%, transparent)` : 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                }}
                className="corvin-interactive"
              >
                {isSelected && (
                  <span style={{
                    position: 'absolute', top: 8, right: 10,
                    fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                    color: accent, fontWeight: 700,
                  }}>✓</span>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ color: isSelected ? accent : 'var(--c-text-faint)' }}>{icon}</span>
                  <span style={{
                    fontFamily: 'var(--font-display)', fontWeight: 700,
                    fontSize: '0.72rem', color: isSelected ? accent : 'var(--c-text)',
                  }}>
                    {preset.label}
                  </span>
                </div>
                <p style={{
                  margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                  color: 'var(--c-text-faint)', lineHeight: 1.5,
                  display: '-webkit-box', WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical', overflow: 'hidden',
                }}>
                  {preset.description}
                </p>
                <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', opacity: 0.6 }}>
                  {preset.service_name} / {preset.environment}
                  {preset.application_name && ` · ${preset.application_name}`}
                </p>
              </button>
            )
          })}
        </div>
      )}

      {/* Custom description */}
      {activePreset && (
        <div>
          <label style={{
            display: 'block', marginBottom: 4,
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '0.68rem', letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)',
          }}>
            Custom description (optional)
          </label>
          <textarea
            rows={2}
            value={customDesc}
            onChange={e => setCustomDesc(e.target.value)}
            placeholder={activePreset.description}
            className="corvin-interactive"
            style={{
              width: '100%', boxSizing: 'border-box',
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
              color: 'var(--c-text)', background: 'var(--c-surface-2)',
              border: '1px solid var(--c-border-hi)',
              borderRadius: 4, padding: '8px 10px', resize: 'none',
            }}
          />
        </div>
      )}

      {/* API load error */}
      {(error || loadError) && (
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-red)' }}>
          ✗ {error || loadError}
        </p>
      )}

      {/* Fire button */}
      <button
        onClick={fire}
        disabled={!selected || firing}
        style={{
          padding: '12px',
          borderRadius: 6,
          border: selected && !firing ? '1px solid var(--c-signal)' : '1px solid var(--c-border)',
          background: selected && !firing ? 'var(--c-signal)' : 'var(--c-surface-2)',
          color: selected && !firing ? 'white' : 'var(--c-text-faint)',
          fontFamily: 'var(--font-display)', fontWeight: 700,
          fontSize: '0.72rem', letterSpacing: '0.06em',
          cursor: selected && !firing ? 'pointer' : 'not-allowed',
          transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          opacity: !selected ? 0.6 : 1,
          boxShadow: selected && !firing ? '0 0 24px color-mix(in srgb, var(--c-signal) 45%, transparent)' : 'none',
        }}
      >
        {firing ? (
          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <svg style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} fill="none" viewBox="0 0 24 24">
              <circle style={{ opacity: 0.25 }} cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path style={{ opacity: 0.75 }} fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Firing simulation…
          </span>
        ) : selected ? (
          `⚡ Simulate ${activePreset?.label} on ${activePreset?.service_name}`
        ) : (
          'Select a scenario above'
        )}
      </button>
    </div>
  )
}
