import { useTranslation } from "react-i18next";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import type { FunnelStep } from "@/api/alertsApi";

const severityTones: StatusTone[] = ["danger", "danger", "warning", "info", "neutral"];

export function SeverityChip({ level }: { level: number }) {
  const { t } = useTranslation("alerts");
  return <StatusChip tone={severityTones[level] ?? "neutral"} size="sm" icon={false}>{t("severity", { level })}</StatusChip>;
}

export function GroupStatusChip({ status }: { status: string }) {
  const { t } = useTranslation("alerts");
  const tone: StatusTone = status === "open" ? "alert" : status === "queued" ? "warning" : "success";
  return <StatusChip tone={tone} size="sm" dot>{t(`groupStatus.${status}`)}</StatusChip>;
}

/** Score bar: the number plus a bar scaled to the highest possible score (about 90). */
export function ScoreBar({ score }: { score: number }) {
  const tone = score >= 40 ? "danger" : score >= 15 ? "warning" : "brand";
  return <ProgressBar value={Math.min(100, (score / 90) * 100)} tone={tone} size="xs" valueLabel={score.toFixed(1)} showValue className="min-w-24" aria-label={String(score)} />;
}

export function useFunnelStepLabel() {
  const { t } = useTranslation("alerts");
  return (step: FunnelStep) => t(`funnel.steps.${step.stepKey}`, { defaultValue: step.stepLabel });
}

export function useOutcomeLabel() {
  const { t } = useTranslation("alerts");
  return (outcome: string | null) => (outcome ? t(`outcome.${outcome}`, { defaultValue: outcome.replace(/_/g, " ") }) : "");
}
