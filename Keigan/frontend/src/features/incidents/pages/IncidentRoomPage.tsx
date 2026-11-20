import { useMemo, useState } from "react";
import { Plus, Siren } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { useIncidents } from "@/api/incidentsApi";
import { useApplicationScope } from "@/auth/applicationScope";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { IncidentBoard } from "../components/IncidentBoard";
import { IncidentFilterBar, type IncidentFilterState, type IncidentView } from "../components/IncidentFilterBar";
import { IncidentTable } from "../components/IncidentTable";
import { NewInvestigationDialog } from "../components/NewInvestigationDialog";

const PAGE_SIZE = 25;
const splitList = (value: string | null) => (value ? value.split(",").filter(Boolean) : []);

/** Incident room (spec 7.5): URL-synced filters, table and board views, live refetch, manual investigations. */
export default function IncidentRoomPage() {
  const { t } = useTranslation("incidents");
  const [searchParams, setSearchParams] = useSearchParams();
  const { applicationIds } = useApplicationScope();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const filters: IncidentFilterState = useMemo(
    () => ({
      search: searchParams.get("search") ?? "",
      priorities: splitList(searchParams.get("priorities")),
      statuses: splitList(searchParams.get("statuses")),
      sources: splitList(searchParams.get("sources")),
      onlyMine: searchParams.get("onlyMine") === "1",
      view: (searchParams.get("view") === "board" ? "board" : "table") as IncidentView,
    }),
    [searchParams],
  );
  const page = Number(searchParams.get("page") ?? "1") || 1;
  const debouncedSearch = useDebouncedValue(filters.search, 300);

  const updateFilters = (changes: Partial<IncidentFilterState>) => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        const merged = { ...filters, ...changes };
        const assign = (key: string, value: string) => (value ? next.set(key, value) : next.delete(key));
        assign("search", merged.search);
        assign("priorities", merged.priorities.join(","));
        assign("statuses", merged.statuses.join(","));
        assign("sources", merged.sources.join(","));
        assign("onlyMine", merged.onlyMine ? "1" : "");
        assign("view", merged.view === "board" ? "board" : "");
        next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  const isBoard = filters.view === "board";
  const incidentsQuery = useIncidents({
    applicationIds,
    priorities: filters.priorities,
    statuses: filters.statuses,
    sources: filters.sources,
    search: debouncedSearch || undefined,
    onlyMine: filters.onlyMine || undefined,
    page: isBoard ? 1 : page,
    pageSize: isBoard ? 100 : PAGE_SIZE,
  });
  const incidents = incidentsQuery.data?.items ?? [];
  const hasFilters = Boolean(filters.search || filters.priorities.length || filters.statuses.length || filters.sources.length || filters.onlyMine);

  return (
    <>
      <PageHeader
        title={t("pageTitle")}
        description={t("pageDescription")}
        actions={<Button leadingIcon={Plus} onClick={() => setIsDialogOpen(true)}>{t("newInvestigation.open")}</Button>}
      />
      <IncidentFilterBar filters={filters} onChange={updateFilters} />
      {incidentsQuery.isError && !incidentsQuery.data ? (
        <ErrorState error={incidentsQuery.error} onRetry={() => void incidentsQuery.refetch()} isRetrying={incidentsQuery.isFetching} />
      ) : !incidentsQuery.isLoading && incidents.length === 0 && !hasFilters ? (
        <EmptyState icon={Siren} title={t("empty.noIncidentsTitle")} description={t("empty.noIncidentsDescription")} action={<Button variant="secondary" onClick={() => setIsDialogOpen(true)}>{t("newInvestigation.open")}</Button>} isBordered />
      ) : isBoard ? (
        <IncidentBoard incidents={incidents} isLoading={incidentsQuery.isLoading} />
      ) : (
        <IncidentTable
          incidents={incidents}
          isLoading={incidentsQuery.isLoading}
          totalCount={incidentsQuery.data?.totalCount ?? 0}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={(nextPage) => setSearchParams((previous) => { const next = new URLSearchParams(previous); next.set("page", String(nextPage)); return next; }, { replace: true })}
        />
      )}
      <NewInvestigationDialog open={isDialogOpen} onOpenChange={setIsDialogOpen} defaultApplicationId={applicationIds.length === 1 ? applicationIds[0] : undefined} />
    </>
  );
}
