import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { ApplicationHealthCard, HealthStatus } from "@/api/dashboardApi";
import { Sparkline } from "@/components/charts";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { cn } from "@/utils/cn";
import { formatPercentage } from "@/utils/formatters";

const ringColors: Record<HealthStatus, string> = {
  healthy: "var(--color-success-fill)",
  watch: "var(--color-info-fill)",
  degraded: "var(--color-warning-fill)",
  critical: "var(--color-danger-fill)",
};

/** Circular health indicator: the arc length is the health percentage, the colour its status. */
function HealthRing({ percentage, status, label }: { percentage: number; status: HealthStatus; label: string }) {
  const radius = 22;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="relative size-14 shrink-0" role="img" aria-label={label}>
      <svg viewBox="0 0 56 56" className="size-14 -rotate-90">
        <circle cx="28" cy="28" r={radius} fill="none" stroke="var(--color-hairline)" strokeWidth="5" />
        <circle cx="28" cy="28" r={radius} fill="none" stroke={ringColors[status]} strokeWidth="5" strokeLinecap="round" strokeDasharray={`${(circumference * percentage) / 100} ${circumference}`} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-body-sm font-semibold text-default tabular-nums">{percentage}</span>
    </div>
  );
}

export function ApplicationHealthCardView({ card }: { card: ApplicationHealthCard }) {
  const { t } = useTranslation("home");
  const { t: translateApplications } = useTranslation("applications");
  const budget = card.worstBudgetRemainingPercentage;
  return (
    <Card interactive dense className="flex flex-col gap-3 p-[var(--card-padding)]">
      <Link to={`/applications/${card.applicationId}`} className="flex items-start gap-3 rounded-md focus-visible:outline-2">
        <HealthRing percentage={card.healthPercentage} status={card.healthStatus} label={t("health.ringLabel", { percentage: card.healthPercentage, status: t(`health.status.${card.healthStatus}`) })} />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-body font-semibold text-default">{card.applicationName}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="rounded-sm bg-surface-sunken px-1.5 py-0.5 font-mono text-caption text-muted">{card.applicationCode}</span>
            <span className="text-caption text-muted">{t("health.tier", { tier: card.criticalityTier })}</span>
          </div>
        </div>
        {card.openIncidentCount > 0 ? <Badge tone="danger">{t("health.openIncidents", { count: card.openIncidentCount })}</Badge> : null}
      </Link>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-caption text-muted">{t("health.worstBudget")}</p>
          <p className={cn("text-body-sm font-semibold tabular-nums", budget !== null && budget < 0 ? "text-danger" : budget !== null && budget < 30 ? "text-warning" : "text-default")}>
            {budget === null ? t("health.noBudget") : formatPercentage(budget, { maximumFractionDigits: 0})}
          </p>
          {card.worstBudgetSloName ? <p className="max-w-40 truncate text-caption text-muted">{card.worstBudgetSloName}</p> : null}
        </div>
        {card.availabilitySparkline.length > 1 ? <Sparkline values={card.availabilitySparkline} width={110} height={32} ariaLabel={t("health.sparklineLabel", { name: card.applicationName })} /> : <span className="text-caption text-muted">{t("health.noTrend")}</span>}
      </div>
      {card.latestSignalTitle ? (
        <p className="flex items-start gap-1.5 text-caption text-muted"><AlertTriangle size={14} className="mt-px shrink-0 text-warning" aria-hidden />{card.latestSignalTitle}</p>
      ) : null}
      <div className="flex flex-wrap gap-1">{card.componentTypes.map((type) => <Badge key={type} tone="neutral">{translateApplications(`componentTypes.${type}`, { defaultValue: type.replaceAll("_", " ") })}</Badge>)}</div>
    </Card>
  );
}
