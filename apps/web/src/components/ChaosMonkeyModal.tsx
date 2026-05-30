import { useState } from 'react'
import { API_BASE } from '../api/baseUrl'

interface ChaosMonkeyModalProps {
  onClose: () => void
}

export function ChaosMonkeyModal({ onClose }: ChaosMonkeyModalProps) {
  const [service, setService] = useState('fundapis')
  const [faultType, setFaultType] = useState('kill_pod')
  const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')

  const handleInject = async () => {
    setStatus('running')
    try {
      const resp = await fetch(`${API_BASE}/triggers/chaos-monkey`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service_name: service,
          environment: 'prod',
          fault_type: faultType
        })
      })
      const data = await resp.json()
      if (resp.ok) {
        setStatus('success')
        setMessage(`Fault injected successfully. Investigation ${data.request_id} started.`)
      } else {
        setStatus('error')
        setMessage(data.detail || 'Failed to inject fault')
      }
    } catch (err: any) {
      setStatus('error')
      setMessage(err.message)
    }
  }

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 100,
          background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)'
        }}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        zIndex: 101, background: 'var(--c-surface)', width: '90%', maxWidth: 450,
        borderRadius: 12, border: '1px solid var(--c-error-border)', boxShadow: 'var(--shadow-xl)',
        overflow: 'hidden'
      }}>
        <div style={{ padding: '16px 20px', background: 'var(--c-error-bg)', borderBottom: '1px solid var(--c-error-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--c-red)', display: 'flex', alignItems: 'center', gap: 8 }}>
            🐵 AI Chaos Monkey
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--c-red)', cursor: 'pointer', fontSize: '1.2rem' }}>×</button>
        </div>

        <div style={{ padding: 20 }}>
          <p style={{ margin: '0 0 16px 0', fontSize: '0.8rem', color: 'var(--c-text-dim)' }}>
            Inject a synthetic fault into a live service to trigger Corvin's auto-healing capabilities.
          </p>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: 6, color: 'var(--c-text)' }}>Target Service</label>
            <select value={service} onChange={e => setService(e.target.value)} style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)', color: 'var(--c-text)' }}>
              <option value="fundapis">fundapis</option>
              <option value="fundsso">fundsso</option>
              <option value="partnerapis">partnerapis</option>
            </select>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: 6, color: 'var(--c-text)' }}>Fault Type</label>
            <select value={faultType} onChange={e => setFaultType(e.target.value)} style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-surface-2)', color: 'var(--c-text)' }}>
              <option value="kill_pod">Kill Pods (Triggers PodRestart)</option>
              <option value="latency_spike">Latency Spike (Triggers APIM Timeout)</option>
            </select>
          </div>

          {status !== 'idle' && (
            <div style={{
              padding: 12, borderRadius: 6, marginBottom: 20, fontSize: '0.75rem',
              background: status === 'error' ? 'var(--c-error-bg)' : status === 'success' ? 'var(--c-success-bg)' : 'var(--c-surface-2)',
              color: status === 'error' ? 'var(--c-red)' : status === 'success' ? 'var(--c-green)' : 'var(--c-text)',
              border: `1px solid ${status === 'error' ? 'var(--c-error-border)' : status === 'success' ? 'var(--c-success-border)' : 'var(--c-border)'}`
            }}>
              {status === 'running' ? 'Injecting fault...' : message}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'transparent', color: 'var(--c-text-dim)', cursor: 'pointer', fontSize: '0.8rem' }}>
              Cancel
            </button>
            <button
              onClick={handleInject}
              disabled={status === 'running'}
              style={{ padding: '8px 16px', borderRadius: 6, border: 'none', background: 'var(--c-red)', color: 'white', fontWeight: 600, cursor: status === 'running' ? 'default' : 'pointer', fontSize: '0.8rem' }}
            >
              {status === 'running' ? 'Unleashing...' : 'Inject Fault'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
