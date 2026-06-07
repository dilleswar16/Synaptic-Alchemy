/**
 * Shared hooks for loading application-scoped data from the API.
 *
 * useApplicationServices() — flat list of all services across all onboarded applications.
 * useApplicationPresets()  — flat list of all active simulator presets across all applications.
 * usePrimaryApplication()  — the first (or only) onboarded application, used when the UI
 *                            doesn't have a specific app context (e.g. dashboard widgets).
 *
 * All hooks return { data, loading, error } and use a simple in-memory cache
 * (same promise during a single page lifecycle) so multiple components can call
 * the same hook without triggering duplicate requests.
 */

import { useEffect, useState } from 'react'
import {
  listApplications,
  listEnvironments,
  listAllServices,
  listAllPresetsAcrossApplications,
  type Application,
  type ApplicationService,
  type ApplicationEnvironment,
  type SimulatorPreset,
} from '../api/client'

interface HookState<T> {
  data: T
  loading: boolean
  error: string | null
}

// ── Simple in-memory cache (per page load) ─────────────────────────────────

let _servicesPromise: Promise<Array<ApplicationService & { application_name: string; application_id: string }>> | null = null
let _presetsPromise: Promise<Array<SimulatorPreset & { application_name: string }>> | null = null
let _appsPromise: Promise<Application[]> | null = null

export function invalidateApplicationCache() {
  _servicesPromise = null
  _presetsPromise = null
  _appsPromise = null
}

// ── Hooks ──────────────────────────────────────────────────────────────────

export function useApplicationServices() {
  const [state, setState] = useState<HookState<Array<ApplicationService & { application_name: string; application_id: string }>>>({
    data: [],
    loading: true,
    error: null,
  })

  useEffect(() => {
    if (!_servicesPromise) {
      _servicesPromise = listAllServices()
    }
    _servicesPromise
      .then(data => setState({ data, loading: false, error: null }))
      .catch(err => setState({ data: [], loading: false, error: String(err) }))
  }, [])

  return state
}

export function useApplicationPresets() {
  const [state, setState] = useState<HookState<Array<SimulatorPreset & { application_name: string }>>>({
    data: [],
    loading: true,
    error: null,
  })

  useEffect(() => {
    if (!_presetsPromise) {
      _presetsPromise = listAllPresetsAcrossApplications()
    }
    _presetsPromise
      .then(data => setState({ data, loading: false, error: null }))
      .catch(err => setState({ data: [], loading: false, error: String(err) }))
  }, [])

  return state
}

export function usePrimaryApplication() {
  const [state, setState] = useState<HookState<Application | null>>({
    data: null,
    loading: true,
    error: null,
  })

  useEffect(() => {
    if (!_appsPromise) {
      _appsPromise = listApplications()
    }
    _appsPromise
      .then(apps => setState({ data: apps[0] ?? null, loading: false, error: null }))
      .catch(err => setState({ data: null, loading: false, error: String(err) }))
  }, [])

  return state
}

/** Return unique service names from the services list (for use as dropdown options). */
export function useServiceNames(): { names: string[]; loading: boolean } {
  const { data, loading } = useApplicationServices()
  const names = Array.from(new Set(data.map(s => s.service_name))).sort()
  return { names, loading }
}

/** Return the environment_default of the primary application. */
export function useDefaultEnvironment(): string {
  const { data } = usePrimaryApplication()
  return data?.environment_default ?? ''
}

/**
 * Return the list of environments defined for the primary application.
 * Falls back to empty list if no environments are configured yet.
 * Used to populate environment dropdowns throughout the UI.
 */
export function useApplicationEnvironments(): { environments: ApplicationEnvironment[]; loading: boolean } {
  const { data: app, loading: appLoading } = usePrimaryApplication()
  const [environments, setEnvironments] = useState<ApplicationEnvironment[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!app) return
    setLoading(true)
    listEnvironments(app.id)
      .then(envs => setEnvironments(envs))
      .catch(() => setEnvironments([]))
      .finally(() => setLoading(false))
  }, [app?.id])

  return { environments, loading: appLoading || loading }
}

/**
 * Return environment names as simple strings for use in select dropdowns.
 * If no environments defined in DB, falls back to a sensible default list.
 */
export function useEnvironmentOptions(): string[] {
  const { environments } = useApplicationEnvironments()
  if (environments.length > 0) {
    return environments
      .sort((a, b) => a.display_order - b.display_order)
      .map(e => e.name)
  }
  // Fallback until the customer defines their environments
  return ['production', 'staging', 'dev']
}
