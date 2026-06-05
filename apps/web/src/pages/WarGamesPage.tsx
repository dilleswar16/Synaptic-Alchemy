import { useState } from 'react'
import NavBar from '../components/NavBar'
import { ChaosExperimentStudio } from '../components/ChaosExperimentStudio'
import AlertCorrelationPanel from '../components/AlertCorrelationPanel'
import CapacityForecastPanel from '../components/CapacityForecastPanel'

type Tab = 'chaos' | 'correlation' | 'capacity' | 'replay'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'chaos', label: 'Chaos Studio', icon: '⚗️' },
  { id: 'correlation', label: 'Alert Correlation', icon: '🔗' },
  { id: 'capacity', label: 'Capacity Forecast', icon: '📈' },
  { id: 'replay', label: 'Incident Replay', icon: '⏪' },
]

export default function WarGamesPage() {
  const [activeTab, setActiveTab] = useState<Tab>('chaos')

  return (
    <div style={{ minHeight: '100vh', background: 'var(--c-bg)', color: 'var(--c-text)' }}>
      <NavBar />
      <main style={{ maxWidth: 1280, margin: '0 auto', padding: '40px 24px' }}>
        {/* Page Header */}
        <div style={{
          marginBottom: 36,
          paddingBottom: 32,
          borderBottom: '1px solid var(--c-border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, marginBottom: 16 }}>
            <div>
              <h1 style={{
                fontFamily: 'var(--font-display)', fontSize: '2.2rem', fontWeight: 900,
                margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 12,
                letterSpacing: '-0.02em',
              }}>
                <span style={{ fontSize: '2rem' }}>⚔</span> War Games
              </h1>
              <p style={{
                fontSize: '1rem', color: 'var(--c-text-dim)', margin: 0, lineHeight: 1.7,
                maxWidth: 700,
              }}>
                Kubernetes chaos experiments · Alert correlation · Capacity forecasting · Incident replay.
                All actions require approval before execution.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'flex-start', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.05em',
                color: 'var(--c-green)', background: 'rgba(34,197,94,0.12)',
                border: '1px solid rgba(34,197,94,0.3)', borderRadius: 6, padding: '5px 10px',
                textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <span>⚗️</span> <span>5 kubectl</span>
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.05em',
                color: '#b45309', background: 'rgba(251,191,36,0.12)',
                border: '1px solid rgba(251,191,36,0.3)', borderRadius: 6, padding: '5px 10px',
                textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <span>☣️</span> <span>4 simulated</span>
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 800, letterSpacing: '0.05em',
                color: 'var(--c-text-faint)', background: 'var(--c-surface-3)',
                border: '1px solid var(--c-border)', borderRadius: 6, padding: '5px 10px',
                textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <span>🔁</span> <span>auto-rollback</span>
              </span>
            </div>
          </div>
        </div>

        {/* Tab bar — redesigned */}
        <div style={{ marginBottom: 32, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <div style={{
            display: 'flex', gap: 2,
          }}>
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    padding: '12px 20px', fontSize: '0.9rem', fontWeight: isActive ? 700 : 600,
                    color: isActive ? 'var(--c-text)' : 'var(--c-text-dim)',
                    background: isActive ? 'rgba(0,122,188,0.12)' : 'var(--c-surface-2)',
                    border: isActive ? '2px solid var(--c-primary)' : '1px solid var(--c-border)',
                    borderRadius: 8, cursor: 'pointer', transition: 'all 0.18s cubic-bezier(0.4, 0, 0.2, 1)',
                    display: 'flex', alignItems: 'center', gap: 8,
                    fontFamily: 'var(--font-body)', letterSpacing: '-0.01em',
                  }}
                >
                  <span style={{ fontSize: '1.1rem' }}>{tab.icon}</span>
                  {tab.label}
                </button>
              )
            })}
          </div>
          <p style={{
            margin: '8px 0 0', fontSize: '0.72rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)',
          }}>
            Select a war game scenario to test your platform's resilience and detection capabilities
          </p>
        </div>

        {/* Tab content */}
        {activeTab === 'chaos' && <ChaosExperimentStudio />}

        {activeTab === 'correlation' && <AlertCorrelationPanel />}

        {activeTab === 'capacity' && <CapacityForecastPanel />}

        {activeTab === 'replay' && (
          <div style={{
            background: 'var(--c-surface)',
            border: '1px solid var(--c-border)',
            borderRadius: 12,
            padding: 32,
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>⏪</div>
            <h3 style={{ fontFamily: 'var(--font-display)', margin: '0 0 8px' }}>Incident Replay</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--c-text-muted)', maxWidth: 480, margin: '0 auto' }}>
              Replay past incidents in a sandboxed environment to test new runbooks and validate
              detection improvements. Select a completed investigation to create a replay scenario.
            </p>
            <div style={{
              marginTop: 20,
              padding: 16,
              background: 'var(--c-bg)',
              borderRadius: 8,
              border: '1px dashed var(--c-border)',
              fontSize: '0.8rem',
              color: 'var(--c-text-muted)',
            }}>
              Coming soon — will pull from completed investigations with post-mortems for replay scenarios.
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
