/** The colour of the budget meter: calm while the share is well under the policy threshold, a warning as it nears it, danger once it is over. */
export function meterTone(sharePercent: number, thresholdPercent: number): string {
  if (sharePercent > thresholdPercent) return "bg-danger-fill";
  if (sharePercent >= thresholdPercent * 0.75) return "bg-warning-fill";
  return "bg-success-fill";
}
