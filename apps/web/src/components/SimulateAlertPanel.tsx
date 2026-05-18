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
  icon: React.ReactNode
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
    label: 'Inject Scale Lag',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>,
    service: 'partnerapis',
    environment: 'dev',
    description: 'Freeze HPA controller — pods stuck at 1 replica despite high load.',
    accentColor: '#f97316',
    accentBg: 'rgba(249,115,22,0.15)',
    accentBorder: 'rgba(249,115,22,0.6)',
  },
  {
    id: 'five_zero_three_spike',
    label: 'Flood 503 Errors',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
    service: 'fundapis',
    environment: 'dev',
    description: 'Simulate network partition — flood 18% error rate on /v1/funds.',
    accentColor: '#ef4444',
    accentBg: 'rgba(239,68,68,0.15)',
    accentBorder: 'rgba(239,68,68,0.6)',
  },
  {
    id: 'auth_errors',
    label: 'Poison JWT Tokens',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
    service: 'fundsso',
    environment: 'dev',
    description: 'Corrupt identity cache — fundsso returning 401 on 35% of requests.',
    accentColor: '#a855f7',
    accentBg: 'rgba(168,85,247,0.15)',
    accentBorder: 'rgba(168,85,247,0.6)',
  },
  {
    id: 'memory_leak',
    label: 'Leak Heap Memory',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>,
    service: 'fundapis',
    environment: 'dev',
    description: 'Deploy memory pressure tool — simulate heap OOM trajectory.',
    accentColor: '#3b82f6',
    accentBg: 'rgba(59,130,246,0.15)',
    accentBorder: 'rgba(59,130,246,0.6)',
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
      background: 'rgba(239,68,68,0.03)',
      border: '1px solid rgba(239,68,68,0.2)',
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
        background: 'repeating-linear-gradient(45deg, #ef4444, #ef4444 10px, transparent 10px, transparent 20px)'
      }} />

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1.4rem', filter: 'drop-shadow(0 0 8px #ef4444)' }}>☣️</span>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 800,
              fontSize: '0.7rem', letterSpacing: '0.2em', textTransform: 'uppercase',
              color: '#ef4444',
            }}>
              Chaos Engineering Console
            </div>
            <p style={{
              margin: '2px 0 0',
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
              color: 'var(--c-text-faint)',
            }}>
              Select experiment to deploy into DEV environment
            </p>
          </div>
        </div>
        <div style={{ 
          background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', 
          padding: '2px 8px', borderRadius: 4, color: '#ef4444', fontSize: '0.68rem', 
          fontFamily: 'var(--font-mono)', fontWeight: 800 
        }}>
          RED TEAM MODE
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
                borderRadius: 6,
                background: isSelected ? `linear-gradient(135deg, ${preset.accentBg}, color-mix(in srgb, ${preset.accentBg} 10%, transparent))` : 'var(--c-surface-2)',
                border: `1px solid ${isSelected ? preset.accentColor : 'var(--c-border)'}`,
                boxShadow: isSelected ? `0 4px 20px color-mix(in srgb, ${preset.accentColor} 15%, transparent)` : 'none',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                outline: 'none',
              }}
            >
              {isSelected && (
                <span style={{
                  position: 'absolute', top: 8, right: 10,
                  fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                  color: preset.accentColor, fontWeight: 700,
                  textShadow: `0 0 8px color-mix(in srgb, ${preset.accentColor} 50%, transparent)`,
                }}>✓</span>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{ color: isSelected ? preset.accentColor : 'var(--c-text-faint)' }}>{preset.icon}</span>
                <span style={{
                  fontFamily: 'var(--font-display)', fontWeight: 700,
                  fontSize: '0.72rem', color: isSelected ? preset.accentColor : 'var(--c-text)',
                  textShadow: isSelected ? `0 0 10px color-mix(in srgb, ${preset.accentColor} 40%, transparent)` : 'none',
                }}>
                  {preset.label}
                </span>
              </div>
              <p style={{
                margin: 0,
                fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
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
              fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
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
          padding: '12px',
          borderRadius: 6,
          border: selected && !firing ? '1px solid var(--c-signal)' : '1px solid var(--c-border)',
          background: selected && !firing ? 'var(--c-signal)' : 'var(--c-surface-2)',
          color: selected && !firing ? '#fff' : 'var(--c-text-faint)',
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: '0.72rem',
          letterSpacing: '0.06em',
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
          `⚡ Simulate ${activePreset?.label} on ${activePreset?.service}`
        ) : (
          'Select a scenario above'
        )}
      </button>
    </div>
  )
}
