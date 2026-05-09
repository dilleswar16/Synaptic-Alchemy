/**
 * Shared time-formatting utilities.
 * Single source of truth — imported by Dashboard, Investigations, and detail pages.
 */

/** "HH:MM:SSZ" from an ISO string */
export function fmtTs(iso: string): string {
  try { return new Date(iso).toISOString().substring(11, 19) + 'Z' } catch { return '—' }
}

/** "Xm ago / Xh ago / Xd ago" from an ISO string */
export function timeAgo(iso: string): string {
  try {
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
    if (s < 60)    return `${s}s ago`
    if (s < 3600)  return `${Math.floor(s / 60)}m ago`
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`
    return `${Math.floor(s / 86400)}d ago`
  } catch { return '—' }
}

/** "+Xm Ys" elapsed between two ISO strings */
export function deltaLabel(from: string, to: string): string {
  const ms = new Date(to).getTime() - new Date(from).getTime()
  if (ms <= 0) return ''
  const s = Math.round(ms / 1000)
  if (s < 60) return `+${s}s`
  const m = Math.floor(s / 60), r = s % 60
  return r > 0 ? `+${m}m ${r}s` : `+${m}m`
}

/** "Xm Ys" total duration between two ISO strings */
export function totalDuration(from: string, to: string): string {
  const ms = new Date(to).getTime() - new Date(from).getTime()
  if (ms <= 0) return '0s'
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60), r = s % 60
  return r > 0 ? `${m}m ${r}s` : `${m}m`
}

/** Short ISO time without seconds: "HH:MMZ" */
export function fmtShortTime(iso: string): string {
  try { return new Date(iso).toISOString().substring(11, 16) + 'Z' } catch { return '—' }
}

/** "YYYY-MM-DD" date portion */
export function fmtDate(iso: string): string {
  try { return iso.slice(0, 10) } catch { return '—' }
}
