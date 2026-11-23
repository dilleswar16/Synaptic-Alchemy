import { Gauge } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useIncidentBudgetImpact, type BudgetImpact, type BudgetImpactState } from "@/api/errorBudgetApi";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { formatDateTime, formatNumber } from "@/utils/formatters";
import { BreachPanel } from "./BreachPanel";
import { meterTone } from "./budgetImpactPresentation";

const stateTones: Record<BudgetImpactState, StatusTone> = { provisional: "info", final: "success", insufficient_data: "neutral" };

/** One SLO's row: the share as a meter with the policy threshold stated in words, and how the figure was worked out. */
function ImpactRow({ impact, thresholdPercent, minimumCoveragePercent }: { impact: BudgetImpact; thresholdPercent: number; minimumCoveragePercent: number }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const share = impact.budgetSharePercent;
  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-default">{impact.sliName}</p>
        <StatusChip tone={stateTones[impact.impactState]} size="sm">{t(`state.${impact.impactState}`)}</StatusChip>
      </div>
      {share === null ? (
        <p className="text-body-sm text-muted">{t("impact.notEnoughData", { coverage: formatNumber(impact.dataCoveragePercent, { maximumFractionDigits: 0 }), minimum: formatNumber(minimumCoveragePercent, { maximumFractionDigits: 0 }) })}</p>
      ) : (
        <>
          <div
            role="meter"
            aria-label={impact.sliName}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.min(100, share)}
            aria-valuetext={t("impact.share", { share: formatNumber(share, { maximumFractionDigits: 1 }), days: impact.budgetWindowDays })}
            className="relative h-2 w-full rounded-full bg-surface-sunken"
          >
            <div className={`h-2 rounded-full ${meterTone(share, thresholdPercent)}`} style={{ width: `${Math.min(100, share)}%` }} />
            <div aria-hidden className="absolute top-[-2px] h-3 w-0.5 bg-default" style={{ left: `${Math.min(100, thresholdPercent)}%` }} />
          </div>
          <p className="text-body text-default">{t("impact.share", { share: formatNumber(share, { maximumFractionDigits: 1 }), days: impact.budgetWindowDays })}</p>
        </>
      )}
      <details className="text-body-sm text-muted">
        <summary className="cursor-pointer text-action-subtle-text">{t("impact.howWorkedOut")}</summary>
        <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
          <div><dt className="inline">{t("impact.badEvents")}: </dt><dd className="inline">{formatNumber(impact.badEventCount)}</dd></div>
          <div><dt className="inline">{t("impact.budgetEvents")}: </dt><dd className="inline">{impact.budgetEventCount === null ? t("impact.none") : formatNumber(impact.budgetEventCount, { maximumFractionDigits: 0 })}</dd></div>
          <div><dt className="inline">{t("impact.target")}: </dt><dd className="inline">{formatNumber(impact.targetPercentage, { maximumFractionDigits: 3 })}%</dd></div>
          <div><dt className="inline">{t("impact.coverage")}: </dt><dd className="inline">{formatNumber(impact.dataCoveragePercent, { maximumFractionDigits: 0 })}%</dd></div>
          <div><dt className="inline">{t("impact.incidentWindow")}: </dt><dd className="inline">{formatDateTime(impact.impactWindowStart)} – {formatDateTime(impact.impactWindowEnd)}</dd></div>
          <div><dt className="inline">{t("impact.budgetWindow")}: </dt><dd className="inline">{t("impact.days", { count: impact.budgetWindowDays })}</dd></div>
          <div><dt className="inline">{t("impact.matched")}: </dt><dd className="inline">{impact.isServiceMatched ? t("impact.matchedByService") : t("impact.applicationWide")}</dd></div>
        </dl>
      </details>
    </li>
  );
}

/** What this incident cost each SLO's error budget. Shown whether or not the team turned the policy on: it is information first. */
export function BudgetImpactCard({ incidentId, postmortemId }: { incidentId: string; postmortemId?: string }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const { data, isLoading, isError, error, refetch } = useIncidentBudgetImpact(incidentId);
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (!data) return null;
  return (
    <Card radius="lg">
      <CardHeader title={t("impact.title")} description={data.policy.isEnabled ? t("impact.policyOn", { threshold: formatNumber(data.policy.singleIncidentThresholdPercent, { maximumFractionDigits: 0 }) }) : t("impact.policyOff")} actions={<Gauge size={18} aria-hidden className="text-muted" />} />
      <CardBody className="flex flex-col gap-4">
        {data.breach ? <BreachPanel breach={data.breach} incidentId={incidentId} postmortemId={postmortemId} /> : null}
        {data.impacts.length === 0 ? (
          <EmptyState icon={Gauge} title={t("impact.emptyTitle")} description={t("impact.emptyDescription")} />
        ) : (
          <>
            <ul className="divide-y divide-hairline">
              {data.impacts.map((impact) => <ImpactRow key={impact.sloId ?? impact.sliName} impact={impact} thresholdPercent={data.policy.singleIncidentThresholdPercent} minimumCoveragePercent={data.policy.minimumDataCoveragePercent} />)}
            </ul>
            <p className="mt-3 text-body-sm text-muted">{t("impact.overlapNote")}</p>
          </>
        )}
      </CardBody>
    </Card>
  );
}
