/**
 * StatusBadge — reusable approval status chip.
 * Used on InvestigationDetailPage, DashboardPage, InvestigationsPage.
 */

const STATUS_ICONS: Record<string, string> = {
  pending: '◎', approved: '✓', rejected: '✗', executed: '▶',
}
const STATUS_CLS: Record<string, string> = {
  pending: 'badge-pending', approved: 'badge-approved',
  rejected: 'badge-rejected', executed: 'badge-executed',
}

export function StatusBadge({ status }: { status: string }) {
  const icon = STATUS_ICONS[status] ?? '○'
  return (
    <span className={`badge ${STATUS_CLS[status] ?? 'badge-pending'}`}>
      {icon} {status}
    </span>
  )
}

export { STATUS_CLS }
