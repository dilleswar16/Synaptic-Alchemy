import { useMemo, useState } from "react";
import { LayoutGrid, Plus, Rows3, Search, SendHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { useApplications, type ApplicationSummary } from "@/api/applicationsApi";
import { useAccessControl } from "@/auth/accessControl";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatPercentage } from "@/utils/formatters";
import { CreateApplicationDialog } from "../components/CreateApplicationDialog";
import { componentTypeIcon, lifecycleTone } from "../components/lifecycle";

type ViewMode = "grid" | "table";

function ComponentTypeIcons({ application, isLabelled = false }: { application: ApplicationSummary; isLabelled?: boolean }) {
  const { t } = useTranslation("applications");
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted">
      {application.componentTypes.map((componentType) => {
        const Icon = componentTypeIcon[componentType];
        const label = t(`componentTypes.${componentType}`);
        return (
          <span key={componentType} title={label} className="inline-flex items-center gap-1.5 text-caption">
            <Icon size={16} aria-label={label} />
            {isLabelled ? <span>{label}</span> : null}
          </span>
        );
      })}
    </span>
  );
}

function ReadinessSummary({ application }: { application: ApplicationSummary }) {
  const { t } = useTranslation("applications");
  if (application.requiredTotalCount === null || application.requiredDoneCount === null) return null;
  return (
    <ProgressBar
      size="xs"
      value={(application.requiredDoneCount / Math.max(1, application.requiredTotalCount)) * 100}
      label={t("card.readiness", { done: application.requiredDoneCount, total: application.requiredTotalCount })}
    />
  );
}

function SloCompliance({ value }: { value: number | null }) {
  return <span className="tabular-nums">{value === null ? "—" : formatPercentage(value, { maximumFractionDigits: 1 })}</span>;
}

export default function ApplicationsPage() {
  const { t } = useTranslation("applications");
  const navigate = useNavigate();
  const { isKeiganAdmin } = useAccessControl();
  const applicationsQuery = useApplications();
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [searchText, setSearchText] = useState("");
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const filteredApplications = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    return (applicationsQuery.data ?? []).filter(
      (application) => !needle || application.applicationName.toLowerCase().includes(needle) || application.applicationCode.toLowerCase().includes(needle),
    );
  }, [applicationsQuery.data, searchText]);

  const openWorkspace = (application: ApplicationSummary) => navigate(`/applications/${application.applicationId}/${application.lifecycleStatus === "live" ? "review" : "components"}`);

  const columns: DataTableColumn<ApplicationSummary>[] = [
    { key: "name", header: t("columns.application"), isSticky: true, sortValue: (row) => row.applicationName, cell: (row) => <span className="font-semibold">{row.applicationName}</span> },
    { key: "code", header: t("columns.code"), sortValue: (row) => row.applicationCode, cell: (row) => <span className="font-mono text-body-sm">{row.applicationCode}</span> },
    { key: "region", header: t("columns.region"), sortValue: (row) => row.regionCode, cell: (row) => row.regionCode ?? "—" },
    { key: "lifecycle", header: t("columns.lifecycle"), sortValue: (row) => row.lifecycleStatus, cell: (row) => <StatusChip tone={lifecycleTone[row.lifecycleStatus]} dot>{t(`lifecycle.${row.lifecycleStatus}`)}</StatusChip> },
    { key: "components", header: t("columns.components"), cell: (row) => <ComponentTypeIcons application={row} /> },
    { key: "services", header: t("columns.services"), align: "end", sortValue: (row) => row.serviceCount, cell: (row) => row.serviceCount },
    { key: "slo", header: t("columns.slo"), align: "end", sortValue: (row) => row.sloCompliancePercentage, cell: (row) => <SloCompliance value={row.sloCompliancePercentage} /> },
    { key: "incidents", header: t("columns.incidents"), align: "end", sortValue: (row) => row.openIncidentCount, cell: (row) => row.openIncidentCount },
    { key: "readiness", header: t("columns.readiness"), width: "180px", cell: (row) => <ReadinessSummary application={row} /> },
  ];

  return (
    <>
      <PageHeader
        title={t("pageTitle")}
        description={t("pageDescription")}
        actions={
          <Button leadingIcon={isKeiganAdmin ? Plus : SendHorizontal} onClick={() => setIsDialogOpen(true)}>
            {isKeiganAdmin ? t("onboardApplication") : t("requestOnboarding")}
          </Button>
        }
      >
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Input aria-label={t("search")} placeholder={t("search")} leadingIcon={Search} size="sm" value={searchText} onChange={(event) => setSearchText(event.target.value)} containerClassName="w-72" />
          <SegmentedControl
            aria-label={t("view.label")}
            size="sm"
            value={viewMode}
            onValueChange={setViewMode}
            options={[
              { value: "grid", label: t("view.grid"), icon: LayoutGrid },
              { value: "table", label: t("view.table"), icon: Rows3 },
            ]}
          />
        </div>
      </PageHeader>

      {applicationsQuery.isError ? (
        <ErrorState error={applicationsQuery.error} onRetry={() => void applicationsQuery.refetch()} />
      ) : applicationsQuery.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-44 rounded-lg" />)}</div>
      ) : filteredApplications.length === 0 ? (
        <EmptyState
          isBordered
          title={searchText ? t("empty.noMatchTitle") : t("empty.title")}
          description={searchText ? t("empty.noMatchDescription") : t("empty.description")}
          action={!searchText ? <Button leadingIcon={Plus} onClick={() => setIsDialogOpen(true)}>{isKeiganAdmin ? t("onboardApplication") : t("requestOnboarding")}</Button> : undefined}
        />
      ) : viewMode === "table" ? (
        <DataTable columns={columns} rows={filteredApplications} getRowId={(row) => row.applicationId} caption={t("pageTitle")} onRowClick={openWorkspace} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredApplications.map((application) => (
            <Card key={application.applicationId} interactive className="h-full">
              <Link to={`/applications/${application.applicationId}/${application.lifecycleStatus === "live" ? "review" : "components"}`} className="flex h-full flex-col gap-4 rounded-md p-[var(--card-padding)] outline-none focus-visible:ring-2 focus-visible:ring-action">
                <div className="flex items-start justify-between gap-3">
                  <h3 title={application.applicationName} className="line-clamp-2 min-w-0 break-words font-display text-h3 font-semibold text-default">{application.applicationName}</h3>
                  <StatusChip tone={lifecycleTone[application.lifecycleStatus]} dot className="shrink-0">{t(`lifecycle.${application.lifecycleStatus}`)}</StatusChip>
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-caption text-muted">
                    <span className="rounded bg-sunken px-1.5 py-0.5 font-mono">{application.applicationCode}</span>
                    {application.regionCode ? <span>{t(`regions.${application.regionCode}`, { defaultValue: application.regionCode })}</span> : null}
                  </div>
                  <ComponentTypeIcons application={application} isLabelled />
                </div>
                <div className="mt-auto flex flex-col gap-4">
                  <dl className="grid grid-cols-3 gap-2 border-t border-hairline pt-4">
                    <div className="min-w-0"><dt className="truncate text-caption text-muted">{t("card.services")}</dt><dd className="mt-0.5 text-h3 font-semibold tabular-nums">{application.serviceCount}</dd></div>
                    <div className="min-w-0"><dt className="truncate text-caption text-muted">{t("card.sloMet")}</dt><dd className="mt-0.5 text-h3 font-semibold"><SloCompliance value={application.sloCompliancePercentage} /></dd></div>
                    <div className="min-w-0"><dt className="truncate text-caption text-muted">{t("card.incidents")}</dt><dd className="mt-0.5 text-h3 font-semibold tabular-nums">{application.openIncidentCount}</dd></div>
                  </dl>
                  <ReadinessSummary application={application} />
                </div>
              </Link>
            </Card>
          ))}
        </div>
      )}

      <CreateApplicationDialog open={isDialogOpen} onOpenChange={setIsDialogOpen} isRequest={!isKeiganAdmin} />
    </>
  );
}
