import { useTranslation } from "react-i18next";
import type { SloStatus, SloSummary } from "@/api/sloApi";
import { Sparkline } from "@/components/charts";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { formatNumber, formatPercentage } from "@/utils/formatters";

const statusTones: Record<SloStatus, StatusTone> = { healthy: "success", at_risk: "warning", breached: "danger", no_data: "neutral" };
const burnTone = (rate: number | null): StatusTone => (rate === null ? "neutral" : rate > 6 ? "danger" : rate > 1 ? "warning" : "success");

export function SloStatusChip({ status }: { status: SloStatus }) {
  const { t } = useTranslation("slo");
  return <StatusChip tone={statusTones[status]} size="sm" dot>{t(`status.${status}`)}</StatusChip>;
}

export function BurnChip({ label, rate }: { label: string; rate: number | null }) {
  const { t } = useTranslation("slo");
  return <StatusChip tone={burnTone(rate)} variant="outline" size="sm" icon={false}>{label} {rate === null ? t("card.noBurn") : `${rate.toFixed(1)}x`}</StatusChip>;
}

/** Compliance versus target, error budget bar with minutes left, 1 h and 6 h burn chips, sparkline and status. */
export function SloCard({ slo, onSelect, isHero = false }: { slo: SloSummary; onSelect: (sloId: string) => void; isHero?: boolean }) {
  const { t } = useTranslation("slo");
  const budget = slo.errorBudgetRemainingPercentage;
  const budgetTone = budget === null ? "brand" : budget < 0 ? "danger" : budget < 30 ? "warning" : "success";
  return (
    <Card interactive dense={!isHero} radius={isHero ? "xl" : "md"} accent={isHero} role="button" tabIndex={0} aria-label={slo.sliName}
      onClick={() => onSelect(slo.sloId)} onKeyDown={(event) => (event.key === "Enter" || event.key === " " ? onSelect(slo.sloId) : undefined)} className="flex cursor-pointer flex-col gap-3 p-[var(--card-padding)]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold">{slo.sliName}</p>
          <p className="truncate text-caption text-muted">{slo.applicationName} · {t("card.window", { days: slo.rollingWindowDays })}{slo.isApproximate ? ` · ${t("card.approximate")}` : ""}</p>
        </div>
        <SloStatusChip status={slo.status} />
      </div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className={isHero ? "text-display font-semibold" : "text-h2 font-semibold"}>{slo.compliancePercentage === null ? "–" : formatPercentage(slo.compliancePercentage, { maximumFractionDigits: 2 })}</p>
          <p className="text-caption text-muted">{t("card.target", { target: formatNumber(slo.targetPercentage, { maximumFractionDigits: 3 }) })}</p>
        </div>
        <Sparkline values={slo.sparkline} targetValue={slo.targetPercentage} width={isHero ? 160 : 96} height={isHero ? 44 : 28} ariaLabel={t("card.sparkline", { name: slo.sliName })} showArea />
      </div>
      <ProgressBar value={budget === null ? 0 : Math.max(0, Math.min(100, budget))} tone={budgetTone} size="sm" label={t("card.budget")}
        valueLabel={budget === null ? t("card.noData") : t("card.budgetLeft", { percent: Math.round(budget), minutes: Math.round(slo.errorBudgetRemainingMinutes ?? 0) })} />
      <div className="flex flex-wrap gap-1.5">
        <BurnChip label={t("card.burn1h")} rate={slo.burnRateOneHour} />
        <BurnChip label={t("card.burn6h")} rate={slo.burnRateSixHours} />
      </div>
    </Card>
  );
}
