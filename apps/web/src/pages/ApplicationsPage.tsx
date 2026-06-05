import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Layout from '../components/Layout'
import { TopologyRadar } from '../components/TopologyRadar'
import {
  listApplications,
  getApplication,
  createApplication,
  deleteApplication,
  addService,
  updateService,
  deleteService,
  addConnector,
  updateConnector,
  deleteConnector,
  testConnector,
  addSloConfig,
  updateSloConfig,
  deleteSloConfig,
  addNotificationContact,
  deleteNotificationContact,
  addOutboundConnector,
  updateOutboundConnector,
  testOutboundConnector,
  deleteOutboundConnector,
  bootstrapOutboundConnectors,
  migrateFromYaml,
  listSimulatorPresets,
  createSimulatorPreset,
  updateSimulatorPreset,
  deleteSimulatorPreset,
  listEnvironments,
  createEnvironment,
  updateEnvironment,
  deleteEnvironment,
  listKnowledge,
  createKnowledge,
  updateKnowledge,
  deleteKnowledge,
  listRunbooks,
  createRunbook,
  updateRunbook,
  deleteRunbook,
  type Application,
  type LogSource,
  type ApplicationService,
  type OutboundConnector,
  type SimulatorPreset,
  type ApplicationEnvironment,
  type KnowledgeEntry,
  type RunbookEntry,
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

const AZURE_ROLE_LABELS: Record<string, string> = {
  apim_logs: 'APIM Logs',
  container_insights: 'Container Insights',
  azure_activity: 'Azure Activity',
}

const SLI_LABELS: Record<string, string> = {
  availability: 'Availability',
  latency: 'Latency p99',
}

function describeCredentialMode(source: LogSource) {
  if (source.source_type === 'azure_monitor' && !source.credential_ref) {
    return 'default_azure_credential'
  }
  return source.credential_type
}

function describeConnectorConfig(source: LogSource) {
  const cfg = source.config_json as Record<string, unknown>
  const cfgNamespaces = Array.isArray(cfg.namespaces)
    ? cfg.namespaces.map(v => String(v)).filter(Boolean)
    : []
  if (source.source_type === 'azure_monitor') {
    const parts: string[] = []
    if (typeof cfg.connector_role === 'string' && cfg.connector_role) parts.push(AZURE_ROLE_LABELS[cfg.connector_role] ?? cfg.connector_role)
    if (typeof cfg.workspace_id === 'string' && cfg.workspace_id) parts.push(`ws:${cfg.workspace_id}`)
    if (typeof cfg.apim_table === 'string' && cfg.apim_table) parts.push(`table:${cfg.apim_table}`)
    if (typeof cfg.activity_table === 'string' && cfg.activity_table) parts.push(`activity:${cfg.activity_table}`)
    if (typeof cfg.max_events === 'number') parts.push(`max:${cfg.max_events}`)
    if (typeof cfg.cluster_name === 'string' && cfg.cluster_name) parts.push(`aks:${cfg.cluster_name}`)
    if (cfgNamespaces.length > 0) parts.push(`ns:${cfgNamespaces.join(',')}`)
    else if (typeof cfg.default_namespace === 'string' && cfg.default_namespace) parts.push(`ns:${cfg.default_namespace}`)
    return parts.join(' · ')
  }
  if (source.source_type === 'aks') {
    const parts: string[] = []
    if (typeof cfg.cluster_name === 'string' && cfg.cluster_name) parts.push(`aks:${cfg.cluster_name}`)
    if (typeof cfg.resource_group === 'string' && cfg.resource_group) parts.push(`rg:${cfg.resource_group}`)
    if (cfgNamespaces.length > 0) parts.push(`ns:${cfgNamespaces.join(',')}`)
    else if (typeof cfg.default_namespace === 'string' && cfg.default_namespace) parts.push(`ns:${cfg.default_namespace}`)
    return parts.join(' · ')
  }
  return ''
}

function parseNamespacesInput(raw: string): string[] {
  const values = raw
    .split(',')
    .map(v => v.trim())
    .filter(Boolean)
  return values.length > 0 ? Array.from(new Set(values.map(v => v.toLowerCase()))).map(
    lower => values.find(v => v.toLowerCase() === lower) as string,
  ) : ['default']
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
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      padding: 24,
      overflowY: 'auto',
    }} onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--c-surface)',
          border: '1px solid var(--c-border)',
          borderRadius: 12,
          padding: 28,
          width: '100%',
          maxWidth: 760,
          maxHeight: 'calc(100vh - 48px)',
          overflowY: 'auto',
          margin: '0 auto',
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
  const [env, setEnv] = useState('dev')

  const mut = useMutation({
    mutationFn: () => createApplication({ name, team_name: team, description: desc, environment_default: env }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['applications'] }); onClose() },
  })

  return (
    <Modal title="New Application" onClose={onClose}>
      <Field label="Name *">
        <input style={INPUT_STYLE} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Payments Platform" />
      </Field>
      <Field label="Team">
        <input style={INPUT_STYLE} value={team} onChange={e => setTeam(e.target.value)} placeholder="e.g. Platform Engineering" />
      </Field>
      <Field label="Default Environment">
        <input style={INPUT_STYLE} value={env} onChange={e => setEnv(e.target.value)} placeholder="e.g. dev, staging, production" />
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
  // Git config
  const [showGit, setShowGit] = useState(false)
  const [gitProvider, setGitProvider] = useState<string>('azure_devops')
  const [gitRepoUrl, setGitRepoUrl] = useState('')
  const [gitBranch, setGitBranch] = useState('')
  const [gitToken, setGitToken] = useState('')

  const mut = useMutation({
    mutationFn: () => {
      const metadata: Record<string, unknown> = {}
      if (apimGateway) {
        metadata.apim_routes_through_gateway = true
        if (apimApiId.trim()) metadata.apim_api_id = apimApiId.trim()
      }
      if (isSsoDirect) metadata.is_sso_direct = true
      const payload: Record<string, unknown> = {
        service_name: svcName,
        display_name: displayName || svcName,
        tier,
        namespace: ns || null,
        k8s_app_label: k8sLabel.trim() || null,
        metadata_json: metadata,
      }
      if (showGit && gitRepoUrl.trim()) {
        payload.git_provider = gitProvider
        payload.git_repo_url = gitRepoUrl.trim()
        payload.git_branch = gitBranch.trim() || null
        if (gitToken.trim()) payload.git_token = gitToken.trim()
      }
      return addService(appId, payload as any)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  return (
    <Modal title="Add Service" onClose={onClose}>
      <Field label="Service Name *">
        <input style={INPUT_STYLE} value={svcName} onChange={e => setSvcName(e.target.value)} placeholder="e.g. payments-api" />
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
        <input style={INPUT_STYLE} value={ns} onChange={e => setNs(e.target.value)} placeholder="e.g. default" />
      </Field>
      <Field label="K8s App Label">
        <input style={INPUT_STYLE} value={k8sLabel} onChange={e => setK8sLabel(e.target.value)} placeholder="e.g. payments-api (deployment app label in cluster)" />
      </Field>
      <Field label="">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem' }}>
          <input type="checkbox" checked={apimGateway} onChange={e => setApimGateway(e.target.checked)} />
          Routes via APIM Gateway
        </label>
      </Field>
      {apimGateway && (
        <Field label="APIM API ID">
          <input style={INPUT_STYLE} value={apimApiId} onChange={e => setApimApiId(e.target.value)} placeholder="e.g. payments-api (defaults to service name)" />
        </Field>
      )}
      <Field label="">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem' }}>
          <input type="checkbox" checked={isSsoDirect} onChange={e => setIsSsoDirect(e.target.checked)} />
          Direct SSO dependency (e.g. PingFederate)
        </label>
      </Field>
      {/* ── Git Repository (optional) ── */}
      <div style={{ marginTop: 12, borderTop: '1px solid var(--c-border)', paddingTop: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600 }}>
          <input type="checkbox" checked={showGit} onChange={e => setShowGit(e.target.checked)} />
          🔗 Configure Git Repository
        </label>
        {showGit && (
          <div style={{ marginTop: 10 }}>
            <Field label="Provider">
              <select style={INPUT_STYLE} value={gitProvider} onChange={e => setGitProvider(e.target.value)}>
                <option value="azure_devops">Azure DevOps</option>
                <option value="github">GitHub</option>
              </select>
            </Field>
            <Field label="Repo URL *">
              <input style={INPUT_STYLE} value={gitRepoUrl} onChange={e => setGitRepoUrl(e.target.value)} placeholder="https://dev.azure.com/org/project/_git/repo" />
            </Field>
            <Field label="Branch">
              <input style={INPUT_STYLE} value={gitBranch} onChange={e => setGitBranch(e.target.value)} placeholder="main (default)" />
            </Field>
            <Field label="Personal Access Token">
              <input style={INPUT_STYLE} type="password" value={gitToken} onChange={e => setGitToken(e.target.value)} placeholder="Optional — stored encrypted" />
            </Field>
          </div>
        )}
      </div>
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

function AddConnectorModal({
  appId,
  onClose,
  existing,
}: {
  appId: string
  onClose: () => void
  existing?: LogSource
}) {
  const qc = useQueryClient()
  const isEdit = Boolean(existing)
  const [sourceType, setSourceType] = useState<'azure_monitor' | 'elastic' | 'byoa' | 'aks'>((existing?.source_type as 'azure_monitor' | 'elastic' | 'byoa' | 'aks') ?? 'azure_monitor')
  const [displayName, setDisplayName] = useState(existing?.display_name ?? '')
  const [credType, setCredType] = useState<'env_var' | 'db_encrypted' | 'kv_reference'>((existing?.credential_type as 'env_var' | 'db_encrypted' | 'kv_reference') ?? 'env_var')
  const [credRef, setCredRef] = useState('')
  const [credValue, setCredValue] = useState('')
  const existingConfig = (existing?.config_json ?? {}) as Record<string, unknown>
  const [configJson, setConfigJson] = useState(JSON.stringify(existingConfig, null, 2))
  const [configError, setConfigError] = useState('')

  // Azure Monitor guided fields
  const [azureRole, setAzureRole] = useState<'apim_logs' | 'container_insights' | 'azure_activity'>((existingConfig.connector_role as 'apim_logs' | 'container_insights' | 'azure_activity') ?? 'apim_logs')
  const [azureWorkspaceId, setAzureWorkspaceId] = useState(typeof existingConfig.workspace_id === 'string' ? existingConfig.workspace_id : '')
  const [azureSub, setAzureSub] = useState(typeof existingConfig.subscription_id === 'string' ? existingConfig.subscription_id : '')
  const [azureRg, setAzureRg] = useState(typeof existingConfig.resource_group === 'string' ? existingConfig.resource_group : '')
  const [azureTenantId, setAzureTenantId] = useState(typeof existingConfig.tenant_id === 'string' ? existingConfig.tenant_id : '')
  const [azureApimTable, setAzureApimTable] = useState(typeof existingConfig.apim_table === 'string' ? existingConfig.apim_table : 'ApiManagementGatewayLogs')
  const [azureApimServiceName, setAzureApimServiceName] = useState(typeof existingConfig.apim_service_name === 'string' ? existingConfig.apim_service_name : '')
  const [azureClusterName, setAzureClusterName] = useState(typeof existingConfig.cluster_name === 'string' ? existingConfig.cluster_name : '')
  const [azureNs, setAzureNs] = useState(
    Array.isArray(existingConfig.namespaces)
      ? existingConfig.namespaces.map(v => String(v)).join(',')
      : (typeof existingConfig.default_namespace === 'string' ? existingConfig.default_namespace : 'default'),
  )
  const [azureActivityTable, setAzureActivityTable] = useState(typeof existingConfig.activity_table === 'string' ? existingConfig.activity_table : 'AzureActivity')
  const [azureActivityRange, setAzureActivityRange] = useState(String(existingConfig.default_time_range_minutes ?? 60))
  const [azureActivityMax, setAzureActivityMax] = useState(String(existingConfig.max_events ?? 100))

  // AKS guided fields
  const [aksCluster, setAksCluster] = useState(typeof existingConfig.cluster_name === 'string' ? existingConfig.cluster_name : '')
  const [aksRg, setAksRg] = useState(typeof existingConfig.resource_group === 'string' ? existingConfig.resource_group : '')
  const [aksSub, setAksSub] = useState(typeof existingConfig.subscription_id === 'string' ? existingConfig.subscription_id : '')
  const [aksNs, setAksNs] = useState(
    Array.isArray(existingConfig.namespaces)
      ? existingConfig.namespaces.map(v => String(v)).join(',')
      : (typeof existingConfig.default_namespace === 'string' ? existingConfig.default_namespace : 'default'),
  )
  const [aksKubeconfigPath, setAksKubeconfigPath] = useState(typeof existingConfig.kube_config_path === 'string' ? existingConfig.kube_config_path : '')
  const [aksInCluster, setAksInCluster] = useState(Boolean(existingConfig.in_cluster))
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
        const namespaces = parseNamespacesInput(aksNs)
        const config = {
          cluster_name: aksCluster.trim(),
          resource_group: aksRg.trim(),
          subscription_id: aksSub.trim(),
          namespaces,
          default_namespace: namespaces[0],
          ...(aksInCluster ? { in_cluster: true } : { kube_config_path: aksKubeconfigPath.trim() || undefined }),
        }
        const cred = JSON.stringify({
          client_id: aksClientId.trim(),
          client_secret: aksClientSecret,
          tenant_id: aksTenantId.trim(),
        })
        const payload: Partial<LogSource> & { credential_value?: string } = {
          source_type: 'aks',
          display_name: displayName,
          config_json: config,
          credential_type: 'db_encrypted',
          credential_value: cred,
        }
        if (existing) {
          return updateConnector(appId, existing.id, payload)
        }
        return addConnector(appId, payload)
      }
      if (sourceType === 'azure_monitor') {
        const config: Record<string, unknown> = {
          connector_role: azureRole,
          workspace_id: azureWorkspaceId.trim(),
        }
        if (azureSub.trim()) config.subscription_id = azureSub.trim()
        if (azureRg.trim()) config.resource_group = azureRg.trim()
        if (azureTenantId.trim()) config.tenant_id = azureTenantId.trim()
        if (azureRole === 'apim_logs') {
          config.apim_table = azureApimTable.trim() || 'ApiManagementGatewayLogs'
          if (azureApimServiceName.trim()) config.apim_service_name = azureApimServiceName.trim()
        }
        if (azureRole === 'container_insights') {
          const namespaces = parseNamespacesInput(azureNs)
          config.cluster_name = azureClusterName.trim()
          config.namespaces = namespaces
          config.default_namespace = namespaces[0]
        }
        if (azureRole === 'azure_activity') {
          config.activity_table = azureActivityTable.trim() || 'AzureActivity'
          config.default_time_range_minutes = Number(azureActivityRange || 60)
          config.max_events = Number(azureActivityMax || 100)
        }
        const payload: Partial<LogSource> & { credential_value?: string } = {
          source_type: sourceType,
          display_name: displayName,
          config_json: config,
          credential_type: credType,
        }
        if (credType === 'db_encrypted') {
          if (credValue) payload.credential_value = credValue
        } else if (credRef.trim()) {
          payload.credential_ref = credRef.trim()
        }
        if (existing) {
          return updateConnector(appId, existing.id, payload)
        }
        return addConnector(appId, payload)
      }
      if (!validateJson(configJson)) return Promise.reject(new Error('Bad JSON'))
      const payload: Partial<LogSource> & { credential_value?: string } = {
        source_type: sourceType,
        display_name: displayName,
        config_json: JSON.parse(configJson),
        credential_type: credType,
      }
      if (credType === 'db_encrypted') {
        if (credValue) payload.credential_value = credValue
      } else if (credRef.trim()) {
        payload.credential_ref = credRef.trim()
      }
      if (existing) {
        return updateConnector(appId, existing.id, payload)
      }
      return addConnector(appId, payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  const placeholders: Record<string, string> = {
    azure_monitor: '{"workspace_id":"<guid>","apim_table":"ApiManagementGatewayLogs"}',
    elastic: '{"cluster_url":"https://elastic:9200","index_pattern_logs":"logs-*"}',
    byoa: '{"base_url":"https://api.example.com","health_endpoint":"/health"}',
  }

  return (
    <Modal title={isEdit ? 'Edit Connector' : 'Add Connector'} onClose={onClose}>
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
          : sourceType === 'aks' ? 'e.g. Production AKS Cluster'
          : 'e.g. Custom Observability API'
        } />
      </Field>

      {sourceType === 'aks' ? (
        <>
          <Field label="Cluster Name *">
            <input style={INPUT_STYLE} value={aksCluster} onChange={e => setAksCluster(e.target.value)} placeholder="e.g. azaustaekub14470dv0101" />
          </Field>
          <Field label="Resource Group *">
            <input style={INPUT_STYLE} value={aksRg} onChange={e => setAksRg(e.target.value)} placeholder="e.g. rg-platform-prod" />
          </Field>
          <Field label="Subscription ID *">
            <input style={INPUT_STYLE} value={aksSub} onChange={e => setAksSub(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </Field>
          <Field label="Namespaces (comma-separated)">
            <input style={INPUT_STYLE} value={aksNs} onChange={e => setAksNs(e.target.value)} placeholder="e.g. default,monitoring,platform" />
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
      ) : sourceType === 'azure_monitor' ? (
        <>
          <Field label="Azure Monitor Role *">
            <select style={INPUT_STYLE} value={azureRole} onChange={e => setAzureRole(e.target.value as 'apim_logs' | 'container_insights' | 'azure_activity')}>
              <option value="apim_logs">APIM Gateway Logs</option>
              <option value="container_insights">AKS Container Insights</option>
              <option value="azure_activity">Azure Activity Changes</option>
            </select>
          </Field>
          <Field label="Workspace ID *">
            <input style={INPUT_STYLE} value={azureWorkspaceId} onChange={e => setAzureWorkspaceId(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
          </Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Field label="Subscription ID">
              <input style={INPUT_STYLE} value={azureSub} onChange={e => setAzureSub(e.target.value)} placeholder="Azure subscription GUID" />
            </Field>
            <Field label="Resource Group">
              <input style={INPUT_STYLE} value={azureRg} onChange={e => setAzureRg(e.target.value)} placeholder="e.g. rg-platform-prod" />
            </Field>
          </div>
          <Field label="Tenant ID">
            <input style={INPUT_STYLE} value={azureTenantId} onChange={e => setAzureTenantId(e.target.value)} placeholder="Azure tenant GUID" />
          </Field>
          {azureRole === 'apim_logs' ? (
            <>
              <Field label="APIM Table">
                <input style={INPUT_STYLE} value={azureApimTable} onChange={e => setAzureApimTable(e.target.value)} placeholder="ApiManagementGatewayLogs" />
              </Field>
              <Field label="APIM Service Name (optional)">
                <input style={INPUT_STYLE} value={azureApimServiceName} onChange={e => setAzureApimServiceName(e.target.value)} placeholder="Helpful for vendor scoping" />
              </Field>
            </>
          ) : azureRole === 'container_insights' ? (
            <>
              <Field label="AKS Cluster Name *">
                <input style={INPUT_STYLE} value={azureClusterName} onChange={e => setAzureClusterName(e.target.value)} placeholder="e.g. azaustaekub14470dv0101" />
              </Field>
              <Field label="Namespaces (comma-separated)">
                <input style={INPUT_STYLE} value={azureNs} onChange={e => setAzureNs(e.target.value)} placeholder="e.g. default,monitoring,platform" />
              </Field>
            </>
          ) : null}
          {azureRole === 'azure_activity' && (
            <>
              <Field label="Activity Table">
                <input style={INPUT_STYLE} value={azureActivityTable} onChange={e => setAzureActivityTable(e.target.value)} placeholder="AzureActivity" />
              </Field>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <Field label="Default Time Range (minutes)">
                  <input style={INPUT_STYLE} type="number" min="1" value={azureActivityRange} onChange={e => setAzureActivityRange(e.target.value)} placeholder="60" />
                </Field>
                <Field label="Max Events">
                  <input style={INPUT_STYLE} type="number" min="1" value={azureActivityMax} onChange={e => setAzureActivityMax(e.target.value)} placeholder="100" />
                </Field>
              </div>
            </>
          )}
          <Field label="Credential Type">
            <select style={INPUT_STYLE} value={credType} onChange={e => setCredType(e.target.value as typeof credType)}>
              <option value="env_var">DefaultAzureCredential / optional env var ref</option>
              <option value="db_encrypted">DB Encrypted (AES-256-GCM)</option>
              <option value="kv_reference">Azure Key Vault Reference</option>
            </select>
          </Field>
          {credType === 'env_var' && (
            <Field label="Env Var Name (optional)">
              <input style={INPUT_STYLE} value={credRef} onChange={e => setCredRef(e.target.value)} placeholder="Leave blank for managed identity" />
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
              <option value="env_var">DefaultAzureCredential / optional env var ref</option>
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
          {mut.isPending ? 'Saving…' : isEdit ? 'Save Changes' : 'Add Connector'}
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

function ServiceCard({ svc, appId }: { svc: ApplicationService; appId: string }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [gitProvider, setGitProvider] = useState(svc.git_provider ?? 'azure_devops')
  const [gitRepoUrl, setGitRepoUrl] = useState(svc.git_repo_url ?? '')
  const [gitBranch, setGitBranch] = useState(svc.git_branch ?? '')
  const [gitToken, setGitToken] = useState('')

  const deleteMut = useMutation({
    mutationFn: () => deleteService(appId, svc.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', appId] }),
  })
  const gitMut = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        git_provider: gitProvider,
        git_repo_url: gitRepoUrl.trim() || null,
        git_branch: gitBranch.trim() || null,
      }
      if (gitToken.trim()) payload.git_token = gitToken.trim()
      return updateService(appId, svc.id, payload as any)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); setGitToken('') },
  })

  return (
    <div style={{
      background: 'var(--c-bg)', border: '1px solid var(--c-border)', borderRadius: 8,
      padding: '11px 14px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 600, marginBottom: 2 }}>{svc.display_name}</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)' }}>{svc.service_name}{svc.namespace ? ` · ${svc.namespace}` : ''}</div>
        </div>
        {svc.git_repo_url && <span title="Git configured" style={{ fontSize: '0.8rem' }}>🔗</span>}
        <TierBadge tier={svc.tier} />
        <button
          onClick={() => setExpanded(v => !v)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.75rem', padding: 4 }}
          title="Git config"
        >{expanded ? '▾' : '▸'} Git</button>
        <button
          onClick={() => deleteMut.mutate()}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}
          title="Remove service"
        >✕</button>
      </div>
      {expanded && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--c-border)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Field label="Provider">
              <select style={INPUT_STYLE} value={gitProvider} onChange={e => setGitProvider(e.target.value)}>
                <option value="azure_devops">Azure DevOps</option>
                <option value="github">GitHub</option>
              </select>
            </Field>
            <Field label="Branch">
              <input style={INPUT_STYLE} value={gitBranch} onChange={e => setGitBranch(e.target.value)} placeholder="main" />
            </Field>
          </div>
          <Field label="Repo URL">
            <input style={INPUT_STYLE} value={gitRepoUrl} onChange={e => setGitRepoUrl(e.target.value)} placeholder="https://dev.azure.com/org/project/_git/repo" />
          </Field>
          <Field label={svc.has_git_token ? "PAT (stored ✓ — enter to replace)" : "Personal Access Token"}>
            <input style={INPUT_STYLE} type="password" value={gitToken} onChange={e => setGitToken(e.target.value)} placeholder="Optional — stored encrypted" />
          </Field>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="btn-primary" style={{ fontSize: '0.72rem', padding: '4px 10px' }} onClick={() => gitMut.mutate()} disabled={gitMut.isPending}>
              {gitMut.isPending ? 'Saving…' : 'Save Git Config'}
            </button>
          </div>
          {gitMut.isError && <p style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: 4 }}>{String(gitMut.error)}</p>}
        </div>
      )}
    </div>
  )
}

function ServicesTab({ app }: { app: Application }) {
  const [showAdd, setShowAdd] = useState(false)
  const services = app.services ?? []

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
          <ServiceCard key={svc.id} svc={svc} appId={app.id} />
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
  azure_devops_boards: '🧩',
  azure_devops_wiki: '📘',
  sharepoint: '📂',
}

// ── Connector builder constants ───────────────────────────────────────────────

type ConnectorAuthType = 'none' | 'bearer' | 'api_key' | 'basic' | 'oauth2'
type ConnectorType =
  | 'teams_webhook'
  | 'servicenow'
  | 'email'
  | 'pagerduty'
  | 'generic_http'
  | 'azure_devops_boards'
  | 'azure_devops_wiki'
  | 'sharepoint'
interface ConnectorVariable { key: string; default_value: string }

const CONNECTOR_DEFAULT_ENDPOINTS: Record<string, string> = {
  teams_webhook: '',
  servicenow: '',
  email: '',
  pagerduty: 'https://events.pagerduty.com/v2/enqueue',
  generic_http: '',
  azure_devops_boards: 'https://dev.azure.com/your-org',
  azure_devops_wiki: 'https://dev.azure.com/your-org',
  sharepoint: 'https://yourtenant.sharepoint.com/sites/your-site',
}

const CONNECTOR_DEFAULT_AUTH: Record<string, ConnectorAuthType> = {
  teams_webhook: 'none',
  servicenow: 'oauth2',
  email: 'basic',
  pagerduty: 'none',
  generic_http: 'none',
  azure_devops_boards: 'api_key',
  azure_devops_wiki: 'api_key',
  sharepoint: 'oauth2',
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
  azure_devops_boards: [
    { key: 'tags', default_value: 'corvin;{{environment}};{{service_name}}' },
  ],
  azure_devops_wiki: [
    { key: 'section', default_value: 'Investigations' },
  ],
  sharepoint: [
    { key: 'folder_hint', default_value: '{{environment}}/{{service_name}}' },
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
  azure_devops_boards: `{
  "title": "Corvin: {{service_name}} degraded",
  "description": "{{rca_summary}}",
  "tags": "{{tags}}"
}`,
  azure_devops_wiki: `{
  "title": "Corvin Investigation {{request_id}}",
  "summary": "{{rca_summary}}",
  "section": "{{section}}"
}`,
  sharepoint: `{
  "title": "Corvin Investigation {{request_id}}",
  "summary": "{{rca_summary}}",
  "folder_hint": "{{folder_hint}}"
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
  const [editingInbound, setEditingInbound] = useState<LogSource | null>(null)
  const [editingOutbound, setEditingOutbound] = useState<OutboundConnector | null>(null)
  const [testingOutboundId, setTestingOutboundId] = useState<string | null>(null)
  const [outboundTestResults, setOutboundTestResults] = useState<Record<string, { ok: boolean; message: string; latency_ms: number | null }>>({})
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

  const bootstrapOutMut = useMutation({
    mutationFn: () => bootstrapOutboundConnectors(app.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['application', app.id] }),
  })

  const runOutboundTest = useCallback(async (connId: string) => {
    setTestingOutboundId(connId)
    try {
      const r = await testOutboundConnector(app.id, connId)
      setOutboundTestResults(prev => ({ ...prev, [connId]: r }))
      qc.invalidateQueries({ queryKey: ['application', app.id] })
    } catch (err) {
      setOutboundTestResults(prev => ({ ...prev, [connId]: { ok: false, message: String(err), latency_ms: null } }))
    } finally {
      setTestingOutboundId(null)
    }
  }, [app.id, qc])

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
                      {src.source_type} · {describeCredentialMode(src)}
                    </div>
                    {describeConnectorConfig(src) && (
                      <div style={{ fontSize: '0.68rem', color: 'var(--c-text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                        {describeConnectorConfig(src)}
                      </div>
                    )}
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
                        className="btn-secondary"
                        style={{ fontSize: '0.72rem', padding: '4px 10px' }}
                        onClick={() => setEditingInbound(src)}
                      >
                        Edit
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
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '5px 12px' }}
              onClick={() => bootstrapOutMut.mutate()}
              disabled={bootstrapOutMut.isPending}
            >
              {bootstrapOutMut.isPending ? 'Bootstrapping…' : 'Bootstrap Defaults'}
            </button>
            <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => setShowAddOutbound(true)}>+ Add Destination</button>
          </div>
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
            const localResult = outboundTestResults[conn.id]
            const ok = localResult?.ok ?? (conn.test_status === 'ok' ? true : conn.test_status === 'error' ? false : null)
            const latency = localResult?.latency_ms ?? null
            const isTesting = testingOutboundId === conn.id
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
                      <StatusDot ok={ok} tested={ok !== null} />
                      {latency !== null && (
                        <span style={{ color: 'var(--c-text-faint)' }}>{latency.toFixed(0)}ms</span>
                      )}
                      {authType !== 'none' && <span style={{ color: 'var(--c-accent)', background: 'color-mix(in srgb, var(--c-accent) 12%, transparent)', padding: '1px 6px', borderRadius: 4 }}>{authType.replace('_', ' ')}</span>}
                      {varCount > 0 && <span style={{ color: 'var(--c-text-muted)' }}>{varCount} var{varCount !== 1 ? 's' : ''}</span>}
                    </div>
                    {(localResult?.message || conn.test_message) && (
                      <div style={{
                        fontSize: '0.7rem', fontFamily: 'var(--font-mono)',
                        color: ok ? '#22c55e' : '#ef4444',
                        marginTop: 2,
                      }}>
                        {localResult?.message ?? conn.test_message}
                      </div>
                    )}
                    {endpoint && (
                      <div style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--c-text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 380 }}>
                        {endpoint}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '0.72rem', padding: '4px 10px' }}
                      onClick={() => runOutboundTest(conn.id)}
                      disabled={isTesting}
                    >
                      {isTesting ? 'Testing…' : 'Test'}
                    </button>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '0.72rem', padding: '4px 10px' }}
                      onClick={() => setEditingOutbound(conn)}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => deleteOutMut.mutate(conn.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}
                      title="Remove outbound connector"
                    >✕</button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {showAdd && <AddConnectorModal appId={app.id} onClose={() => setShowAdd(false)} />}
      {editingInbound && <AddConnectorModal appId={app.id} onClose={() => setEditingInbound(null)} existing={editingInbound} />}
      {showAddOutbound && <AddOutboundModal appId={app.id} onClose={() => setShowAddOutbound(false)} />}
      {editingOutbound && (
        <AddOutboundModal
          appId={app.id}
          onClose={() => setEditingOutbound(null)}
          existing={editingOutbound}
        />
      )}
    </div>
  )
}

// ── Add Outbound Modal ────────────────────────────────────────────────────────

function AddOutboundModal({
  appId,
  onClose,
  existing,
}: {
  appId: string
  onClose: () => void
  existing?: OutboundConnector
}) {
  const qc = useQueryClient()
  const isEdit = Boolean(existing)

  // ── Basic ──────────────────────────────────────────────────────────────────
  const initialType = (existing?.connector_type ?? 'teams_webhook') as ConnectorType
  const existingCfg = existing?.config_json
  const existingEndpointFields = existingCfg?.endpoint_fields ?? {}
  const existingAuth = existingCfg?.auth ?? { type: CONNECTOR_DEFAULT_AUTH[initialType] }

  const [connType, setConnType] = useState<ConnectorType>(initialType)
  const [displayName, setDisplayName] = useState(existing?.display_name ?? '')

  // ── Endpoint ───────────────────────────────────────────────────────────────
  const [endpoint, setEndpoint] = useState(existingCfg?.endpoint ?? existingCfg?.webhook_url ?? CONNECTOR_DEFAULT_ENDPOINTS[initialType])
  const [httpMethod, setHttpMethod] = useState(existingEndpointFields.http_method ?? 'POST')
  const [snTable, setSnTable] = useState(existingEndpointFields.table ?? 'incident')
  const [emailPort, setEmailPort] = useState(existingEndpointFields.port ?? '587')
  const [emailFrom, setEmailFrom] = useState(existingEndpointFields.from ?? '')
  const [adoProjectName, setAdoProjectName] = useState(existingEndpointFields.project_name ?? '')
  const [adoWorkItemType, setAdoWorkItemType] = useState(existingEndpointFields.work_item_type ?? 'Issue')
  const [adoWikiId, setAdoWikiId] = useState(existingEndpointFields.wiki_id ?? 'auto')
  const [sharePointSiteId, setSharePointSiteId] = useState(existingEndpointFields.site_id ?? '')
  const [sharePointDriveId, setSharePointDriveId] = useState(existingEndpointFields.drive_id ?? 'auto')
  const [sharePointFolderPath, setSharePointFolderPath] = useState(existingEndpointFields.folder_path ?? 'Corvin/Investigations')

  // ── Auth ───────────────────────────────────────────────────────────────────
  const [authType, setAuthType] = useState<ConnectorAuthType>((existingAuth.type ?? CONNECTOR_DEFAULT_AUTH[initialType]) as ConnectorAuthType)
  const [bearerToken, setBearerToken] = useState(existingAuth.bearer_token ?? '')
  const [bearerTokenRef, setBearerTokenRef] = useState(existingAuth.bearer_token_ref ?? '')
  const [apiKey, setApiKey] = useState(existingAuth.api_key ?? '')
  const [apiKeyRef, setApiKeyRef] = useState(existingAuth.api_key_ref ?? '')
  const [apiKeyHeader, setApiKeyHeader] = useState(existingAuth.api_key_header ?? 'X-API-Key')
  const [authUser, setAuthUser] = useState(existingAuth.username ?? '')
  const [authPass, setAuthPass] = useState(existingAuth.password ?? '')
  const [authPassRef, setAuthPassRef] = useState(existingAuth.password_ref ?? '')
  const [oauthTokenUrl, setOauthTokenUrl] = useState(existingAuth.token_url ?? '')
  const [oauthClientId, setOauthClientId] = useState(existingAuth.client_id ?? '')
  const [oauthClientSecret, setOauthClientSecret] = useState(existingAuth.client_secret ?? '')
  const [oauthClientSecretRef, setOauthClientSecretRef] = useState(existingAuth.client_secret_ref ?? '')
  const [oauthScopes, setOauthScopes] = useState(existingAuth.scopes ?? '')

  // ── Variables ──────────────────────────────────────────────────────────────
  const [variables, setVariables] = useState<ConnectorVariable[]>(
    () => (existingCfg?.variables?.length ? existingCfg.variables.map((v: ConnectorVariable) => ({ ...v })) : CONNECTOR_DEFAULT_VARS[initialType].map(v => ({ ...v }))),
  )

  // ── Payload template ───────────────────────────────────────────────────────
  const [payloadTemplate, setPayloadTemplate] = useState(existingCfg?.payload_template ?? CONNECTOR_DEFAULT_PAYLOADS[initialType])

  const handleTypeChange = (t: ConnectorType) => {
    setConnType(t)
    setEndpoint(CONNECTOR_DEFAULT_ENDPOINTS[t] || '')
    setAuthType(CONNECTOR_DEFAULT_AUTH[t] || 'none')
    setVariables((CONNECTOR_DEFAULT_VARS[t] || []).map(v => ({ ...v })))
    setPayloadTemplate(CONNECTOR_DEFAULT_PAYLOADS[t] || '')
    setHttpMethod('POST'); setSnTable('incident'); setEmailPort('587'); setEmailFrom('')
    setAdoProjectName(''); setAdoWorkItemType('Issue'); setAdoWikiId('auto')
    setSharePointSiteId(''); setSharePointDriveId('auto'); setSharePointFolderPath('Corvin/Investigations')
    setBearerToken(''); setApiKey(''); setApiKeyHeader('X-API-Key')
    setBearerTokenRef(''); setApiKeyRef('')
    setAuthUser(''); setAuthPass(''); setOauthTokenUrl('')
    setAuthPassRef('')
    setOauthClientId(''); setOauthClientSecret(''); setOauthClientSecretRef(''); setOauthScopes('')
  }

  const buildConfig = () => {
    const auth: Record<string, string> = { type: authType }
    if (authType === 'bearer') {
      if (bearerToken.trim()) auth.bearer_token = bearerToken
      if (bearerTokenRef.trim()) auth.bearer_token_ref = bearerTokenRef
    }
    if (authType === 'api_key') {
      if (apiKey.trim()) auth.api_key = apiKey
      if (apiKeyRef.trim()) auth.api_key_ref = apiKeyRef
      auth.api_key_header = apiKeyHeader
    }
    if (authType === 'basic') {
      if (authUser.trim()) auth.username = authUser
      if (authPass.trim()) auth.password = authPass
      if (authPassRef.trim()) auth.password_ref = authPassRef
    }
    if (authType === 'oauth2') {
      auth.token_url = oauthTokenUrl
      auth.client_id = oauthClientId
      if (oauthClientSecret.trim()) auth.client_secret = oauthClientSecret
      if (oauthClientSecretRef.trim()) auth.client_secret_ref = oauthClientSecretRef
      auth.scopes = oauthScopes
    }
    const endpoint_fields: Record<string, string> = {}
    if (connType === 'servicenow') endpoint_fields.table = snTable
    if (connType === 'email') { endpoint_fields.port = emailPort; endpoint_fields.from = emailFrom }
    if (connType === 'generic_http') endpoint_fields.http_method = httpMethod
    if (connType === 'azure_devops_boards') {
      endpoint_fields.project_name = adoProjectName
      endpoint_fields.work_item_type = adoWorkItemType
    }
    if (connType === 'azure_devops_wiki') {
      endpoint_fields.project_name = adoProjectName
      endpoint_fields.wiki_id = adoWikiId
    }
    if (connType === 'sharepoint') {
      endpoint_fields.site_id = sharePointSiteId
      endpoint_fields.drive_id = sharePointDriveId
      endpoint_fields.folder_path = sharePointFolderPath
    }
    return { endpoint, endpoint_fields, auth, variables, payload_template: payloadTemplate }
  }

  const mut = useMutation({
    mutationFn: () => {
      const payload = {
        connector_type: connType,
        display_name: displayName,
        config_json: buildConfig() as never,
      }
      if (existing) {
        return updateOutboundConnector(appId, existing.id, payload)
      }
      return addOutboundConnector(appId, payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['application', appId] }); onClose() },
  })

  // ── Shared style helpers ───────────────────────────────────────────────────
  const inp = { display: 'block', width: '100%', marginTop: 4, padding: '7px 10px', borderRadius: 6, border: '1px solid var(--c-border)', background: 'var(--c-bg)', color: 'var(--c-text)', fontSize: '0.8rem', boxSizing: 'border-box' as const }
  const monoInp = { ...inp, fontFamily: 'var(--font-mono)' as string }
  const lbl = { fontSize: '0.75rem', fontFamily: 'var(--font-display)', fontWeight: 600, display: 'block' as const }
  const sectionHdr = { fontSize: '0.68rem', fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--c-text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', paddingBottom: 8, borderBottom: '1px solid var(--c-border)', marginBottom: 12 }

  const endpointLabel = connType === 'servicenow'
    ? 'Instance URL'
    : connType === 'teams_webhook'
      ? 'Webhook URL'
      : connType === 'pagerduty'
        ? 'Events API URL'
        : connType === 'email'
          ? 'SMTP Host / API Endpoint'
          : connType === 'azure_devops_boards' || connType === 'azure_devops_wiki'
            ? 'Azure DevOps Org URL'
            : connType === 'sharepoint'
              ? 'SharePoint Site URL'
              : 'Endpoint URL'
  const endpointPlaceholder = connType === 'servicenow'
    ? 'https://myinstance.service-now.com'
    : connType === 'pagerduty'
      ? 'https://events.pagerduty.com/v2/enqueue'
      : connType === 'email'
        ? 'smtp.example.com'
        : connType === 'azure_devops_boards' || connType === 'azure_devops_wiki'
          ? 'https://dev.azure.com/your-org'
          : connType === 'sharepoint'
            ? 'https://yourtenant.sharepoint.com/sites/your-site'
            : 'https://...'

  return (
    <Modal title={isEdit ? 'Edit Outbound Connector' : 'Add Outbound Connector'} onClose={onClose}>
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
              <option value="azure_devops_boards">🧩  Azure DevOps Boards</option>
              <option value="azure_devops_wiki">📘  Azure DevOps Wiki</option>
              <option value="sharepoint">📂  SharePoint</option>
            </select>
          </label>
          <label style={lbl}>
            Display Name
            <input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="e.g. Production Alerts" style={{ ...inp, marginTop: 4 }} />
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
            {(connType === 'azure_devops_boards' || connType === 'azure_devops_wiki') && (
              <label style={lbl}>
                Project Name
                <input value={adoProjectName} onChange={e => setAdoProjectName(e.target.value)} placeholder="e.g. Corvin" style={monoInp} />
              </label>
            )}
            {connType === 'azure_devops_boards' && (
              <label style={lbl}>
                Work Item Type
                <input value={adoWorkItemType} onChange={e => setAdoWorkItemType(e.target.value)} placeholder="Issue" style={monoInp} />
              </label>
            )}
            {connType === 'azure_devops_wiki' && (
              <label style={lbl}>
                Wiki ID
                <input value={adoWikiId} onChange={e => setAdoWikiId(e.target.value)} placeholder="auto" style={monoInp} />
              </label>
            )}
            {connType === 'email' && (
              <label style={lbl}>
                From Address
                <input value={emailFrom} onChange={e => setEmailFrom(e.target.value)} placeholder="corvin@yourorg.com" style={inp} />
              </label>
            )}
            {connType === 'sharepoint' && (
              <>
                <label style={lbl}>
                  Site ID
                  <input value={sharePointSiteId} onChange={e => setSharePointSiteId(e.target.value)} placeholder="SharePoint site id" style={monoInp} />
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <label style={lbl}>
                    Drive ID
                    <input value={sharePointDriveId} onChange={e => setSharePointDriveId(e.target.value)} placeholder="auto" style={monoInp} />
                  </label>
                  <label style={lbl}>
                    Folder Path
                    <input value={sharePointFolderPath} onChange={e => setSharePointFolderPath(e.target.value)} placeholder="Corvin/Investigations" style={monoInp} />
                  </label>
                </div>
              </>
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
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label style={lbl}>
                Bearer Token
                <input type="password" value={bearerToken} onChange={e => setBearerToken(e.target.value)} placeholder="eyJ..." style={monoInp} />
              </label>
              <label style={lbl}>
                Bearer Token Ref
                <input value={bearerTokenRef} onChange={e => setBearerTokenRef(e.target.value)} placeholder="env:TEAMS_BEARER_TOKEN" style={monoInp} />
              </label>
            </div>
          )}
          {authType === 'api_key' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 160px', gap: 10 }}>
              <label style={lbl}>
                API Key
                <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." style={monoInp} />
              </label>
              <label style={lbl}>
                API Key Ref
                <input value={apiKeyRef} onChange={e => setApiKeyRef(e.target.value)} placeholder="env:SERVICENOW_API_KEY" style={monoInp} />
              </label>
              <label style={lbl}>
                Header Name
                <input value={apiKeyHeader} onChange={e => setApiKeyHeader(e.target.value)} placeholder="X-API-Key" style={monoInp} />
              </label>
            </div>
          )}
          {authType === 'basic' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <label style={lbl}>
                Username
                <input value={authUser} onChange={e => setAuthUser(e.target.value)} placeholder="admin" style={inp} />
              </label>
              <label style={lbl}>
                Password
                <input type="password" value={authPass} onChange={e => setAuthPass(e.target.value)} placeholder="••••••" style={inp} />
              </label>
              <label style={lbl}>
                Password Ref
                <input value={authPassRef} onChange={e => setAuthPassRef(e.target.value)} placeholder="env:BASIC_AUTH_PASSWORD" style={monoInp} />
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
                <label style={lbl}>
                  Client Secret Ref
                  <input value={oauthClientSecretRef} onChange={e => setOauthClientSecretRef(e.target.value)} placeholder="env:SERVICENOW_CLIENT_SECRET" style={monoInp} />
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
          {mut.isPending ? 'Saving…' : isEdit ? 'Save Changes' : 'Save Connector'}
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

// ── Environments Tab ──────────────────────────────────────────────────────────

const PRIORITY_TIERS = ['P1', 'P2', 'P3']

function EnvironmentsTab({ appId }: { appId: string }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<Partial<ApplicationEnvironment>>({})

  const { data: envs = [], isLoading } = useQuery({
    queryKey: ['app-environments', appId],
    queryFn: () => listEnvironments(appId),
  })

  const createMut = useMutation({
    mutationFn: (p: Partial<ApplicationEnvironment>) => createEnvironment(appId, p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['app-environments', appId] }); setShowAdd(false); setForm({}) },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, p }: { id: number; p: Partial<ApplicationEnvironment> }) => updateEnvironment(appId, id, p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['app-environments', appId] }); setEditId(null); setForm({}) },
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteEnvironment(appId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-environments', appId] }),
  })

  const fs: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', padding: '7px 10px',
    background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
    borderRadius: 6, color: 'var(--c-text)', fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
  }

  const PRIORITY_COLORS: Record<string, string> = { P1: '#ef4444', P2: '#f59e0b', P3: '#10b981' }

  function openEdit(env: ApplicationEnvironment) {
    setEditId(env.id)
    setForm({ name: env.name, display_name: env.display_name, priority_tier: env.priority_tier, lookback_minutes: env.lookback_minutes, is_default: env.is_default, display_order: env.display_order })
    setShowAdd(true)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
          Define your application's environments. These drive priority classification, alert routing, and all environment dropdowns across the UI.
        </p>
        <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 14px', whiteSpace: 'nowrap' }} onClick={() => { setEditId(null); setForm({}); setShowAdd(true) }}>+ Add Environment</button>
      </div>

      {isLoading && <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem' }}>Loading…</p>}
      {!isLoading && envs.length === 0 && (
        <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem', fontStyle: 'italic' }}>
          No environments defined yet. Add at least one (e.g. production) to enable priority routing.
        </p>
      )}

      {envs.map(env => (
        <div key={env.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.82rem', color: PRIORITY_COLORS[env.priority_tier] || 'var(--c-text)' }}>{env.priority_tier}</span>
            <div>
              <span style={{ fontWeight: 600, fontSize: '0.8rem' }}>{env.display_name}</span>
              <span style={{ marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)' }}>{env.name}</span>
              {env.is_default && <span style={{ marginLeft: 8, fontSize: '0.65rem', color: 'var(--c-signal)', background: 'var(--c-signal-light)', padding: '1px 6px', borderRadius: 4 }}>default</span>}
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)' }}>lookback: {env.lookback_minutes}min</span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => openEdit(env)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.8rem', padding: 4 }}>✎</button>
            <button onClick={() => { if (window.confirm(`Delete environment "${env.name}"?`)) deleteMut.mutate(env.id) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}>✕</button>
          </div>
        </div>
      ))}

      {showAdd && (
        <div style={{ padding: 16, background: 'var(--c-surface)', border: '1px solid var(--c-border-hi)', borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem' }}>{editId ? 'Edit Environment' : 'New Environment'}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Name (slug)</label>
              <input style={fs} value={form.name ?? ''} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. production" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Display Name</label>
              <input style={fs} value={form.display_name ?? ''} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} placeholder="e.g. Production" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Priority Tier</label>
              <select style={fs} value={form.priority_tier ?? 'P3'} onChange={e => setForm(f => ({ ...f, priority_tier: e.target.value as ApplicationEnvironment['priority_tier'] }))}>
                {PRIORITY_TIERS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Lookback (minutes)</label>
              <input style={fs} type="number" value={form.lookback_minutes ?? 60} onChange={e => setForm(f => ({ ...f, lookback_minutes: parseInt(e.target.value) || 60 }))} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 20 }}>
              <input type="checkbox" id="env-default" checked={!!form.is_default} onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} />
              <label htmlFor="env-default" style={{ fontSize: '0.78rem' }}>Set as default environment</label>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 16px' }}
              onClick={() => { if (!form.name || !form.display_name) return; editId ? updateMut.mutate({ id: editId, p: form }) : createMut.mutate({ ...form, priority_tier: form.priority_tier ?? 'P3', lookback_minutes: form.lookback_minutes ?? 60 }) }}
              disabled={createMut.isPending || updateMut.isPending}>
              {editId ? 'Save Changes' : 'Add Environment'}
            </button>
            <button className="btn-ghost" style={{ fontSize: '0.75rem', padding: '6px 14px' }} onClick={() => { setShowAdd(false); setEditId(null); setForm({}) }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Knowledge Scaffold Modal ──────────────────────────────────────────────────

const SCAFFOLD_PROMPT = `You are mapping this workspace's architecture for Corvin — an AI-powered SRE intelligence platform. Your output will be injected verbatim into live incident-investigation prompts, so precision matters more than prose.

Scan ALL of the following files and directories (silently skip anything absent):
  • package.json / requirements.txt / pyproject.toml / *.csproj
  • docker-compose.yml / docker-compose.*.yml
  • Kubernetes manifests, Helm charts, Kustomize overlays
  • Azure resources: APIM policies, Function App host.json, App Service config
  • CI/CD pipelines: .github/workflows/, azure-pipelines.yml, .gitlab-ci.yml
  • Environment configs: .env.example, appsettings*.json, config/*.yaml
  • OpenAPI / Swagger specs: openapi.json, swagger.json, swagger.yaml
  • Infrastructure-as-code: Terraform .tf files, Bicep .bicep, ARM templates
  • Service mesh: Istio VirtualService / DestinationRule, Linkerd ServiceProfiles

Output ONLY the markdown sections below — no preamble, no commentary, no apologies.
Omit any section that yields no data. Include every section that does.

---

## Service Inventory

| Service | Runtime | Tier | K8s Namespace | k8s_app_label | Health Endpoint | Purpose |
|---|---|---|---|---|---|---|

Tier values: frontend | api | worker | db | cache | gateway

---

## Service Dependencies

Bullet list — show direction and protocol:
- **ServiceA** → ServiceB (sync/HTTP), ServiceC (async/Service Bus queue: payments)
- **ServiceA** → PostgreSQL (direct), Redis (cache-aside)

Include all external dependencies: managed databases, blob storage, third-party APIs, identity providers.

---

## API & APIM Routes

If Azure API Management is present:
- Gateway hostname:
- Products and route prefixes:

Top API endpoints (up to 20):
| Method | Path | Service | Auth | Purpose |
|---|---|---|---|---|

---

## AKS Infrastructure

- Cluster name and region:
- Namespaces and their purpose:
- Key deployments (name | replicas | CPU limit | Memory limit):
- HPA targets (service | min replicas | max replicas | CPU target %):
- Ingress hostnames and controllers:
- Stateful sets or PVCs:

---

## Azure Resources (names only — no secrets, no connection strings)

- Resource groups:
- Key Vaults:
- Storage accounts:
- Service Bus namespaces + queues/topics:
- Event Hub namespaces + hub names:
- App Insights / Log Analytics workspace names:
- Managed Identity names and their access scope:

---

## Known Failure Modes & Gotchas

Non-obvious risks an on-call engineer must know:
- Services with no circuit breaker or retry policy
- Rate-limit-sensitive external integrations
- Cold-start / scale-to-zero services and warm-up time
- Known flaky dependencies
- Deployment sequencing constraints (deploy A before B)

---

## SLO Candidates

| Service | Endpoint / Signal | SLI Type | Suggested Target | Notes |
|---|---|---|---|---|

SLI types: availability | latency_p99 (estimate target in ms)`

const STEPS = [
  {
    num: '01',
    title: 'Open your AI assistant',
    body: 'Use any premium AI model with codebase access. Best results with:',
    extra: (
      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' as const }}>
        {[
          { icon: '⎈', label: 'GitHub Copilot', sub: 'VS Code / JetBrains' },
          { icon: '◈', label: 'Cursor', sub: 'Composer / Agent' },
          { icon: '◆', label: 'Claude Code', sub: 'Terminal / IDE' },
          { icon: '✦', label: 'Windsurf', sub: 'Cascade' },
        ].map(t => (
          <div key={t.label} style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '6px 12px',
            background: 'var(--c-surface-3)',
            border: '1px solid var(--c-border)',
            borderRadius: 8,
            fontSize: '0.72rem',
          }}>
            <span style={{ fontSize: '1rem', opacity: 0.7 }}>{t.icon}</span>
            <div>
              <div style={{ fontWeight: 600, color: 'var(--c-text)', lineHeight: 1.2 }}>{t.label}</div>
              <div style={{ color: 'var(--c-text-faint)', fontSize: '0.65rem' }}>{t.sub}</div>
            </div>
          </div>
        ))}
      </div>
    ),
  },
  {
    num: '02',
    title: 'Open it in your project workspace',
    body: 'Navigate to the root of your service repository before running the prompt. For monorepos or multi-repo architectures, run once per project and combine the outputs into separate knowledge entries.',
    extra: null,
  },
  {
    num: '03',
    title: 'Paste and run this prompt',
    body: 'Copy the prompt below and send it to your AI assistant. It will analyse your codebase and return structured markdown. One-time run — typically takes 15–60 seconds.',
    extra: null,
  },
  {
    num: '04',
    title: 'Paste the output into Add Entry',
    body: 'Split the output into logical sections if preferred (e.g. one entry for "Service Inventory", another for "AKS Infrastructure"). Use the section headings as entry titles. Corvin will inject all active entries into every investigation prompt for this application.',
    extra: null,
  },
]

function KnowledgeScaffoldModal({ onClose, onAddEntry }: { onClose: () => void; onAddEntry: () => void }) {
  const [copied, setCopied] = useState(false)

  function copyPrompt() {
    navigator.clipboard.writeText(SCAFFOLD_PROMPT).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2200)
    })
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 300,
      background: 'rgba(0,0,0,0.72)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      padding: '24px 16px',
      overflowY: 'auto',
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border-hi)',
        borderRadius: 14,
        width: '100%',
        maxWidth: 820,
        boxShadow: '0 32px 64px rgba(0,0,0,0.5)',
        overflow: 'hidden',
        margin: '0 auto',
      }}>

        {/* Modal header */}
        <div style={{
          padding: '20px 28px',
          borderBottom: '1px solid var(--c-border)',
          background: 'var(--c-surface-2)',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16,
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 8,
                background: 'var(--c-signal)',
                fontSize: '0.85rem', flexShrink: 0,
              }}>⚡</span>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1rem', color: 'var(--c-text)' }}>
                Corvin Knowledge Scaffold
              </span>
            </div>
            <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>
              Use your AI assistant to reverse-engineer your codebase and generate architecture context that Corvin injects into every investigation. One prompt run covers services, dependencies, APIM, AKS, and known failure modes.
            </p>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--c-text-faint)', fontSize: '1.3rem', lineHeight: 1, flexShrink: 0, padding: 2,
          }}>×</button>
        </div>

        <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 0 }}>

          {/* Steps 01–04 */}
          {STEPS.map((step, idx) => (
            <div key={step.num} style={{ display: 'flex', gap: 16, paddingBottom: idx < STEPS.length - 1 ? 0 : 0 }}>
              {/* Step spine */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: 36 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                  background: 'var(--c-surface-3)',
                  border: '1.5px solid var(--c-border-hi)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.62rem',
                  color: 'var(--c-signal)', letterSpacing: '0.05em',
                }}>
                  {step.num}
                </div>
                {idx < STEPS.length - 1 && (
                  <div style={{ flex: 1, width: 1.5, background: 'var(--c-border)', minHeight: 24, marginTop: 6, marginBottom: 6 }} />
                )}
              </div>

              {/* Step content */}
              <div style={{ flex: 1, paddingBottom: idx < STEPS.length - 1 ? 20 : 0 }}>
                <div style={{
                  fontWeight: 700, fontSize: '0.82rem', color: 'var(--c-text)',
                  marginBottom: 4, lineHeight: 1.3,
                }}>
                  {step.title}
                </div>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--c-text-faint)', lineHeight: 1.6 }}>
                  {step.body}
                </p>
                {step.extra}

                {/* Prompt block — shown inline in step 03 */}
                {step.num === '03' && (
                  <div style={{ marginTop: 12 }}>
                    {/* Prompt header bar */}
                    <div style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '8px 14px',
                      background: 'var(--c-surface-3)',
                      border: '1px solid var(--c-border-hi)',
                      borderBottom: 'none',
                      borderRadius: '8px 8px 0 0',
                    }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--c-text-faint)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                        Corvin Architecture Scaffold Prompt
                      </span>
                      <button
                        onClick={copyPrompt}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 6,
                          padding: '4px 12px',
                          background: copied ? 'var(--c-green)' : 'var(--c-surface)',
                          border: `1px solid ${copied ? 'var(--c-green)' : 'var(--c-border-hi)'}`,
                          borderRadius: 6,
                          color: copied ? '#fff' : 'var(--c-text-dim)',
                          fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 0.18s',
                        }}
                      >
                        {copied ? '✓ Copied' : '⧉ Copy'}
                      </button>
                    </div>
                    {/* Prompt content */}
                    <pre style={{
                      margin: 0,
                      padding: '14px 16px',
                      background: 'var(--c-bg)',
                      border: '1px solid var(--c-border-hi)',
                      borderRadius: '0 0 8px 8px',
                      fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                      color: 'var(--c-text-dim)', lineHeight: 1.6,
                      overflowX: 'auto',
                      maxHeight: 320,
                      overflowY: 'auto',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}>
                      {SCAFFOLD_PROMPT}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Footer CTA */}
          <div style={{
            marginTop: 24,
            padding: '14px 18px',
            background: 'var(--c-surface-2)',
            border: '1px solid var(--c-border)',
            borderRadius: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
          }}>
            <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>
              Ready to add the generated content? Click <strong style={{ color: 'var(--c-text-dim)' }}>Add Entry</strong> to paste your output into a knowledge entry.
            </p>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              <button className="btn-ghost" style={{ fontSize: '0.75rem', padding: '6px 14px' }} onClick={onClose}>
                Close
              </button>
              <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 16px' }} onClick={() => { onClose(); onAddEntry() }}>
                + Add Entry
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Knowledge Base Tab ────────────────────────────────────────────────────────

function KnowledgeBaseTab({ appId }: { appId: string }) {
  const qc = useQueryClient()
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<KnowledgeEntry>>({})
  const [showAdd, setShowAdd] = useState(false)
  const [showScaffold, setShowScaffold] = useState(false)

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['app-knowledge', appId],
    queryFn: () => listKnowledge(appId),
  })

  const createMut = useMutation({
    mutationFn: (p: Partial<KnowledgeEntry>) => createKnowledge(appId, p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['app-knowledge', appId] }); setShowAdd(false); setForm({}) },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, p }: { id: string; p: Partial<KnowledgeEntry> }) => updateKnowledge(appId, id, p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['app-knowledge', appId] }); setEditId(null); setForm({}) },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteKnowledge(appId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-knowledge', appId] }),
  })

  const fs: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', padding: '7px 10px',
    background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
    borderRadius: 6, color: 'var(--c-text)', fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {showScaffold && (
        <KnowledgeScaffoldModal
          onClose={() => setShowScaffold(false)}
          onAddEntry={() => { setEditId(null); setForm({}); setShowAdd(true) }}
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--c-text-faint)', maxWidth: 600 }}>
          Site knowledge is injected into every investigation prompt for this application. Add architecture docs, service inventories, known gotchas, and infra facts.
          <span style={{ display: 'block', marginTop: 4, color: 'var(--c-text-faint)', fontSize: '0.72rem' }}>Disk-based knowledge/site.md is used as fallback when no entries exist here.</span>
        </p>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <button
            onClick={() => setShowScaffold(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: '0.75rem', padding: '6px 14px', whiteSpace: 'nowrap',
              background: 'var(--c-surface-3)',
              border: '1px solid var(--c-border-hi)',
              borderRadius: 6,
              color: 'var(--c-text-dim)',
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontWeight: 500,
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--c-signal)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--c-border-hi)')}
          >
            <span style={{ fontSize: '0.8rem' }}>⚡</span> Scaffold with Copilot
          </button>
          <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 14px', whiteSpace: 'nowrap' }} onClick={() => { setEditId(null); setForm({}); setShowAdd(true) }}>+ Add Entry</button>
        </div>
      </div>

      {isLoading && <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem' }}>Loading…</p>}
      {!isLoading && entries.length === 0 && (
        <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem', fontStyle: 'italic' }}>No knowledge entries. Using disk-based knowledge/site.md as fallback.</p>
      )}

      {entries.map(entry => (
        <div key={entry.id} style={{ padding: '12px 14px', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{ fontWeight: 700, fontSize: '0.82rem' }}>{entry.title}</span>
              {!entry.is_active && <span style={{ marginLeft: 8, fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>inactive</span>}
              <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', whiteSpace: 'pre-wrap', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{entry.content}</p>
            </div>
            <div style={{ display: 'flex', gap: 6, marginLeft: 12 }}>
              <button onClick={() => { setEditId(entry.id); setForm({ title: entry.title, content: entry.content, is_active: entry.is_active }); setShowAdd(true) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.8rem', padding: 4 }}>✎</button>
              <button onClick={() => { if (window.confirm(`Delete "${entry.title}"?`)) deleteMut.mutate(entry.id) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}>✕</button>
            </div>
          </div>
        </div>
      ))}

      {showAdd && (
        <div style={{ padding: 16, background: 'var(--c-surface)', border: '1px solid var(--c-border-hi)', borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem' }}>{editId ? 'Edit Entry' : 'New Knowledge Entry'}</div>
          <div>
            <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Title</label>
            <input style={fs} value={form.title ?? ''} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="e.g. AKS Cluster Layout" />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Content (Markdown)</label>
            <textarea style={{ ...fs, resize: 'vertical' }} rows={8} value={form.content ?? ''} onChange={e => setForm(f => ({ ...f, content: e.target.value }))} placeholder="# Architecture&#10;&#10;Describe your infrastructure, services, namespaces, monitoring endpoints…" />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 16px' }}
              onClick={() => { if (!form.title || !form.content) return; editId ? updateMut.mutate({ id: editId, p: form }) : createMut.mutate({ ...form, is_active: true }) }}
              disabled={createMut.isPending || updateMut.isPending}>
              {editId ? 'Save Changes' : 'Add Entry'}
            </button>
            <button className="btn-ghost" style={{ fontSize: '0.75rem', padding: '6px 14px' }} onClick={() => { setShowAdd(false); setEditId(null); setForm({}) }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Runbook Library Tab ───────────────────────────────────────────────────────

function RunbookLibraryTab({ appId, services }: { appId: string; services: ApplicationService[] }) {
  const qc = useQueryClient()
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<RunbookEntry>>({})
  const [showAdd, setShowAdd] = useState(false)

  const { data: runbooks = [], isLoading } = useQuery({
    queryKey: ['app-runbooks', appId],
    queryFn: () => listRunbooks(appId),
  })

  const createMut = useMutation({
    mutationFn: (p: Partial<RunbookEntry>) => createRunbook(appId, p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['app-runbooks', appId] }); setShowAdd(false); setForm({}) },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, p }: { id: string; p: Partial<RunbookEntry> }) => updateRunbook(appId, id, p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['app-runbooks', appId] }); setEditId(null); setForm({}) },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteRunbook(appId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-runbooks', appId] }),
  })

  const fs: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', padding: '7px 10px',
    background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
    borderRadius: 6, color: 'var(--c-text)', fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
  }

  const serviceOptions = services.map(s => s.service_name)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--c-text-faint)', maxWidth: 600 }}>
          Runbooks are matched to investigations by service or keywords and injected into the AI prompt.
          <span style={{ display: 'block', marginTop: 4, fontSize: '0.72rem' }}>Disk-based runbooks in knowledge/runbooks/ are used as fallback when no DB runbooks match.</span>
        </p>
        <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 14px', whiteSpace: 'nowrap' }} onClick={() => { setEditId(null); setForm({ keywords: [] }); setShowAdd(true) }}>+ Add Runbook</button>
      </div>

      {isLoading && <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem' }}>Loading…</p>}
      {!isLoading && runbooks.length === 0 && (
        <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem', fontStyle: 'italic' }}>No runbooks in DB. Disk-based runbooks in knowledge/runbooks/ are active as fallback.</p>
      )}

      {runbooks.map(rb => (
        <div key={rb.id} style={{ padding: '12px 14px', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontWeight: 700, fontSize: '0.82rem' }}>{rb.title}</span>
                {rb.service_name && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 4, padding: '1px 6px' }}>{rb.service_name}</span>}
                {!rb.is_active && <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>inactive</span>}
              </div>
              {rb.keywords.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4 }}>
                  {rb.keywords.map(kw => <span key={kw} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 4, padding: '1px 6px' }}>{kw}</span>)}
                </div>
              )}
              <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--c-text-faint)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{rb.content}</p>
            </div>
            <div style={{ display: 'flex', gap: 6, marginLeft: 12 }}>
              <button onClick={() => { setEditId(rb.id); setForm({ title: rb.title, content: rb.content, service_name: rb.service_name, keywords: rb.keywords, is_active: rb.is_active }); setShowAdd(true) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.8rem', padding: 4 }}>✎</button>
              <button onClick={() => { if (window.confirm(`Delete runbook "${rb.title}"?`)) deleteMut.mutate(rb.id) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }}>✕</button>
            </div>
          </div>
        </div>
      ))}

      {showAdd && (
        <div style={{ padding: 16, background: 'var(--c-surface)', border: '1px solid var(--c-border-hi)', borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem' }}>{editId ? 'Edit Runbook' : 'New Runbook'}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Title</label>
              <input style={fs} value={form.title ?? ''} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="e.g. OOM Kill Investigation" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Specific Service (optional)</label>
              <select style={fs} value={form.service_name ?? ''} onChange={e => setForm(f => ({ ...f, service_name: e.target.value || null }))}>
                <option value="">— All services (keyword match) —</option>
                {serviceOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Keywords (comma-separated, for generic runbooks)</label>
            <input style={fs} value={(form.keywords ?? []).join(', ')} onChange={e => setForm(f => ({ ...f, keywords: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))} placeholder="e.g. oom, memory, heap" />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Content (Markdown)</label>
            <textarea style={{ ...fs, resize: 'vertical' }} rows={10} value={form.content ?? ''} onChange={e => setForm(f => ({ ...f, content: e.target.value }))} placeholder="# Investigation Steps&#10;&#10;1. Check pod logs…&#10;2. …" />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 16px' }}
              onClick={() => { if (!form.title || !form.content) return; editId ? updateMut.mutate({ id: editId, p: form }) : createMut.mutate({ ...form, is_active: true, keywords: form.keywords ?? [] }) }}
              disabled={createMut.isPending || updateMut.isPending}>
              {editId ? 'Save Changes' : 'Add Runbook'}
            </button>
            <button className="btn-ghost" style={{ fontSize: '0.75rem', padding: '6px 14px' }} onClick={() => { setShowAdd(false); setEditId(null); setForm({}) }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Simulator Presets Tab ─────────────────────────────────────────────────────

function SimulatorPresetsTab({ appId, services }: { appId: string; services: ApplicationService[] }) {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<SimulatorPreset>>({})

  const { data: presets = [], isLoading } = useQuery({
    queryKey: ['simulator-presets', appId],
    queryFn: () => listSimulatorPresets(appId),
  })

  const createMut = useMutation({
    mutationFn: (payload: Partial<SimulatorPreset>) => createSimulatorPreset(appId, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['simulator-presets', appId] }); setShowAdd(false); setForm({}) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<SimulatorPreset> }) => updateSimulatorPreset(appId, id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['simulator-presets', appId] }); setEditId(null); setForm({}) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSimulatorPreset(appId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['simulator-presets', appId] }),
  })

  const serviceOptions = services.map(s => s.service_name)

  function openEdit(preset: SimulatorPreset) {
    setEditId(preset.id)
    setForm({ scenario_id: preset.scenario_id, label: preset.label, service_name: preset.service_name, environment: preset.environment, description: preset.description, icon_key: preset.icon_key ?? '', display_order: preset.display_order })
  }

  function handleSave() {
    if (!form.scenario_id || !form.label || !form.service_name || !form.environment || !form.description) return
    if (editId) {
      updateMut.mutate({ id: editId, payload: form })
    } else {
      createMut.mutate({ ...form, is_active: true, display_order: form.display_order ?? presets.length })
    }
  }

  const fieldStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', padding: '7px 10px',
    background: 'var(--c-surface-2)', border: '1px solid var(--c-border-hi)',
    borderRadius: 6, color: 'var(--c-text)', fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--c-text-faint)' }}>
          Manage the chaos scenarios shown in the Simulator panel. Each preset fires a full investigation pipeline.
        </p>
        <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 14px', whiteSpace: 'nowrap' }} onClick={() => { setEditId(null); setForm({}); setShowAdd(true) }}>
          + Add Preset
        </button>
      </div>

      {isLoading && <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem' }}>Loading…</p>}

      {!isLoading && presets.length === 0 && (
        <p style={{ margin: 0, color: 'var(--c-text-faint)', fontSize: '0.78rem', fontStyle: 'italic' }}>No presets yet. Add one to enable the Chaos Engineering Console.</p>
      )}

      {presets.map(preset => (
        <div key={preset.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '12px 14px', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem' }}>{preset.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--c-text-faint)', background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 4, padding: '1px 6px' }}>{preset.scenario_id}</span>
              {!preset.is_active && <span style={{ fontSize: '0.65rem', color: 'var(--c-text-faint)' }}>inactive</span>}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--c-text-faint)', marginBottom: 4 }}>
              {preset.service_name} / {preset.environment}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--c-text-dim)', lineHeight: 1.4 }}>{preset.description}</div>
          </div>
          <div style={{ display: 'flex', gap: 6, marginLeft: 12 }}>
            <button onClick={() => { openEdit(preset); setShowAdd(true) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.8rem', padding: 4 }} title="Edit">✎</button>
            <button onClick={() => { if (window.confirm(`Delete preset "${preset.label}"?`)) deleteMut.mutate(preset.id) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--c-text-faint)', fontSize: '0.9rem', padding: 4 }} title="Delete">✕</button>
          </div>
        </div>
      ))}

      {showAdd && (
        <div style={{ padding: 16, background: 'var(--c-surface)', border: '1px solid var(--c-border-hi)', borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '0.8rem', marginBottom: 4 }}>{editId ? 'Edit Preset' : 'New Preset'}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Scenario ID (slug)</label>
              <input style={fieldStyle} value={form.scenario_id ?? ''} onChange={e => setForm(f => ({ ...f, scenario_id: e.target.value }))} placeholder="e.g. hpa_failure" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Display Label</label>
              <input style={fieldStyle} value={form.label ?? ''} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} placeholder="e.g. Inject Scale Lag" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Service</label>
              <select style={fieldStyle} value={form.service_name ?? ''} onChange={e => setForm(f => ({ ...f, service_name: e.target.value }))}>
                <option value="">— Select service —</option>
                {serviceOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Environment</label>
              <input style={fieldStyle} value={form.environment ?? ''} onChange={e => setForm(f => ({ ...f, environment: e.target.value }))} placeholder="e.g. dev" />
            </div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.68rem', color: 'var(--c-text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Description</label>
            <textarea style={{ ...fieldStyle, resize: 'vertical' }} rows={2} value={form.description ?? ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="What does this scenario simulate?" />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-primary" style={{ fontSize: '0.75rem', padding: '6px 16px' }} onClick={handleSave} disabled={createMut.isPending || updateMut.isPending}>
              {editId ? 'Save Changes' : 'Add Preset'}
            </button>
            <button className="btn-ghost" style={{ fontSize: '0.75rem', padding: '6px 14px' }} onClick={() => { setShowAdd(false); setEditId(null); setForm({}) }}>Cancel</button>
          </div>
          {(createMut.isError || updateMut.isError) && (
            <p style={{ margin: 0, color: 'var(--c-red)', fontSize: '0.72rem', fontFamily: 'var(--font-mono)' }}>Save failed. Check all fields.</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Application Detail Panel ──────────────────────────────────────────────────

type Tab = 'services' | 'connectors' | 'notifications' | 'slo' | 'simulator_presets' | 'knowledge' | 'runbooks'

function AppDetail({ appId }: { appId: string }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('services')
  const [topologyOpen, setTopologyOpen] = useState(false)
  const { data: app, isLoading, isError } = useQuery({
    queryKey: ['application', appId],
    queryFn: () => getApplication(appId),
  })
  const deleteAppMut = useMutation({
    mutationFn: () => deleteApplication(appId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['applications'] })
      qc.removeQueries({ queryKey: ['application', appId] })
      navigate('/applications')
    },
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
    { key: 'knowledge', label: 'Knowledge Base' },
    { key: 'runbooks', label: 'Runbook Library' },
    { key: 'simulator_presets', label: 'Simulator Presets' },
  ]

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 12, padding: '20px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '1.25rem', marginBottom: 4 }}>{app.name}</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--c-text-muted)', marginBottom: 8 }}>
              {app.team_name || 'No team'} · <span style={{ fontFamily: 'var(--font-mono)' }}>{app.environment_default}</span>
            </div>
            {app.description && (
              <div style={{ fontSize: '0.8rem', color: 'var(--c-text-faint)', lineHeight: 1.5 }}>{app.description}</div>
            )}
          </div>
          <button
            className="btn-secondary"
            style={{ fontSize: '0.75rem', padding: '7px 14px', color: '#ef4444', borderColor: '#ef444455' }}
            onClick={() => {
              if (window.confirm(`Delete application \"${app.name}\"? This removes its services, connectors, SLOs, and notifications.`)) {
                deleteAppMut.mutate()
              }
            }}
            disabled={deleteAppMut.isPending}
            title="Delete application"
          >
            {deleteAppMut.isPending ? 'Deleting…' : 'Delete Application'}
          </button>
        </div>
      </div>

      <div style={{ background: 'var(--c-surface)', border: '1px solid var(--c-border)', borderRadius: 12, overflow: 'hidden' }}>
        <button
          onClick={() => setTopologyOpen(!topologyOpen)}
          style={{ width: '100%', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.9rem', color: 'var(--c-text)' }}
        >
          <span>Dependency Visualizer</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--c-text-faint)', transform: topologyOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
        </button>
        {topologyOpen && (
          <div style={{ borderTop: '1px solid var(--c-border)', paddingBottom: 16 }}>
            <TopologyRadar applicationId={appId} appTitle={app.name} appOnly />
          </div>
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
          {tab === 'knowledge' && <KnowledgeBaseTab appId={app.id} />}
          {tab === 'runbooks' && <RunbookLibraryTab appId={app.id} services={app.services ?? []} />}
          {tab === 'simulator_presets' && <SimulatorPresetsTab appId={app.id} services={app.services ?? []} />}
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
