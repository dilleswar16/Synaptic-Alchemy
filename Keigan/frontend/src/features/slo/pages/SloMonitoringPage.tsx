import { useState } from "react";
import { Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSloDashboard } from "@/api/sloApi";
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
  const { applicationIds } = useApplicationScope();
  const dashboardQuery = useSloDashboard(applicationIds);
  const [selectedSloId, setSelectedSloId] = useState<string | null>(null);
  const slos = dashboardQuery.data ?? [];
  const headlines = slos.filter((slo) => slo.isHeadline);
  const others = slos.filter((slo) => !slo.isHeadline && slo.sliKind !== "supporting_signal");
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
      {dashboardQuery.isLoading ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-44 w-full" />)}</div> : null}
      {dashboardQuery.isError ? <ErrorState error={dashboardQuery.error} onRetry={() => dashboardQuery.refetch()} /> : null}
      {dashboardQuery.isSuccess && slos.length === 0 ? <EmptyState icon={Target} title={t("emptyTitle")} description={t("emptyDescription")} /> : null}
      {headlines.length > 0 ? (
        <section className="flex flex-col gap-3">
          <SectionHeader level={3} title={t("headline.title")} description={t("headline.description")} />
          <div className="grid gap-4 lg:grid-cols-2">{headlines.map((slo) => <SloCard key={slo.sloId} slo={slo} isHero onSelect={setSelectedSloId} />)}</div>
        </section>
      ) : null}
      {others.length > 0 ? (
        <section className="flex flex-col gap-3">
          <SectionHeader level={3} title={t("cards.title")} />
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{others.map((slo) => <SloCard key={slo.sloId} slo={slo} onSelect={setSelectedSloId} />)}</div>
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
