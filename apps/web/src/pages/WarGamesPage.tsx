import { useState } from 'react'
import NavBar from '../components/NavBar'
import { SimulateAlertPanel } from '../components/SimulateAlertPanel'
import AlertCorrelationPanel from '../components/AlertCorrelationPanel'
import CapacityForecastPanel from '../components/CapacityForecastPanel'

type Tab = 'chaos' | 'correlation' | 'capacity' | 'replay'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'chaos', label: 'Chaos Experiments', icon: '☣️' },
  { id: 'correlation', label: 'Alert Correlation', icon: '🔗' },
  { id: 'capacity', label: 'Capacity Forecast', icon: '📈' },
  { id: 'replay', label: 'Incident Replay', icon: '⏪' },
]

export default function WarGamesPage() {
  const [activeTab, setActiveTab] = useState<Tab>('chaos')

  return (
    <div style={{ minHeight: '100vh', background: 'var(--c-bg)', color: 'var(--c-text)' }}>
      <NavBar />
      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        {/* Page Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.6rem',
            fontWeight: 800,
            margin: '0 0 6px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <span style={{ fontSize: '1.4rem' }}>⚔</span> War Games
          </h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--c-text-muted)', margin: 0 }}>
            Chaos engineering, alert correlation analysis, capacity forecasting, and incident replay simulations.
            All actions require human approval before execution.
          </p>
        </div>

        {/* Tab bar */}
        <div style={{
          display: 'flex',
          gap: 2,
          marginBottom: 24,
          borderBottom: '1px solid var(--c-border)',
          paddingBottom: 0,
        }}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '10px 18px',
                fontSize: '0.82rem',
                fontWeight: activeTab === tab.id ? 700 : 500,
                color: activeTab === tab.id ? 'var(--c-link)' : 'var(--c-text-muted)',
                background: 'none',
                border: 'none',
                borderBottom: activeTab === tab.id ? '2px solid var(--c-link)' : '2px solid transparent',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'chaos' && (
          <div style={{ maxWidth: 700 }}>
            <SimulateAlertPanel />
          </div>
        )}

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
