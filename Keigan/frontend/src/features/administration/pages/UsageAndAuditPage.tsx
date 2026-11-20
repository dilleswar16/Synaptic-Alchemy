import { useState } from "react";
import { Coins, Cpu, RotateCw, Sigma, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuditEvents, useJobStats, useRetryJob, useUsage, type AuditEvent, type BackgroundJobSummary, type UsageBucket } from "@/api/administrationApi";
import { BarChart } from "@/components/charts";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { StatusChip } from "@/components/ui/StatusChip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { formatCompactNumber, formatDateTime, formatNumber } from "@/utils/formatters";

const currencyFormatter = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });

function UsageBucketTable({ groupBy, caption }: { groupBy: "application" | "feature"; caption: string }) {
  const { t } = useTranslation("administration");
  const usage = useUsage(groupBy, 30);
  const columns: DataTableColumn<UsageBucket>[] = [
    { key: "label", header: t("usage.columns.name"), cell: (row) => row.bucketLabel, isSortable: true, sortValue: (row) => row.bucketLabel },
    { key: "calls", header: t("usage.columns.calls"), align: "end", cell: (row) => formatNumber(row.callCount), isSortable: true, sortValue: (row) => row.callCount },
    { key: "input", header: t("usage.columns.input"), align: "end", cell: (row) => formatCompactNumber(row.inputTokenCount), isSortable: true, sortValue: (row) => row.inputTokenCount },
    { key: "output", header: t("usage.columns.output"), align: "end", cell: (row) => formatCompactNumber(row.outputTokenCount), isSortable: true, sortValue: (row) => row.outputTokenCount },
    { key: "cost", header: t("usage.columns.cost"), align: "end", cell: (row) => currencyFormatter.format(row.estimatedCost), isSortable: true, sortValue: (row) => row.estimatedCost },
  ];
  return <DataTable caption={caption} columns={columns} rows={usage.data?.buckets ?? []} getRowId={(row) => row.bucketKey} isLoading={usage.isLoading} density="dense" emptyState={<p className="p-4 text-body-sm text-muted">{t("usage.empty")}</p>} />;
}

function UsageTab() {
  const { t } = useTranslation("administration");
  const [days, setDays] = useState<7 | 14 | 30>(14);
  const usage = useUsage("day", days);
  if (usage.isError) return <ErrorState error={usage.error} onRetry={() => void usage.refetch()} />;
  const data = usage.data;
  return (
    <div className="flex flex-col gap-6">
      <SegmentedControl<string> aria-label={t("usage.range")} value={String(days)} onValueChange={(value) => setDays(Number(value) as 7 | 14 | 30)} options={[{ value: "7", label: t("usage.days", { count: 7 }) }, { value: "14", label: t("usage.days", { count: 14 }) }, { value: "30", label: t("usage.days", { count: 30 }) }]} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {!data ? [0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-28" />) : (
          <>
            <StatTile icon={Sigma} label={t("usage.tiles.tokens")} value={formatCompactNumber(data.totalInputTokenCount + data.totalOutputTokenCount)} secondaryText={t("usage.tiles.tokenSplit", { input: formatCompactNumber(data.totalInputTokenCount), output: formatCompactNumber(data.totalOutputTokenCount) })} />
            <StatTile icon={Coins} iconTone="success" label={t("usage.tiles.cost")} value={currencyFormatter.format(data.totalEstimatedCost)} secondaryText={t("usage.tiles.costNote")} />
            <StatTile icon={Zap} iconTone="ai" label={t("usage.tiles.calls")} value={formatNumber(data.totalCallCount)} secondaryText={t("usage.tiles.failedCalls", { count: data.failedCallCount })} secondaryTone={data.failedCallCount ? "negative" : "default"} />
            <StatTile icon={Cpu} iconTone="info" label={t("usage.tiles.perInvestigation")} value={data.averageTokensPerInvestigation === null ? "—" : formatCompactNumber(data.averageTokensPerInvestigation)} secondaryText={t("usage.tiles.perInvestigationNote")} />
          </>
        )}
      </div>
      <Card>
        <CardHeader title={t("usage.chartTitle")} description={t("usage.chartDescription")} />
        <CardBody>
          {!data ? <Skeleton className="h-56" /> : data.buckets.length === 0 ? <p className="text-body-sm text-muted">{t("usage.empty")}</p> : (
            <BarChart ariaLabel={t("usage.chartTitle")} data={data.buckets.map((bucket) => ({ ...bucket }))} categoryKey="bucketLabel" stacked height={240} valueFormatter={(value) => formatCompactNumber(value)} series={[{ key: "inputTokenCount", label: t("usage.columns.input") }, { key: "outputTokenCount", label: t("usage.columns.output") }]} />
          )}
        </CardBody>
      </Card>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card><CardHeader title={t("usage.byApplication")} /><CardBody><UsageBucketTable groupBy="application" caption={t("usage.byApplication")} /></CardBody></Card>
        <Card><CardHeader title={t("usage.byFeature")} /><CardBody><UsageBucketTable groupBy="feature" caption={t("usage.byFeature")} /></CardBody></Card>
      </div>
    </div>
  );
}

function AuditTab() {
  const { t } = useTranslation("administration");
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const debouncedActor = useDebouncedValue(actor, 300);
  const debouncedAction = useDebouncedValue(action, 300);
  const audit = useAuditEvents({ actor: debouncedActor, action: debouncedAction, page, pageSize: 25 });
  const columns: DataTableColumn<AuditEvent>[] = [
    { key: "time", header: t("audit.columns.time"), cell: (row) => formatDateTime(row.occurredAt, { dateStyle: "short", timeStyle: "medium" }), width: "11rem" },
    { key: "actor", header: t("audit.columns.actor"), cell: (row) => row.actorUserPrincipalName },
    { key: "action", header: t("audit.columns.action"), cell: (row) => <span className="font-mono text-caption">{row.actionName}</span> },
    { key: "target", header: t("audit.columns.target"), cell: (row) => (row.targetEntityType ? `${row.targetEntityType}${row.targetEntityId ? ` ${row.targetEntityId.slice(0, 8)}` : ""}` : "—") },
    { key: "details", header: t("audit.columns.details"), cell: (row) => <span className="block max-w-80 truncate font-mono text-caption text-muted" title={row.actionDetails ? JSON.stringify(row.actionDetails) : undefined}>{row.actionDetails ? JSON.stringify(row.actionDetails) : "—"}</span> },
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Input label={t("audit.filters.actor")} value={actor} onChange={(event) => { setActor(event.target.value); setPage(1); }} placeholder="name@company.com" />
        <Input label={t("audit.filters.action")} value={action} onChange={(event) => { setAction(event.target.value); setPage(1); }} placeholder="application.update" />
      </div>
      {audit.isError ? <ErrorState error={audit.error} onRetry={() => void audit.refetch()} /> : (
        <DataTable caption={t("audit.caption")} columns={columns} rows={audit.data?.items ?? []} getRowId={(row) => row.auditEventId} isLoading={audit.isLoading} density="dense"
          serverPagination={{ page, pageSize: 25, totalCount: audit.data?.totalCount ?? 0, onPageChange: setPage }} emptyState={<p className="p-4 text-body-sm text-muted">{t("audit.empty")}</p>} />
      )}
    </div>
  );
}

function JobsTab() {
  const { t } = useTranslation("administration");
  const jobs = useJobStats();
  const retryJob = useRetryJob();
  if (jobs.isError) return <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />;
  const columns = (canRetry: boolean): DataTableColumn<BackgroundJobSummary>[] => [
    { key: "type", header: t("jobs.columns.type"), cell: (row) => <span className="font-mono text-caption">{row.jobType}</span> },
    { key: "status", header: t("jobs.columns.status"), cell: (row) => <StatusChip size="sm" tone={row.jobStatus === "succeeded" ? "success" : row.jobStatus === "dead_lettered" || row.jobStatus === "failed" ? "danger" : "info"}>{row.jobStatus.replaceAll("_", " ")}</StatusChip> },
    { key: "attempts", header: t("jobs.columns.attempts"), align: "end", cell: (row) => `${row.attemptCount}/${row.maximumAttemptCount}` },
    { key: "created", header: t("jobs.columns.created"), cell: (row) => formatDateTime(row.createdAt, { dateStyle: "short", timeStyle: "medium" }) },
    { key: "error", header: t("jobs.columns.error"), cell: (row) => <span className="block max-w-96 truncate text-caption text-muted" title={row.lastErrorMessage ?? undefined}>{row.lastErrorMessage ?? "—"}</span> },
    ...(canRetry ? [{ key: "retry", header: "", align: "end" as const, cell: (row: BackgroundJobSummary) => <Button size="sm" variant="secondary" leadingIcon={RotateCw} isLoading={retryJob.isPending && retryJob.variables === row.jobId} onClick={() => retryJob.mutate(row.jobId)}>{t("jobs.retry")}</Button> }] : []),
  ];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-2">
        {Object.entries(jobs.data?.countsByStatus ?? {}).map(([status, count]) => <StatusChip key={status} tone={status === "dead_lettered" ? "danger" : status === "succeeded" ? "success" : "info"}>{`${status.replaceAll("_", " ")}: ${count}`}</StatusChip>)}
      </div>
      <Card>
        <CardHeader title={t("jobs.deadLetters")} description={t("jobs.deadLettersDescription")} />
        <CardBody><DataTable caption={t("jobs.deadLetters")} columns={columns(true)} rows={jobs.data?.deadLetters ?? []} getRowId={(row) => row.jobId} isLoading={jobs.isLoading} density="dense" emptyState={<p className="p-4 text-body-sm text-muted">{t("jobs.noDeadLetters")}</p>} /></CardBody>
      </Card>
      <Card>
        <CardHeader title={t("jobs.recent")} />
        <CardBody><DataTable caption={t("jobs.recent")} columns={columns(false)} rows={jobs.data?.recentJobs ?? []} getRowId={(row) => row.jobId} isLoading={jobs.isLoading} density="dense" /></CardBody>
      </Card>
    </div>
  );
}

export default function UsageAndAuditPage() {
  const { t } = useTranslation("administration");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("usage.pageTitle")} description={t("usage.pageDescription")} />
      <Tabs defaultValue="usage">
        <TabsList>
          <TabsTrigger value="usage">{t("tabs.usage")}</TabsTrigger>
          <TabsTrigger value="audit">{t("tabs.audit")}</TabsTrigger>
          <TabsTrigger value="jobs">{t("tabs.jobs")}</TabsTrigger>
        </TabsList>
        <TabsContent value="usage" className="pt-6"><UsageTab /></TabsContent>
        <TabsContent value="audit" className="pt-6"><AuditTab /></TabsContent>
        <TabsContent value="jobs" className="pt-6"><JobsTab /></TabsContent>
      </Tabs>
    </div>
  );
}
