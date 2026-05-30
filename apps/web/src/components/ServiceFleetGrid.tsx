/**
 * ServiceFleetGrid — responsive 6-column grid of ServiceCards.
 *
 * Data:
 *   - listSloStatus()      → SloStatusEntry[] (all SLO configs with latest snapshot)
 *   - fetchInvestigations() → InvestigationSummary[] (to tag "Corvin active" pulse)
 *
 * Controls:
 *   - Sort by: health (default) | service name | burn rate
 *   - Filter: All | Breaching | At Risk | Healthy
 *   - Search: free-text service name filter
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listSloStatus, fetchInvestigations, type SloStatusEntry } from '../api/client'
import { ServiceCard } from './ServiceCard'
import '../styles/ServiceFleetGrid.css'

type SortKey = 'health' | 'name' | 'burn'
type FilterKey = 'all' | 'breaching' | 'at_risk' | 'healthy' | 'no_data'

function healthOrder(entry: SloStatusEntry): number {
  const burn = entry.latest_snapshot?.burn_rate ?? -1
  if (burn > 1.2) return 0
  if (burn > 0.7) return 1
  if (burn >= 0)  return 2
  return 3
}

function matchesFilter(entry: SloStatusEntry, filter: FilterKey): boolean {
  const burn = entry.latest_snapshot?.burn_rate ?? null
  const measured = entry.latest_snapshot?.measured_pct ?? null
  if (filter === 'all') return true
  if (filter === 'no_data') return measured == null
  if (filter === 'breaching') return burn != null && burn > 1.2
  if (filter === 'at_risk') return burn != null && burn > 0.7 && burn <= 1.2
  if (filter === 'healthy') return burn != null && burn <= 0.7
  return true
}

export function ServiceFleetGrid() {
  const [sort, setSort] = useState<SortKey>('health')
  const [filter, setFilter] = useState<FilterKey>('all')
  const [search, setSearch] = useState('')

  const { data: sloList = [], isLoading: sloLoading } = useQuery({
    queryKey: ['slo-status'],
    queryFn: () => listSloStatus(),
    staleTime: 30_000,
  })

  const { data: investigations = [] } = useQuery({
    queryKey: ['investigations'],
    queryFn: fetchInvestigations,
    staleTime: 30_000,
  })

  // Services with a pending/approved investigation → show Corvin pulse dot
  const activeServices = useMemo(() => {
    return new Set(
      investigations
        .filter(i => i.approval_status === 'pending' || i.approval_status === 'approved')
        .map(i => i.service_name)
    )
  }, [investigations])

  // Deduplicate: prefer availability SLO over latency for each service
  const deduped = useMemo(() => {
    const map = new Map<string, SloStatusEntry>()
    for (const entry of sloList) {
      const key = entry.service_name
      const existing = map.get(key)
      if (!existing) {
        map.set(key, entry)
      } else if (entry.sli_type === 'availability') {
        // Prefer availability
        map.set(key, entry)
      }
    }
    return Array.from(map.values())
  }, [sloList])

  const filtered = useMemo(() => {
    return deduped
      .filter(e => matchesFilter(e, filter))
      .filter(e =>
        search.trim() === '' ||
        e.service_name.toLowerCase().includes(search.toLowerCase())
      )
  }, [deduped, filter, search])

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (sort === 'health') return healthOrder(a) - healthOrder(b)
      if (sort === 'name')   return a.service_name.localeCompare(b.service_name)
      if (sort === 'burn') {
        const ba = a.latest_snapshot?.burn_rate ?? -1
        const bb = b.latest_snapshot?.burn_rate ?? -1
        return bb - ba
      }
      return 0
    })
  }, [filtered, sort])

  const counts = useMemo(() => {
    const c = { all: deduped.length, breaching: 0, at_risk: 0, healthy: 0, no_data: 0 }
    for (const e of deduped) {
      const burn = e.latest_snapshot?.burn_rate ?? null
      if (burn == null) c.no_data++
      else if (burn > 1.2) c.breaching++
      else if (burn > 0.7) c.at_risk++
      else c.healthy++
    }
    return c
  }, [deduped])

  return (
    <div className="fleet-grid-container">
      {/* Controls */}
      <div className="fleet-controls">
        <div className="fleet-filters" role="tablist" aria-label="Filter services by health">
          {(['all', 'breaching', 'at_risk', 'healthy', 'no_data'] as FilterKey[]).map(f => (
            <button
              key={f}
              role="tab"
              aria-selected={filter === f}
              className={`fleet-filter-btn fleet-filter-${f} ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? `All (${counts.all})`
               : f === 'breaching' ? `Breaching (${counts.breaching})`
               : f === 'at_risk' ? `At Risk (${counts.at_risk})`
               : f === 'healthy' ? `Healthy (${counts.healthy})`
               : `No Data (${counts.no_data})`}
            </button>
          ))}
        </div>

        <div className="fleet-sort-search">
          <input
            className="fleet-search"
            type="search"
            placeholder="Search services…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            aria-label="Search services"
          />
          <select
            className="fleet-sort"
            value={sort}
            onChange={e => setSort(e.target.value as SortKey)}
            aria-label="Sort services by"
          >
            <option value="health">Sort: Health</option>
            <option value="name">Sort: Name</option>
            <option value="burn">Sort: Burn Rate</option>
          </select>
        </div>
      </div>

      {/* Grid */}
      {sloLoading ? (
        <div className="fleet-empty">Loading services…</div>
      ) : sorted.length === 0 ? (
        <div className="fleet-empty">
          {deduped.length === 0
            ? 'No services registered. Start the backend with CORVIN_DEMO_MODE=true to seed data.'
            : 'No services match your filter.'}
        </div>
      ) : (
        <div className="fleet-grid" role="list">
          {sorted.map(entry => (
            <div key={`${entry.service_name}-${entry.sli_type}`} role="listitem">
              <ServiceCard
                entry={entry}
                hasPendingInvestigation={activeServices.has(entry.service_name)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
