import { useState } from "react";
import { ChevronRight, Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useErrorBudgetBreaches } from "@/api/errorBudgetApi";
import { useSloDashboard, type SloSummary } from "@/api/sloApi";
import { Banner } from "@/components/ui/Banner";
import { useApplicationScope } from "@/auth/applicationScope";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { EcosystemHeatmap } from "../components/EcosystemHeatmap";
import { SloCard } from "../components/SloCard";
import { SloDetailDrawer } from "../components/SloDetailDrawer";

/** SLO monitoring: headline SLO hero, SLO cards (compliance vs target, budget, burn chips), detail drawer and the ecosystem heatmap. */
export default function SloMonitoringPage() {
  const { t } = useTranslation("slo");
  const { t: translateBudget } = useTranslation("errorBudgetPolicy");
  const { applicationIds } = useApplicationScope();
  const dashboardQuery = useSloDashboard(applicationIds);
  const exhausted = useErrorBudgetBreaches({ applicationIds, statuses: ["open"], kinds: ["budget_exhausted"] }).data ?? [];
  const [selectedSloId, setSelectedSloId] = useState<string | null>(null);
  const slos = dashboardQuery.data ?? [];
  const needsAttention = (slo: SloSummary) => slo.status === "breached" || slo.status === "at_risk";
  const attention = slos
    .filter((slo) => needsAttention(slo) && (slo.sliKind !== "supporting_signal" || slo.isHeadline))
    .sort((first, second) => Number(second.status === "breached") - Number(first.status === "breached") || (first.errorBudgetRemainingPercentage ?? 0) - (second.errorBudgetRemainingPercentage ?? 0));
  const headlines = slos.filter((slo) => slo.isHeadline && !needsAttention(slo));
  const others = slos.filter((slo) => !slo.isHeadline && !needsAttention(slo) && slo.sliKind !== "supporting_signal");
  const counts = { breached: slos.filter((slo) => slo.status === "breached").length, at_risk: slos.filter((slo) => slo.status === "at_risk").length, healthy: slos.filter((slo) => slo.status === "healthy").length };

  return (
    <div className="flex flex-col gap-8">
      <PageHeader title={t("pageTitle")} description={t("pageDescription")}>
        {slos.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            <StatusChip tone="danger" size="sm" dot>{t("summary.breached", { count: counts.breached })}</StatusChip>
            <StatusChip tone="warning" size="sm" dot>{t("summary.at_risk", { count: counts.at_risk })}</StatusChip>
            <StatusChip tone="success" size="sm" dot>{t("summary.healthy", { count: counts.healthy })}</StatusChip>
          </div>
        ) : null}
      </PageHeader>
      {exhausted.map((breach) => (
        <Banner key={breach.breachId} tone="danger" title={translateBudget("exhausted.title", { sli: breach.sliName ?? "", application: breach.applicationName })}>
          {breach.guidanceText ? translateBudget("exhausted.agreed", { guidance: breach.guidanceText }) : translateBudget("exhausted.noResponse")}
        </Banner>
      ))}
      {dashboardQuery.isLoading ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-44 w-full" />)}</div> : null}
      {dashboardQuery.isError ? <ErrorState error={dashboardQuery.error} onRetry={() => dashboardQuery.refetch()} /> : null}
      {dashboardQuery.isSuccess && slos.length === 0 ? <EmptyState icon={Target} title={t("emptyTitle")} description={t("emptyDescription")} /> : null}
      {slos.length > 0 ? (
        <section className="flex flex-col gap-3" aria-labelledby="slo-attention">
          <SectionHeader level={3} id="slo-attention" title={t("attention.title")} description={attention.length > 0 ? t("attention.description") : undefined} />
          {attention.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{attention.map((slo) => <SloCard key={slo.sloId} slo={slo} onSelect={setSelectedSloId} />)}</div>
          ) : (
            <p className="rounded-md border border-hairline bg-success-soft px-4 py-3 text-body-sm text-success">{t("attention.none")}</p>
          )}
        </section>
      ) : null}
      {headlines.length > 0 ? (
        <section className="flex flex-col gap-3">
          <SectionHeader level={3} title={t("headline.title")} description={t("headline.description")} />
          <div className="grid gap-4 lg:grid-cols-2">{headlines.map((slo) => <SloCard key={slo.sloId} slo={slo} isHero onSelect={setSelectedSloId} />)}</div>
        </section>
      ) : null}
      {others.length > 0 ? (
        <section className="flex flex-col gap-3">
          <details className="group flex flex-col gap-3">
            <summary className="flex w-fit cursor-pointer list-none items-center gap-2 rounded-md font-display text-h3 text-default focus-visible:outline-2 [&::-webkit-details-marker]:hidden">
              <ChevronRight size={18} aria-hidden className="transition-transform group-open:rotate-90" />
              {t("cards.showHealthy", { count: others.length })}
            </summary>
            <div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{others.map((slo) => <SloCard key={slo.sloId} slo={slo} onSelect={setSelectedSloId} />)}</div>
          </details>
        </section>
      ) : null}
      {slos.length > 0 ? (
        <section className="flex flex-col gap-3">
          <SectionHeader level={3} title={t("heatmap.title")} description={t("heatmap.description")} />
          <EcosystemHeatmap days={30} />
        </section>
      ) : null}
      <SloDetailDrawer slo={slos.find((slo) => slo.sloId === selectedSloId) ?? null} onClose={() => setSelectedSloId(null)} />
    </div>
  );
}
