/**
 * SimulateAlertPanel — V3.5
 *
 * Hackathon demo widget: fires a synthetic alert investigation with one click.
 * Shows 4 preset scenarios, then navigates to the new investigation detail page.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { simulateAlert } from '../api/client'

interface Preset {
  id: string
  label: string
  icon: string
  service: string
  environment: string
  description: string
  accentColor: string
  accentBg: string
  accentBorder: string
}

const PRESETS: Preset[] = [
  {
    id: 'hpa_failure',
    label: 'HPA Failure',
    icon: '⚠',
    service: 'partnerapis',
    environment: 'dev',
    description: 'HPA not scaling — pods stuck at 1 replica despite 92% CPU.',
    accentColor: '#f59e0b',
    accentBg: 'rgba(245,158,11,0.10)',
    accentBorder: 'rgba(245,158,11,0.45)',
  },
  {
    id: 'five_zero_three_spike',
    label: '503 Spike',
    icon: '⚡',
    service: 'fundapis',
    environment: 'dev',
    description: '503 error rate spiked to 18% on /v1/funds. Two pods restarted.',
    accentColor: 'var(--c-red)',
    accentBg: 'rgba(239,68,68,0.10)',
    accentBorder: 'rgba(239,68,68,0.45)',
  },
  {
    id: 'auth_errors',
    label: 'Auth Errors',
    icon: '🔒',
    service: 'fundsso',
    environment: 'dev',
    description: 'JWT validation failures — fundsso returning 401 on 35% of requests.',
    accentColor: '#a78bfa',
    accentBg: 'rgba(167,139,250,0.10)',
    accentBorder: 'rgba(167,139,250,0.45)',
  },
  {
    id: 'memory_leak',
    label: 'Memory Leak',
    icon: '💾',
    service: 'fundapis',
    environment: 'dev',
    description: 'Heap at 89% — fundapis OOM kill expected within 2 hours.',
    accentColor: '#60a5fa',
    accentBg: 'rgba(96,165,250,0.10)',
    accentBorder: 'rgba(96,165,250,0.45)',
  },
]

export function SimulateAlertPanel() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string | null>(null)
  const [customDesc, setCustomDesc] = useState('')
  const [firing, setFiring] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activePreset = PRESETS.find(p => p.id === selected)

  async function fire() {
    if (!activePreset) return
    setFiring(true)
    setError(null)
    try {
      const result = await simulateAlert({
        service_name: activePreset.service,
        environment: activePreset.environment,
        scenario: activePreset.id,
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
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border-hi)',
      borderRadius: 6,
      padding: '18px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: '1.1rem' }}>🧪</span>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '0.62rem', letterSpacing: '0.18em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)',
          }}>
            Alert Simulator
          </div>
          <p style={{
            margin: '2px 0 0',
            fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
            color: 'var(--c-text-faint)',
          }}>
            Fire a synthetic incident to demo Corvin in action
          </p>
        </div>
      </div>

      {/* Preset grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {PRESETS.map(preset => {
          const isSelected = selected === preset.id
          return (
            <button
              key={preset.id}
              onClick={() => setSelected(isSelected ? null : preset.id)}
              style={{
                position: 'relative',
                padding: '10px 12px',
                borderRadius: 4,
                background: isSelected ? preset.accentBg : 'var(--c-surface-2)',
                border: `1px solid ${isSelected ? preset.accentBorder : 'var(--c-border)'}`,
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'all 0.15s',
                outline: 'none',
              }}
            >
              {isSelected && (
                <span style={{
                  position: 'absolute', top: 6, right: 8,
                  fontFamily: 'var(--font-mono)', fontSize: '0.6rem',
                  color: preset.accentColor, fontWeight: 700,
                }}>✓</span>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{ fontSize: '0.9rem' }}>{preset.icon}</span>
                <span style={{
                  fontFamily: 'var(--font-display)', fontWeight: 700,
                  fontSize: '0.72rem', color: isSelected ? preset.accentColor : 'var(--c-text)',
                }}>
                  {preset.label}
                </span>
              </div>
              <p style={{
                margin: 0,
                fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
                color: 'var(--c-text-faint)', lineHeight: 1.5,
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}>
                {preset.description}
              </p>
              <p style={{
                margin: '4px 0 0',
                fontFamily: 'var(--font-mono)', fontSize: '0.55rem',
                color: 'var(--c-text-faint)', opacity: 0.6,
              }}>
                {preset.service} / {preset.environment}
              </p>
            </button>
          )
        })}
      </div>

      {/* Custom description */}
      {activePreset && (
        <div>
          <label style={{
            display: 'block', marginBottom: 4,
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '0.58rem', letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--c-text-muted)',
          }}>
            Custom description (optional)
          </label>
          <textarea
            rows={2}
            value={customDesc}
            onChange={e => setCustomDesc(e.target.value)}
            placeholder={activePreset.description}
            style={{
              width: '100%', boxSizing: 'border-box',
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
              color: 'var(--c-text)', background: 'var(--c-surface-2)',
              border: '1px solid var(--c-border-hi)',
              borderRadius: 4, padding: '8px 10px', resize: 'none',
              outline: 'none',
            }}
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <p style={{
          margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
          color: 'var(--c-red)',
        }}>
          ✗ {error}
        </p>
      )}

      {/* Fire button */}
      <button
        onClick={fire}
        disabled={!selected || firing}
        style={{
          padding: '10px',
          borderRadius: 4,
          border: selected && !firing ? '1px solid var(--c-signal)' : '1px solid var(--c-border)',
          background: selected && !firing ? 'var(--c-signal)' : 'var(--c-surface-2)',
          color: selected && !firing ? '#fff' : 'var(--c-text-faint)',
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: '0.72rem',
          letterSpacing: '0.06em',
          cursor: selected && !firing ? 'pointer' : 'not-allowed',
          transition: 'all 0.15s',
          opacity: !selected ? 0.6 : 1,
          boxShadow: selected && !firing ? '0 0 14px rgba(249,115,22,0.3)' : 'none',
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
          `⚡ Simulate ${activePreset?.label} on ${activePreset?.service}`
        ) : (
          'Select a scenario above'
        )}
      </button>
    </div>
  )
}
