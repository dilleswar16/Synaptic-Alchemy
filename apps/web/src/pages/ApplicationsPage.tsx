import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Layout from '../components/Layout'
import {
  listApplications,
  getApplication,
  createApplication,
  updateApplication,
  deleteApplication,
  addService,
  deleteService,
  addConnector,
  deleteConnector,
  testConnector,
  addSloConfig,
  updateSloConfig,
  deleteSloConfig,
  addNotificationContact,
  deleteNotificationContact,
  addOutboundConnector,
  deleteOutboundConnector,
  migrateFromYaml,
  type Application,
  type ApplicationService,
  type LogSource,
  type SloConfig,
  type NotificationContact,
  type OutboundConnector,
} from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  frontend: '#6366f1',
  api: '#06b6d4',
  worker: '#f59e0b',
  db: '#22c55e',
  cache: '#a855f7',
  gateway: '#ec4899',
}

const SOURCE_ICONS: Record<string, string> = {
  azure_monitor: '☁',
  elastic: '⚡',
  byoa: '⊕',
  aks: '⎈',
}

const SLI_LABELS: Record<string, string> = {
  availability: 'Availability',
  latency: 'Latency p99',
}

function TierBadge({ tier }: { tier: string }) {
  const color = TIER_COLORS[tier] ?? '#6b7280'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: '0.65rem',
      fontWeight: 700,
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
      background: `${color}22`,
      color,
      border: `1px solid ${color}55`,
      fontFamily: 'var(--font-mono)',
    }}>
      {tier}
    </span>
  )
}

function StatusDot({ ok, tested }: { ok: boolean | null; tested: boolean }) {
  if (!tested) return <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--c-border)', display: 'inline-block' }} />
  return <span style={{ width: 8, height: 8, borderRadius: '50%', background: ok ? '#22c55e' : '#ef4444', display: 'inline-block' }} />
}

// ── Modal shell ───────────────────────────────────────────────────────────────

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }} onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--c-surface)',
          border: '1px solid var(--c-border)',
          borderRadius: 12,
          padding: 28,
          width: '100%',
          maxWidth: 520,
          boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1rem' }}>{title}</span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-muted)', fontSize: '1.2rem', lineHeight: 1 }}
          >×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{
        display: 'block', marginBottom: 5,
        fontFamily: 'var(--font-display)', fontSize: '0.65rem', fontWeight: 700,
        letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--c-text-muted)',
      }}>{label}</label>
      {children}
    </div>
  )
}

const INPUT_STYLE: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  padding: '8px 12px',
  background: 'var(--c-bg)',
  border: '1px solid var(--c-border)',
  borderRadius: 6,
  color: 'var(--c-text)',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.82rem',
  outline: 'none',
}

// ── Create Application Modal ──────────────────────────────────────────────────

function CreateAppModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [team, setTeam] = useState('')
  const [desc, setDesc] = useState('')
  const [env, setEnv] = useState('prod')

  const mut = useMutation({
    mutationFn: () => createApplication({ name, team_name: team, description: desc, environment_default: env }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['applications'] }); onClose() },
  })

  return (
    <Modal title="New Application" onClose={onClose}>
      <Field label="Name *">
        <input style={INPUT_STYLE} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. ChAD Platform" />
      </Field>
      <Field label="Team">
        <input style={INPUT_STYLE} value={team} onChange={e => setTeam(e.target.value)} placeholder="e.g. AMS Platform" />
      </Field>
      <Field label="Default Environment">
        <select style={INPUT_STYLE} value={env} onChange={e => setEnv(e.target.value)}>
          {['prod', 'staging', 'dev', 'uat'].map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </Field>
      <Field label="Description">
        <textarea style={{ ...INPUT_STYLE, resize: 'vertical', minHeight: 64 }} value={desc} onChange={e => setDesc(e.target.value)} placeholder="Brief description..." />
      </Field>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!name || mut.isPending}>
          {mut.isPending ? 'Creating…' : 'Create'}
        </button>
      </div>
      {mut.isError && <p style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: 8 }}>{String(mut.error)}</p>}
    </Modal>
  )
}

// ── Add Service Modal ─────────────────────────────────────────────────────────

function AddServiceModal({ appId, onClose }: { appId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [svcName, setSvcName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [tier, setTier] = useState('api')
  const [ns, setNs] = useState('')
  const [k8sLabel, setK8sLabel] = useState('')
  const [apimGateway, setApimGateway] = useState(false)
  const [apimApiId, setApimApiId] = useState('')
  const [isSsoDirect, setIsSsoDirect] = useState(false)

  const mut = useMutation({
    mutationFn: () => {
      const metadata: Record<string, unknown> = {}
      if (apimGateway) {
        metadata.apim_routes_through_gateway = true
        if (apimApiId.trim()) metadata.apim_api_id = apimApiId.trim()
      }
      if (isSsoDirect) metadata.is_sso_direct = true
      return addService(appId, {
        service_name: svcName,
        display_name: displayName || svcName,
        tier,
        namespace: ns || null,
        k8s_app_label: k8sLabel.trim() || null,
        metadata_json: metadata,
      })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  return (
    <Modal title="Add Service" onClose={onClose}>
      <Field label="Service Name *">
        <input style={INPUT_STYLE} value={svcName} onChange={e => setSvcName(e.target.value)} placeholder="e.g. fundapis" />
      </Field>
      <Field label="Display Name">
        <input style={INPUT_STYLE} value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="Defaults to service name" />
      </Field>
      <Field label="Tier">
        <select style={INPUT_STYLE} value={tier} onChange={e => setTier(e.target.value)}>
          {Object.keys(TIER_COLORS).map(t => <option key={t} value={t}>{t}</option>)}
          <option value="other">other</option>
        </select>
      </Field>
      <Field label="Kubernetes Namespace">
        <input style={INPUT_STYLE} value={ns} onChange={e => setNs(e.target.value)} placeholder="e.g. chad" />
      </Field>
      <Field label="K8s App Label">
        <input style={INPUT_STYLE} value={k8sLabel} onChange={e => setK8sLabel(e.target.value)} placeholder="e.g. chad-fundapis (deployment app label in cluster)" />
      </Field>
      <Field label="">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem' }}>
          <input type="checkbox" checked={apimGateway} onChange={e => setApimGateway(e.target.checked)} />
          Routes via APIM Gateway
        </label>
      </Field>
      {apimGateway && (
        <Field label="APIM API ID">
          <input style={INPUT_STYLE} value={apimApiId} onChange={e => setApimApiId(e.target.value)} placeholder="e.g. fundapis (defaults to service name)" />
        </Field>
      )}
      <Field label="">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem' }}>
          <input type="checkbox" checked={isSsoDirect} onChange={e => setIsSsoDirect(e.target.checked)} />
          Direct SSO dependency (e.g. PingFederate)
        </label>
      </Field>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!svcName || mut.isPending}>
          {mut.isPending ? 'Adding…' : 'Add Service'}
        </button>
      </div>
      {mut.isError && <p style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: 8 }}>{String(mut.error)}</p>}
    </Modal>
  )
}

// ── Add Connector Modal ───────────────────────────────────────────────────────

function AddConnectorModal({ appId, onClose }: { appId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [sourceType, setSourceType] = useState<'azure_monitor' | 'elastic' | 'byoa' | 'aks'>('azure_monitor')
  const [displayName, setDisplayName] = useState('')
  const [credType, setCredType] = useState<'env_var' | 'db_encrypted' | 'kv_reference'>('env_var')
  const [credRef, setCredRef] = useState('')
  const [credValue, setCredValue] = useState('')
  const [configJson, setConfigJson] = useState('{}')
  const [configError, setConfigError] = useState('')

  // AKS guided fields
  const [aksCluster, setAksCluster] = useState('')
  const [aksRg, setAksRg] = useState('')
  const [aksSub, setAksSub] = useState('')
  const [aksNs, setAksNs] = useState('default')
  const [aksKubeconfigPath, setAksKubeconfigPath] = useState('')
  const [aksInCluster, setAksInCluster] = useState(false)
  const [aksClientId, setAksClientId] = useState('')
  const [aksClientSecret, setAksClientSecret] = useState('')
  const [aksTenantId, setAksTenantId] = useState('')

  function validateJson(v: string) {
    try { JSON.parse(v); setConfigError(''); return true }
    catch { setConfigError('Invalid JSON'); return false }
  }

  const mut = useMutation({
    mutationFn: () => {
      if (sourceType === 'aks') {
        const config = {
          cluster_name: aksCluster.trim(),
          resource_group: aksRg.trim(),
          subscription_id: aksSub.trim(),
          default_namespace: aksNs.trim() || 'default',
          ...(aksInCluster ? { in_cluster: true } : { kube_config_path: aksKubeconfigPath.trim() || undefined }),
        }
        const cred = JSON.stringify({
          client_id: aksClientId.trim(),
          client_secret: aksClientSecret,
          tenant_id: aksTenantId.trim(),
        })
        return addConnector(appId, {
          source_type: 'aks',
          display_name: displayName,
          config_json: config,
          credential_type: 'db_encrypted',
          credential_value: cred,
        })
      }
      if (!validateJson(configJson)) return Promise.reject(new Error('Bad JSON'))
      return addConnector(appId, {
        source_type: sourceType,
        display_name: displayName,
        config_json: JSON.parse(configJson),
        credential_type: credType,
        credential_ref: credType !== 'db_encrypted' ? credRef || null : null,
        credential_value: credType === 'db_encrypted' ? credValue : undefined,
      })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  const placeholders: Record<string, string> = {
    azure_monitor: '{"workspace_id":"<guid>","apim_table":"ApiManagementGatewayLogs"}',
    elastic: '{"cluster_url":"https://elastic:9200","index_pattern_logs":"logs-*"}',
    byoa: '{"base_url":"https://api.example.com","health_endpoint":"/health"}',
  }

  return (
    <Modal title="Add Connector" onClose={onClose}>
      <Field label="Type">
        <select style={INPUT_STYLE} value={sourceType} onChange={e => setSourceType(e.target.value as typeof sourceType)}>
          <option value="azure_monitor">Azure Monitor / Log Analytics</option>
          <option value="elastic">Elasticsearch</option>
          <option value="byoa">Bring Your Own API (BYOA)</option>
          <option value="aks">AKS / Kubernetes</option>
        </select>
      </Field>
      <Field label="Display Name *">
        <input style={INPUT_STYLE} value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder={
          sourceType === 'azure_monitor' ? 'e.g. Azure Log Analytics (APIM)'
          : sourceType === 'elastic' ? 'e.g. Production Elasticsearch'
          : sourceType === 'aks' ? 'e.g. CHAD AKS Cluster'
          : 'e.g. Custom Observability API'
        } />
      </Field>

      {sourceType === 'aks' ? (
        <>
          <Field label="Cluster Name *">
            <input style={INPUT_STYLE} value={aksCluster} onChange={e => setAksCluster(e.target.value)} placeholder="e.g. azaustaekub14470dv0101" />
          </Field>
          <Field label="Resource Group *">
            <input style={INPUT_STYLE} value={aksRg} onChange={e => setAksRg(e.target.value)} placeholder="e.g. RG_14470_AUCHAD_DV01" />
          </Field>
          <Field label="Subscription ID *">
            <input style={INPUT_STYLE} value={aksSub} onChange={e => setAksSub(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </Field>
          <Field label="Default Namespace">
            <input style={INPUT_STYLE} value={aksNs} onChange={e => setAksNs(e.target.value)} placeholder="e.g. chad" />
          </Field>
          <Field label="">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem' }}>
              <input type="checkbox" checked={aksInCluster} onChange={e => setAksInCluster(e.target.checked)} />
              Running in-cluster (use pod service account, no kubeconfig needed)
            </label>
          </Field>
          {!aksInCluster && (
            <Field label="Kubeconfig Path">
              <input style={INPUT_STYLE} value={aksKubeconfigPath} onChange={e => setAksKubeconfigPath(e.target.value)} placeholder="e.g. ~/.kube/config (leave blank for default)" />
            </Field>
          )}
          <div style={{ borderTop: '1px solid var(--c-border)', margin: '14px 0 10px', paddingTop: 10, fontSize: '0.75rem', color: 'var(--c-text-muted)', fontFamily: 'var(--font-display)' }}>
            Azure Service Principal (encrypted at rest)
          </div>
          <Field label="Azure Client ID *">
            <input style={INPUT_STYLE} value={aksClientId} onChange={e => setAksClientId(e.target.value)} placeholder="Service principal client ID" />
          </Field>
          <Field label="Azure Client Secret *">
            <input type="password" style={INPUT_STYLE} value={aksClientSecret} onChange={e => setAksClientSecret(e.target.value)} placeholder="Service principal client secret" />
          </Field>
          <Field label="Azure Tenant ID *">
            <input style={INPUT_STYLE} value={aksTenantId} onChange={e => setAksTenantId(e.target.value)} placeholder="e.g. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </Field>
        </>
      ) : (
        <>
          <Field label={`Config JSON (${sourceType})`}>
            <textarea
              style={{ ...INPUT_STYLE, resize: 'vertical', minHeight: 90, borderColor: configError ? '#ef4444' : undefined }}
              value={configJson}
              onChange={e => { setConfigJson(e.target.value); setConfigError('') }}
              placeholder={placeholders[sourceType]}
              spellCheck={false}
            />
            {configError && <p style={{ color: '#ef4444', fontSize: '0.72rem', margin: '4px 0 0' }}>{configError}</p>}
          </Field>
          <Field label="Credential Type">
            <select style={INPUT_STYLE} value={credType} onChange={e => setCredType(e.target.value as typeof credType)}>
              <option value="env_var">Env Var (DefaultAzureCredential / no secret)</option>
              <option value="db_encrypted">DB Encrypted (AES-256-GCM)</option>
              <option value="kv_reference">Azure Key Vault Reference</option>
            </select>
          </Field>
          {credType === 'env_var' && (
            <Field label="Env Var Name (optional)">
              <input style={INPUT_STYLE} value={credRef} onChange={e => setCredRef(e.target.value)} placeholder="e.g. ELASTIC_API_KEY (leave blank for managed identity)" />
            </Field>
          )}
          {credType === 'db_encrypted' && (
            <Field label="Secret Value (will be AES-256 encrypted at rest)">
              <input type="password" style={INPUT_STYLE} value={credValue} onChange={e => setCredValue(e.target.value)} placeholder="Enter API key / password…" />
            </Field>
          )}
          {credType === 'kv_reference' && (
            <Field label="Key Vault Reference (vault_url|secret_name)">
              <input style={INPUT_STYLE} value={credRef} onChange={e => setCredRef(e.target.value)} placeholder="https://my-vault.vault.azure.net|my-secret" />
            </Field>
          )}
        </>
      )}

      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!displayName || mut.isPending}>
          {mut.isPending ? 'Saving…' : 'Add Connector'}
        </button>
      </div>
      {mut.isError && <p style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: 8 }}>{String(mut.error)}</p>}
    </Modal>
  )
}

// ── Add SLO Modal ─────────────────────────────────────────────────────────────

function AddSloModal({ appId, services, onClose }: { appId: string; services: ApplicationService[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [svcName, setSvcName] = useState(services[0]?.service_name ?? '')
  const [sliType, setSliType] = useState<'availability' | 'latency'>('availability')
  const [target, setTarget] = useState('99.9')
  const [window, setWindow] = useState('30')
  const [latencyMs, setLatencyMs] = useState('')

  const mut = useMutation({
    mutationFn: () => addSloConfig(appId, {
      service_name: svcName,
      sli_type: sliType,
      target_pct: parseFloat(target),
      time_window_days: parseInt(window),
      latency_threshold_ms: latencyMs ? parseInt(latencyMs) : null,
      enabled: true,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  return (
    <Modal title="Add SLO Config" onClose={onClose}>
      <Field label="Service">
        <select style={INPUT_STYLE} value={svcName} onChange={e => setSvcName(e.target.value)}>
          {services.map(s => <option key={s.service_name} value={s.service_name}>{s.display_name}</option>)}
          <option value="__all__">All services</option>
        </select>
      </Field>
      <Field label="SLI Type">
        <select style={INPUT_STYLE} value={sliType} onChange={e => setSliType(e.target.value as typeof sliType)}>
          <option value="availability">Availability (%)</option>
          <option value="latency">Latency p99 (ms)</option>
        </select>
      </Field>
      <Field label="Target %">
        <input style={INPUT_STYLE} type="number" min="0" max="100" step="0.01" value={target} onChange={e => setTarget(e.target.value)} />
      </Field>
      <Field label="Rolling Window (days)">
        <input style={INPUT_STYLE} type="number" min="1" max="90" value={window} onChange={e => setWindow(e.target.value)} />
      </Field>
      {sliType === 'latency' && (
        <Field label="Latency Threshold (ms)">
          <input style={INPUT_STYLE} type="number" min="1" value={latencyMs} onChange={e => setLatencyMs(e.target.value)} placeholder="e.g. 500" />
        </Field>
      )}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!svcName || mut.isPending}>
          {mut.isPending ? 'Saving…' : 'Add SLO'}
        </button>
      </div>
    </Modal>
  )
}

// ── Application Card ──────────────────────────────────────────────────────────

function AppCard({ app, selected, onClick }: { app: Application; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%', textAlign: 'left',
        background: selected ? 'var(--c-surface-2)' : 'var(--c-surface)',
        border: `1px solid ${selected ? 'var(--c-border-glow)' : 'var(--c-border)'}`,
        borderRadius: 10, padding: '16px 18px',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.1s',
        boxShadow: selected ? '0 0 0 2px var(--c-border-glow)22' : 'none',
      }}
    >
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.9rem', marginBottom: 4 }}>{app.name}</div>
      <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>{app.team_name || '—'} · {app.environment_default}</div>
      {app.description && (
        <div style={{ fontSize: '0.73rem', color: 'var(--c-text-faint)', lineHeight: 1.4, marginBottom: 8 }}>{app.description}</div>
      )}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {app.services && app.services.length > 0 && (
          <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>{app.services.length} svc</span>
        )}
      </div>
    </button>
  )
}

// ── Services Tab ──────────────────────────────────────────────────────────────

function ServicesTab({ app }: { app: Application }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const services = app.services ?? []

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteService(app.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.85rem' }}>{services.length} Service{services.length !== 1 ? 's' : ''}</span>
        <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => setShowAdd(true)}>+ Add Service</button>
      </div>
      {services.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', padding: '32px 0', fontSize: '0.82rem' }}>
          No services yet. Click <strong>+ Add Service</strong> to register one.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {services.map(svc => (
          <div key={svc.id} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            background: 'var(--c-bg)', border: '1px solid var(--c-border)', borderRadius: 8,
            padding: '11px 14px',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 600, marginBottom: 2 }}>{svc.display_name}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>{svc.service_name}{svc.namespace ? ` · ${svc.namespace}` : ''}</div>
            </div>
            <TierBadge tier={svc.tier} />
            <button
              onClick={() => deleteMut.mutate(svc.id)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}
              title="Remove service"
            >✕</button>
          </div>
        ))}
      </div>
      {showAdd && <AddServiceModal appId={app.id} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

// ── Connectors Tab (Inbound + Outbound) ───────────────────────────────────────

const OUTBOUND_ICONS: Record<string, string> = {
  teams_webhook: '💬',
  servicenow: '🎫',
  email: '✉️',
  pagerduty: '🚨',
  generic_http: '🌐',
}

// ── Connector builder constants ───────────────────────────────────────────────

type ConnectorAuthType = 'none' | 'bearer' | 'api_key' | 'basic' | 'oauth2'
type ConnectorType = 'teams_webhook' | 'servicenow' | 'email' | 'pagerduty' | 'generic_http'
interface ConnectorVariable { key: string; default_value: string }

const CONNECTOR_DEFAULT_ENDPOINTS: Record<string, string> = {
  teams_webhook: '',
  servicenow: '',
  email: '',
  pagerduty: 'https://events.pagerduty.com/v2/enqueue',
  generic_http: '',
}

const CONNECTOR_DEFAULT_AUTH: Record<string, ConnectorAuthType> = {
  teams_webhook: 'none',
  servicenow: 'oauth2',
  email: 'basic',
  pagerduty: 'none',
  generic_http: 'none',
}

const CONNECTOR_DEFAULT_VARS: Record<string, ConnectorVariable[]> = {
  teams_webhook: [
    { key: 'title',          default_value: 'Corvin Alert: {{service_name}}' },
    { key: 'summary',        default_value: '{{rca_summary}}' },
    { key: 'severity_color', default_value: 'FF0000' },
  ],
  servicenow: [
    { key: 'title',     default_value: 'Corvin: {{service_name}} degraded' },
    { key: 'summary',   default_value: '{{rca_summary}}' },
    { key: 'urgency',   default_value: '1' },
    { key: 'caller_id', default_value: 'corvin-bot' },
  ],
  email: [
    { key: 'to',      default_value: 'team@example.com' },
    { key: 'title',   default_value: '[Corvin] {{service_name}} alert' },
    { key: 'summary', default_value: '{{rca_summary}}' },
  ],
  pagerduty: [
    { key: 'routing_key', default_value: '' },
    { key: 'summary',     default_value: 'Corvin: {{service_name}} — {{rca_summary}}' },
    { key: 'severity',    default_value: 'critical' },
    { key: 'source',      default_value: '{{service_name}}' },
  ],
  generic_http: [
    { key: 'title',    default_value: '{{service_name}} alert' },
    { key: 'summary',  default_value: '{{rca_summary}}' },
    { key: 'severity', default_value: '{{confidence}}' },
  ],
}

const CONNECTOR_DEFAULT_PAYLOADS: Record<string, string> = {
  teams_webhook: `{
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "title": "{{title}}",
  "text": "{{summary}}",
  "themeColor": "{{severity_color}}"
}`,
  servicenow: `{
  "short_description": "{{title}}",
  "description": "{{summary}}",
  "urgency": "{{urgency}}",
  "caller_id": "{{caller_id}}"
}`,
  email: `{
  "to": ["{{to}}"],
  "subject": "{{title}}",
  "body": "{{summary}}"
}`,
  pagerduty: `{
  "routing_key": "{{routing_key}}",
  "event_action": "trigger",
  "payload": {
    "summary": "{{summary}}",
    "severity": "{{severity}}",
    "source": "{{source}}"
  }
}`,
  generic_http: `{
  "title": "{{title}}",
  "message": "{{summary}}",
  "severity": "{{severity}}"
}`,
}

const AUTH_TYPE_OPTS: { key: ConnectorAuthType; label: string }[] = [
  { key: 'none',   label: 'None' },
  { key: 'bearer', label: 'Bearer Token' },
  { key: 'api_key', label: 'API Key' },
  { key: 'oauth2', label: 'OAuth 2.0' },
  { key: 'basic',  label: 'Basic Auth' },
]

function ConnectorsTab({ app }: { app: Application }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showAddOutbound, setShowAddOutbound] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string; latency_ms: number | null }>>({})
  const connectors = app.log_sources ?? []
  const outbound = app.outbound_connectors ?? []

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteConnector(app.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  const deleteOutMut = useMutation({
    mutationFn: (id: string) => deleteOutboundConnector(app.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  const runTest = useCallback(async (srcId: string) => {
    setTestingId(srcId)
    try {
      const r = await testConnector(app.id, srcId)
      setTestResults(prev => ({ ...prev, [srcId]: r }))
      qc.invalidateQueries({ queryKey: ['application', app.id] })
    } catch (err) {
      setTestResults(prev => ({ ...prev, [srcId]: { ok: false, message: String(err), latency_ms: null } }))
    } finally {
      setTestingId(null)
    }
  }, [app.id, qc])

  return (
    <div>
      {/* ── Inbound (Data Sources) ── */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-text-muted)' }}>⬇ Inbound — Data Sources ({connectors.length})</span>
          <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => setShowAdd(true)}>+ Add Source</button>
        </div>
        {connectors.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', padding: '24px 0', fontSize: '0.82rem' }}>
            No inbound connectors. Add one to pull logs & metrics.
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {connectors.map(src => {
            const localResult = testResults[src.id]
            const ok = localResult?.ok ?? (src.test_status === 'ok' ? true : src.test_status === 'error' ? false : null)
            const latency = localResult?.latency_ms ?? null
            const isTesting = testingId === src.id
            return (
              <div key={src.id} style={{
                background: 'var(--c-bg)', border: '1px solid var(--c-border)', borderRadius: 10, padding: '14px 16px',
              }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <span style={{ fontSize: '1.2rem', lineHeight: 1, marginTop: 2 }}>{SOURCE_ICONS[src.source_type] ?? '◈'}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.85rem' }}>{src.display_name}</span>
                      <StatusDot ok={ok} tested={ok !== null} />
                      {latency !== null && (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>{latency.toFixed(0)}ms</span>
                      )}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                      {src.source_type} · {src.credential_type}
                    </div>
                    {(localResult?.message || src.test_message) && (
                      <div style={{
                        fontSize: '0.7rem', fontFamily: 'var(--font-mono)',
                        color: ok ? '#22c55e' : '#ef4444',
                        marginTop: 2,
                      }}>
                        {localResult?.message ?? src.test_message}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '0.72rem', padding: '4px 10px' }}
                      onClick={() => runTest(src.id)}
                      disabled={isTesting}
                    >
                      {isTesting ? 'Testing…' : 'Test'}
                    </button>
                    <button
                      onClick={() => deleteMut.mutate(src.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}
                      title="Remove connector"
                    >✕</button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Outbound (Notifications / Integrations) ── */}
      <div style={{ borderTop: '1px solid var(--c-border)', paddingTop: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-text-muted)' }}>⬆ Outbound — Notifications & Integrations ({outbound.length})</span>
          <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => setShowAddOutbound(true)}>+ Add Destination</button>
        </div>
        {outbound.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', padding: '24px 0', fontSize: '0.82rem' }}>
            No outbound connectors. Add a Teams webhook, ServiceNow, or email destination.
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {outbound.map(conn => {
            const cfg = conn.config_json
            const endpoint = cfg.endpoint || cfg.webhook_url || ''
            const authType = cfg.auth?.type ?? 'none'
            const varCount = Array.isArray(cfg.variables) ? cfg.variables.length : 0
            return (
              <div key={conn.id} style={{
                background: 'var(--c-bg)', border: '1px solid var(--c-border)', borderRadius: 10, padding: '14px 16px',
              }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <span style={{ fontSize: '1.2rem', lineHeight: 1, marginTop: 2 }}>{OUTBOUND_ICONS[conn.connector_type] ?? '📤'}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.85rem', marginBottom: 3 }}>{conn.display_name}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 4, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span>{conn.connector_type.replace(/_/g, ' ')}</span>
                      {authType !== 'none' && <span style={{ color: 'var(--c-accent)', background: 'color-mix(in srgb, var(--c-accent) 12%, transparent)', padding: '1px 6px', borderRadius: 4 }}>{authType.replace('_', ' ')}</span>}
                      {varCount > 0 && <span style={{ color: 'var(--c-text-muted)' }}>{varCount} var{varCount !== 1 ? 's' : ''}</span>}
                    </div>
                    {endpoint && (
                      <div style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 380 }}>
                        {endpoint}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => deleteOutMut.mutate(conn.id)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4, flexShrink: 0 }}
                    title="Remove outbound connector"
                  >✕</button>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {showAdd && <AddConnectorModal appId={app.id} onClose={() => setShowAdd(false)} />}
      {showAddOutbound && <AddOutboundModal appId={app.id} onClose={() => setShowAddOutbound(false)} />}
    </div>
  )
}

// ── Add Outbound Modal ────────────────────────────────────────────────────────

function AddOutboundModal({ appId, onClose }: { appId: string; onClose: () => void }) {
  const qc = useQueryClient()

  // ── Basic ──────────────────────────────────────────────────────────────────
  const [connType, setConnType] = useState<ConnectorType>('teams_webhook')
  const [displayName, setDisplayName] = useState('')

  // ── Endpoint ───────────────────────────────────────────────────────────────
  const [endpoint, setEndpoint] = useState(CONNECTOR_DEFAULT_ENDPOINTS['teams_webhook'])
  const [httpMethod, setHttpMethod] = useState('POST')
  const [snTable, setSnTable] = useState('incident')
  const [emailPort, setEmailPort] = useState('587')
  const [emailFrom, setEmailFrom] = useState('')

  // ── Auth ───────────────────────────────────────────────────────────────────
  const [authType, setAuthType] = useState<ConnectorAuthType>(CONNECTOR_DEFAULT_AUTH['teams_webhook'])
  const [bearerToken, setBearerToken] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiKeyHeader, setApiKeyHeader] = useState('X-API-Key')
  const [authUser, setAuthUser] = useState('')
  const [authPass, setAuthPass] = useState('')
  const [oauthTokenUrl, setOauthTokenUrl] = useState('')
  const [oauthClientId, setOauthClientId] = useState('')
  const [oauthClientSecret, setOauthClientSecret] = useState('')
  const [oauthScopes, setOauthScopes] = useState('')

  // ── Variables ──────────────────────────────────────────────────────────────
  const [variables, setVariables] = useState<ConnectorVariable[]>(() => CONNECTOR_DEFAULT_VARS['teams_webhook'].map(v => ({ ...v })))

  // ── Payload template ───────────────────────────────────────────────────────
  const [payloadTemplate, setPayloadTemplate] = useState(CONNECTOR_DEFAULT_PAYLOADS['teams_webhook'])

  const handleTypeChange = (t: ConnectorType) => {
    setConnType(t)
    setEndpoint(CONNECTOR_DEFAULT_ENDPOINTS[t] || '')
    setAuthType(CONNECTOR_DEFAULT_AUTH[t] || 'none')
    setVariables((CONNECTOR_DEFAULT_VARS[t] || []).map(v => ({ ...v })))
    setPayloadTemplate(CONNECTOR_DEFAULT_PAYLOADS[t] || '')
    setHttpMethod('POST'); setSnTable('incident'); setEmailPort('587'); setEmailFrom('')
    setBearerToken(''); setApiKey(''); setApiKeyHeader('X-API-Key')
    setAuthUser(''); setAuthPass(''); setOauthTokenUrl('')
    setOauthClientId(''); setOauthClientSecret(''); setOauthScopes('')
  }

  const buildConfig = () => {
    const auth: Record<string, string> = { type: authType }
    if (authType === 'bearer') auth.bearer_token = bearerToken
    if (authType === 'api_key') { auth.api_key = apiKey; auth.api_key_header = apiKeyHeader }
    if (authType === 'basic') { auth.username = authUser; auth.password = authPass }
    if (authType === 'oauth2') {
      auth.token_url = oauthTokenUrl
      auth.client_id = oauthClientId
      auth.client_secret = oauthClientSecret
      auth.scopes = oauthScopes
    }
    const endpoint_fields: Record<string, string> = {}
    if (connType === 'servicenow') endpoint_fields.table = snTable
    if (connType === 'email') { endpoint_fields.port = emailPort; endpoint_fields.from = emailFrom }
    if (connType === 'generic_http') endpoint_fields.http_method = httpMethod
    return { endpoint, endpoint_fields, auth, variables, payload_template: payloadTemplate }
  }

  const mut = useMutation({
    mutationFn: () => addOutboundConnector(appId, {
      connector_type: connType,
      display_name: displayName,
      config_json: buildConfig() as never,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  // ── Shared style helpers ───────────────────────────────────────────────────
  const inp = { display: 'block', width: '100%', marginTop: 4, padding: '7px 10px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-bg)', color: 'var(--c-text)', fontSize: '0.8rem', boxSizing: 'border-box' as const }
  const monoInp = { ...inp, fontFamily: 'var(--font-mono)' as string }
  const lbl = { fontSize: '0.75rem', fontFamily: 'var(--font-display)', fontWeight: 600, display: 'block' as const }
  const sectionHdr = { fontSize: '0.68rem', fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--c-text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', paddingBottom: 8, borderBottom: '1px solid var(--c-border)', marginBottom: 12 }

  const endpointLabel = connType === 'servicenow' ? 'Instance URL' : connType === 'teams_webhook' ? 'Webhook URL' : connType === 'pagerduty' ? 'Events API URL' : connType === 'email' ? 'SMTP Host / API Endpoint' : 'Endpoint URL'
  const endpointPlaceholder = connType === 'servicenow' ? 'https://myinstance.service-now.com' : connType === 'pagerduty' ? 'https://events.pagerduty.com/v2/enqueue' : connType === 'email' ? 'smtp.example.com' : 'https://...'

  return (
    <Modal title="Add Outbound Connector" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, padding: '4px 0 8px', maxHeight: '72vh', overflowY: 'auto', paddingRight: 2 }}>

        {/* ── Type + Name ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={lbl}>
            Type
            <select value={connType} onChange={e => handleTypeChange(e.target.value as ConnectorType)} style={{ ...inp, marginTop: 4 }}>
              <option value="teams_webhook">💬  Teams Webhook</option>
              <option value="servicenow">🎫  ServiceNow</option>
              <option value="email">✉️  Email / SMTP</option>
              <option value="pagerduty">🚨  PagerDuty</option>
              <option value="generic_http">🌐  Generic HTTP</option>
            </select>
          </label>
          <label style={lbl}>
            Display Name
            <input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="e.g. CHAD Platform Alerts" style={{ ...inp, marginTop: 4 }} />
          </label>
        </div>

        {/* ── Endpoint ── */}
        <div>
          <div style={sectionHdr}>Endpoint</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {connType === 'generic_http' && (
              <label style={lbl}>
                HTTP Method
                <select value={httpMethod} onChange={e => setHttpMethod(e.target.value)} style={{ ...inp, marginTop: 4 }}>
                  <option>POST</option><option>PUT</option><option>PATCH</option><option>GET</option>
                </select>
              </label>
            )}
            {connType === 'email' ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px', gap: 10 }}>
                <label style={lbl}>
                  {endpointLabel}
                  <input value={endpoint} onChange={e => setEndpoint(e.target.value)} placeholder={endpointPlaceholder} style={monoInp} />
                </label>
                <label style={lbl}>
                  Port
                  <input value={emailPort} onChange={e => setEmailPort(e.target.value)} placeholder="587" style={monoInp} />
                </label>
              </div>
            ) : (
              <label style={lbl}>
                {endpointLabel}
                <input value={endpoint} onChange={e => setEndpoint(e.target.value)} placeholder={endpointPlaceholder} style={monoInp} />
              </label>
            )}
            {connType === 'servicenow' && (
              <label style={lbl}>
                Table
                <input value={snTable} onChange={e => setSnTable(e.target.value)} placeholder="incident" style={monoInp} />
              </label>
            )}
            {connType === 'email' && (
              <label style={lbl}>
                From Address
                <input value={emailFrom} onChange={e => setEmailFrom(e.target.value)} placeholder="corvin@yourorg.com" style={inp} />
              </label>
            )}
          </div>
        </div>

        {/* ── Authentication ── */}
        <div>
          <div style={sectionHdr}>Authentication</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
            {AUTH_TYPE_OPTS.map(opt => (
              <button key={opt.key} onClick={() => setAuthType(opt.key)} style={{
                padding: '4px 12px', borderRadius: 20, fontSize: '0.72rem', fontWeight: 600,
                cursor: 'pointer', transition: 'all 0.15s',
                border: authType === opt.key ? '1.5px solid var(--c-accent)' : '1px solid var(--c-border)',
                background: authType === opt.key ? 'var(--c-accent)' : 'var(--c-bg)',
                color: authType === opt.key ? '#fff' : 'var(--c-text-muted)',
              }}>{opt.label}</button>
            ))}
          </div>
          {authType === 'bearer' && (
            <label style={lbl}>
              Bearer Token
              <input type="password" value={bearerToken} onChange={e => setBearerToken(e.target.value)} placeholder="eyJ..." style={monoInp} />
            </label>
          )}
          {authType === 'api_key' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 160px', gap: 10 }}>
              <label style={lbl}>
                API Key
                <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." style={monoInp} />
              </label>
              <label style={lbl}>
                Header Name
                <input value={apiKeyHeader} onChange={e => setApiKeyHeader(e.target.value)} placeholder="X-API-Key" style={monoInp} />
              </label>
            </div>
          )}
          {authType === 'basic' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label style={lbl}>
                Username
                <input value={authUser} onChange={e => setAuthUser(e.target.value)} placeholder="admin" style={inp} />
              </label>
              <label style={lbl}>
                Password
                <input type="password" value={authPass} onChange={e => setAuthPass(e.target.value)} placeholder="••••••" style={inp} />
              </label>
            </div>
          )}
          {authType === 'oauth2' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <label style={lbl}>
                Token URL
                <input value={oauthTokenUrl} onChange={e => setOauthTokenUrl(e.target.value)} placeholder="https://your-idp.com/oauth/token" style={monoInp} />
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <label style={lbl}>
                  Client ID
                  <input value={oauthClientId} onChange={e => setOauthClientId(e.target.value)} placeholder="client_id" style={monoInp} />
                </label>
                <label style={lbl}>
                  Client Secret
                  <input type="password" value={oauthClientSecret} onChange={e => setOauthClientSecret(e.target.value)} placeholder="••••••" style={monoInp} />
                </label>
              </div>
              <label style={lbl}>
                Scopes <span style={{ fontWeight: 400, color: 'var(--c-text-faint)' }}>(space-separated)</span>
                <input value={oauthScopes} onChange={e => setOauthScopes(e.target.value)} placeholder="read write" style={monoInp} />
              </label>
            </div>
          )}
        </div>

        {/* ── Variables ── */}
        <div>
          <div style={{ ...sectionHdr, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Variables</span>
            <button onClick={() => setVariables(v => [...v, { key: '', default_value: '' }])}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-accent)', fontSize: '0.72rem', fontWeight: 700, padding: 0, letterSpacing: 0, textTransform: 'none' }}>
              + Add Variable
            </button>
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', marginBottom: 10, lineHeight: 1.5 }}>
            Use <code style={{ fontFamily: 'var(--font-mono)', background: 'var(--c-bg-elevated)', padding: '1px 5px', borderRadius: 3 }}>{'{{key}}'}</code> in the payload template.
            Built-in vars: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-muted)' }}>{'{{service_name}} {{rca_summary}} {{confidence}} {{environment}} {{request_id}}'}</code>
          </div>
          {variables.length === 0 ? (
            <div style={{ fontSize: '0.75rem', color: 'var(--c-text-faint)', textAlign: 'center', padding: '10px 0' }}>
              No variables —{' '}
              <button onClick={() => setVariables((CONNECTOR_DEFAULT_VARS[connType] || []).map(v => ({ ...v })))}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-accent)', fontSize: '0.75rem', padding: 0 }}>
                load defaults for {connType.replace(/_/g, ' ')}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 24px', gap: 6, marginBottom: 2 }}>
                <span style={{ fontSize: '0.63rem', fontWeight: 700, color: 'var(--c-text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Key</span>
                <span style={{ fontSize: '0.63rem', fontWeight: 700, color: 'var(--c-text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Default Value</span>
                <span />
              </div>
              {variables.map((v, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '140px 1fr 24px', gap: 6, alignItems: 'center' }}>
                  <input value={v.key} onChange={e => setVariables(vs => vs.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
                    placeholder="key" style={{ ...monoInp, marginTop: 0, fontSize: '0.75rem' }} />
                  <input value={v.default_value} onChange={e => setVariables(vs => vs.map((x, j) => j === i ? { ...x, default_value: e.target.value } : x))}
                    placeholder="value or {{builtin}}" style={{ ...monoInp, marginTop: 0, fontSize: '0.75rem' }} />
                  <button onClick={() => setVariables(vs => vs.filter((_, j) => j !== i))}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 0, lineHeight: 1 }}>✕</button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Payload Template ── */}
        <div>
          <div style={{ ...sectionHdr, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Payload Template</span>
            <button onClick={() => setPayloadTemplate(CONNECTOR_DEFAULT_PAYLOADS[connType] || '')}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-accent)', fontSize: '0.72rem', fontWeight: 700, padding: 0, letterSpacing: 0, textTransform: 'none' }}>
              Reset to default
            </button>
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', marginBottom: 8 }}>
            JSON body sent with every outbound request. Interpolate with <code style={{ fontFamily: 'var(--font-mono)', background: 'var(--c-bg-elevated)', padding: '1px 5px', borderRadius: 3 }}>{'{{key}}'}</code>.
          </div>
          <textarea value={payloadTemplate} onChange={e => setPayloadTemplate(e.target.value)}
            rows={8} spellCheck={false}
            style={{ ...monoInp, marginTop: 0, resize: 'vertical', fontSize: '0.73rem', lineHeight: 1.5 }} />
        </div>

        {/* ── Save ── */}
        {mut.isError && (
          <div style={{ fontSize: '0.75rem', color: '#ef4444', padding: '6px 10px', background: '#ef444414', borderRadius: 6 }}>
            {String((mut.error as Error)?.message ?? 'Save failed')}
          </div>
        )}
        <button className="btn-primary" onClick={() => mut.mutate()}
          disabled={!displayName.trim() || !endpoint.trim() || mut.isPending}
          style={{ marginTop: 4 }}>
          {mut.isPending ? 'Saving…' : 'Save Connector'}
        </button>
      </div>
    </Modal>
  )
}

// ── Notifications Tab ─────────────────────────────────────────────────────────

const METHOD_ICONS: Record<string, string> = { email: '✉️', phone: '📱', teams: '💬' }

function NotificationsTab({ app }: { app: Application }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const contacts = app.notification_contacts ?? []

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteNotificationContact(app.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.85rem' }}>{contacts.length} Contact{contacts.length !== 1 ? 's' : ''}</span>
        <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => setShowAdd(true)}>+ Add Contact</button>
      </div>
      {contacts.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', padding: '32px 0', fontSize: '0.82rem' }}>
          No notification contacts. Add people or channels to alert on incidents.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {contacts.map(c => (
          <div key={c.id} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            background: 'var(--c-bg)', border: '1px solid var(--c-border)', borderRadius: 8,
            padding: '12px 14px',
            opacity: c.is_active ? 1 : 0.5,
          }}>
            <span style={{ fontSize: '1.1rem' }}>{METHOD_ICONS[c.method] ?? '📣'}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.82rem' }}>{c.contact_name}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                {c.method} · {c.value} · <span style={{ color: c.priority_filter === 'all' ? '#22c55e' : '#f59e0b' }}>{c.priority_filter.replace('_', ' ')}</span>
              </div>
            </div>
            <button
              onClick={() => deleteMut.mutate(c.id)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}
              title="Remove contact"
            >✕</button>
          </div>
        ))}
      </div>
      {showAdd && <AddContactModal appId={app.id} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

// ── Add Contact Modal ─────────────────────────────────────────────────────────

function AddContactModal({ appId, onClose }: { appId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [method, setMethod] = useState<string>('email')
  const [value, setValue] = useState('')
  const [priority, setPriority] = useState<string>('all')

  const mut = useMutation({
    mutationFn: () => addNotificationContact(appId, {
      contact_name: name,
      method: method as 'email' | 'phone' | 'teams',
      value,
      priority_filter: priority as 'all' | 'p1_only' | 'p1_p2',
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  return (
    <Modal title="Add Notification Contact" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '12px 0' }}>
        <label style={{ fontSize: '0.78rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
          Name
          <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Jane Smith" style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-bg)', color: 'var(--c-text)', fontSize: '0.8rem' }} />
        </label>
        <label style={{ fontSize: '0.78rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
          Method
          <select value={method} onChange={e => setMethod(e.target.value)} style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-bg)', color: 'var(--c-text)', fontSize: '0.8rem' }}>
            <option value="email">Email</option>
            <option value="phone">Phone / SMS</option>
            <option value="teams">Teams Channel</option>
          </select>
        </label>
        <label style={{ fontSize: '0.78rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
          {method === 'email' ? 'Email Address' : method === 'phone' ? 'Phone Number' : 'Teams Channel Webhook'}
          <input value={value} onChange={e => setValue(e.target.value)} placeholder={method === 'email' ? 'user@company.com' : method === 'phone' ? '+1 555-0100' : 'https://...'} style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-bg)', color: 'var(--c-text)', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }} />
        </label>
        <label style={{ fontSize: '0.78rem', fontFamily: 'var(--font-display)', fontWeight: 600 }}>
          Alert On
          <select value={priority} onChange={e => setPriority(e.target.value)} style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-bg)', color: 'var(--c-text)', fontSize: '0.8rem' }}>
            <option value="all">All Incidents</option>
            <option value="p1_only">P1 Only</option>
            <option value="p1_p2">P1 & P2</option>
          </select>
        </label>
        <button className="btn-primary" style={{ marginTop: 8 }} onClick={() => mut.mutate()} disabled={!name || !value || mut.isPending}>
          {mut.isPending ? 'Saving…' : 'Add Contact'}
        </button>
      </div>
    </Modal>
  )
}

// ── SLO Tab ───────────────────────────────────────────────────────────────────

function SloTab({ app }: { app: Application }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const slos = app.slo_configs ?? []

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSloConfig(app.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateSloConfig(app.id, id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.85rem' }}>{slos.length} SLO{slos.length !== 1 ? 's' : ''}</span>
        <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => setShowAdd(true)}>+ Add SLO</button>
      </div>
      {slos.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--c-text-faint)', padding: '32px 0', fontSize: '0.82rem' }}>
          No SLO configurations. Define targets to enable error budget tracking.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {slos.map(slo => (
          <div key={slo.id} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            background: 'var(--c-bg)', border: '1px solid var(--c-border)', borderRadius: 8,
            padding: '12px 14px',
            opacity: slo.enabled ? 1 : 0.5,
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 600 }}>{slo.service_name}</span>
                <span style={{
                  fontSize: '0.62rem', padding: '1px 6px', borderRadius: 4,
                  background: 'var(--c-surface)', border: '1px solid var(--c-border)',
                  color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)',
                }}>{SLI_LABELS[slo.sli_type] ?? slo.sli_type}</span>
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>
                Target: <strong style={{ color: 'var(--c-text)' }}>{slo.target_pct}%</strong>
                {' · '}{slo.time_window_days}d rolling
                {slo.latency_threshold_ms ? ` · ≤${slo.latency_threshold_ms}ms` : ''}
              </div>
            </div>
            {/* Toggle */}
            <button
              onClick={() => toggleMut.mutate({ id: slo.id, enabled: !slo.enabled })}
              style={{
                width: 36, height: 20, borderRadius: 10,
                background: slo.enabled ? 'var(--c-border-glow)' : 'var(--c-border)',
                border: 'none', cursor: 'pointer', position: 'relative',
                transition: 'background 0.2s',
              }}
              title={slo.enabled ? 'Disable SLO' : 'Enable SLO'}
            >
              <span style={{
                position: 'absolute', top: 2, left: slo.enabled ? 18 : 2, width: 16, height: 16,
                borderRadius: '50%', background: 'white', transition: 'left 0.2s',
              }} />
            </button>
            <button
              onClick={() => deleteMut.mutate(slo.id)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}
              title="Remove SLO"
            >✕</button>
          </div>
        ))}
      </div>
      {showAdd && <AddSloModal appId={app.id} services={app.services ?? []} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

// ── Application Detail Panel ──────────────────────────────────────────────────

type Tab = 'services' | 'connectors' | 'notifications' | 'slo'

function AppDetail({ appId }: { appId: string }) {
  const [tab, setTab] = useState<Tab>('services')
  const { data: app, isLoading, isError } = useQuery({
    queryKey: ['application', appId],
    queryFn: () => getApplication(appId),
  })

  if (isLoading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--c-text-faint)', fontSize: '0.85rem' }}>
      Loading…
    </div>
  )
  if (isError || !app) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ef4444', fontSize: '0.85rem' }}>
      Failed to load application
    </div>
  )

  const TABS: { key: Tab; label: string }[] = [
    { key: 'services', label: `Services (${app.services?.length ?? 0})` },
    { key: 'connectors', label: `Connectors (${(app.log_sources?.length ?? 0) + (app.outbound_connectors?.length ?? 0)})` },
    { key: 'notifications', label: `Notifications (${app.notification_contacts?.length ?? 0})` },
    { key: 'slo', label: `SLO (${app.slo_configs?.length ?? 0})` },
  ]

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 12, padding: '20px 24px' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.25rem', marginBottom: 4 }}>{app.name}</div>
        <div style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
          {app.team_name || 'No team'} · <span style={{ fontFamily: 'var(--font-mono)' }}>{app.environment_default}</span>
        </div>
        {app.description && (
          <div style={{ fontSize: '0.8rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>{app.description}</div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--c-border)' }}>
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                flex: 1, padding: '12px 16px',
                background: tab === t.key ? 'var(--c-surface-2)' : 'transparent',
                border: 'none', borderBottom: tab === t.key ? '2px solid var(--c-border-glow)' : '2px solid transparent',
                color: tab === t.key ? 'var(--c-text)' : 'var(--c-text-muted)',
                fontFamily: 'var(--font-display)', fontWeight: tab === t.key ? 700 : 500,
                fontSize: '0.78rem', cursor: 'pointer',
                transition: 'color 0.15s, background 0.1s',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ padding: 20 }}>
          {tab === 'services' && <ServicesTab app={app} />}
          {tab === 'connectors' && <ConnectorsTab app={app} />}
          {tab === 'notifications' && <NotificationsTab app={app} />}
          {tab === 'slo' && <SloTab app={app} />}
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ApplicationsPage() {
  const { id } = useParams<{ id?: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [migrating, setMigrating] = useState(false)
  const [migrateResult, setMigrateResult] = useState<string | null>(null)

  const { data: apps = [], isLoading, isError } = useQuery({
    queryKey: ['applications'],
    queryFn: listApplications,
  })

  const selectedId = id ?? (apps[0]?.id ?? null)

  async function handleMigrate() {
    setMigrating(true)
    setMigrateResult(null)
    try {
      const r = await migrateFromYaml()
      setMigrateResult(r.status === 'skipped' ? `Skipped: ${r.reason}` : `Migrated: ${r.applications_created ?? 1} app, ${r.services_created ?? 0} services`)
      qc.invalidateQueries({ queryKey: ['applications'] })
    } catch (err) {
      setMigrateResult(`Error: ${String(err)}`)
    } finally {
      setMigrating(false)
    }
  }

  return (
    <Layout>
      <div style={{ maxWidth: 1280, margin: '0 auto', padding: '28px 24px' }}>
        {/* Page header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.6rem', margin: 0 }}>Applications</h1>
            <p style={{ color: 'var(--c-text-muted)', fontSize: '0.82rem', margin: '4px 0 0' }}>
              Register services, configure connectors, and define SLO targets
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {migrateResult && (
              <span style={{ fontSize: '0.72rem', color: migrateResult.startsWith('Error') ? '#ef4444' : '#22c55e', fontFamily: 'var(--font-mono)' }}>
                {migrateResult}
              </span>
            )}
            <button
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '6px 14px' }}
              onClick={handleMigrate}
              disabled={migrating}
              title="One-time seed from YAML config files"
            >
              {migrating ? 'Migrating…' : '⟳ Migrate from YAML'}
            </button>
            <button className="btn-primary" style={{ fontSize: '0.8rem', padding: '7px 16px' }} onClick={() => setShowCreate(true)}>
              + New Application
            </button>
          </div>
        </div>

        {isError && (
          <div style={{ background: '#ef444422', border: '1px solid #ef4444', borderRadius: 8, padding: '12px 16px', marginBottom: 20, fontSize: '0.82rem', color: '#ef4444' }}>
            Failed to load applications. Ensure the API is running at localhost:8000.
          </div>
        )}

        <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
          {/* Left: App list */}
          <div style={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {isLoading && (
              <div style={{ color: 'var(--c-text-faint)', fontSize: '0.82rem', padding: 16 }}>Loading…</div>
            )}
            {!isLoading && apps.length === 0 && (
              <div style={{
                background: 'var(--c-surface)', border: '1px dashed var(--c-border)', borderRadius: 10,
                padding: 24, textAlign: 'center', color: 'var(--c-text-faint)', fontSize: '0.8rem',
              }}>
                No applications yet.<br />
                <button className="btn-primary" style={{ marginTop: 12, fontSize: '0.75rem' }} onClick={() => setShowCreate(true)}>
                  Create first app
                </button>
              </div>
            )}
            {apps.map(app => (
              <AppCard
                key={app.id}
                app={app}
                selected={app.id === selectedId}
                onClick={() => navigate(`/applications/${app.id}`)}
              />
            ))}
          </div>

          {/* Right: Detail */}
          {selectedId && apps.length > 0 && (
            <AppDetail key={selectedId} appId={selectedId} />
          )}
        </div>
      </div>

      {showCreate && <CreateAppModal onClose={() => setShowCreate(false)} />}
    </Layout>
  )
}
