import { useState } from "react";
import { ChevronRight, MailX, Search, TriangleExclamationPoint } from "lucide-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { administrationQueryKeys, useOutboxDelivery, type OutboxDeliverySummary } from "@/api/administrationApi";
import { apiGet } from "@/api/httpClient";
import type { PagedResult } from "@/api/types/common";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Drawer } from "@/components/ui/Drawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDateTime } from "@/utils/formatters";

const deliveryStatuses = ["pending", "sent", "simulated", "failed", "skipped"] as const;
type StatusFilter = "all" | (typeof deliveryStatuses)[number];

/** Outbox page with the status filter applied by the API (the shared `useOutbox` hook has no filter). */
function useFilteredOutbox(page: number, status: StatusFilter) {
  return useQuery({
    queryKey: [...administrationQueryKeys.outbox(page), status],
    queryFn: () => apiGet<PagedResult<OutboxDeliverySummary>>("/outbox", { query: { page, pageSize: 25, deliveryStatus: status === "all" ? undefined : status } }),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/** Emails and Teams messages Keigan sent or simulated, with the rendered HTML in a sandboxed frame. */
export default function OutboxPage() {
  const { t } = useTranslation("administration");
  const { t: translateNotifications } = useTranslation("notifications");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [searchText, setSearchText] = useState("");
  const outbox = useFilteredOutbox(page, status);
  const needle = searchText.trim().toLowerCase();
  // The API filters by status; recipient and subject are matched on the rows of the page that is open.
  const rows = (outbox.data?.items ?? []).filter((row) => !needle || row.recipientAddress.toLowerCase().includes(needle) || (row.subjectLine ?? row.notificationType).toLowerCase().includes(needle));
  const isFiltered = status !== "all" || needle !== "";
  const changeStatus = (next: StatusFilter) => {
    setStatus(next);
    setPage(1);
  };
  const delivery = useOutboxDelivery(selectedId);
  const columns: DataTableColumn<OutboxDeliverySummary>[] = [
    { key: "created", header: t("outbox.columns.created"), cell: (row) => formatDateTime(row.createdAt, { dateStyle: "short", timeStyle: "short" }), width: "10rem" },
    { key: "subject", header: t("outbox.columns.subject"), cell: (row) => <span className="block max-w-72 truncate font-medium">{row.subjectLine ?? row.notificationType}</span> },
    { key: "recipient", header: t("outbox.columns.recipient"), cell: (row) => row.recipientAddress },
    { key: "application", header: t("outbox.columns.application"), cell: (row) => row.applicationName ?? "—" },
    { key: "channel", header: t("outbox.columns.channel"), cell: (row) => translateNotifications(`channels.${row.deliveryChannel}`, { defaultValue: row.deliveryChannel }) },
    { key: "status", header: t("outbox.columns.status"), cell: (row) => (
      <span className="flex items-center justify-between gap-2">
        <StatusChip size="sm" tone={row.deliveryStatus === "sent" || row.deliveryStatus === "simulated" ? "success" : row.deliveryStatus === "failed" ? "danger" : "info"}>{t(`outbox.status.${row.deliveryStatus}`, { defaultValue: row.deliveryStatus })}</StatusChip>
        <ChevronRight aria-hidden="true" size={16} className="shrink-0 text-muted group-hover:text-action" />
      </span>
    ) },
  ];
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("outbox.pageTitle")} description={t("outbox.pageDescription")}>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Input aria-label={t("outbox.filterSearch")} placeholder={t("outbox.filterSearch")} leadingIcon={Search} size="sm" value={searchText} onChange={(event) => setSearchText(event.target.value)} containerClassName="w-72 max-w-full" />
          <Select<StatusFilter>
            aria-label={t("outbox.columns.status")}
            size="sm"
            className="w-44"
            value={status}
            onValueChange={changeStatus}
            options={[{ value: "all", label: t("outbox.filterAllStatuses") }, ...deliveryStatuses.map((value) => ({ value, label: t(`outbox.status.${value}`) }))]}
          />
          <Button size="sm" variant={status === "failed" ? "primary" : "secondary"} aria-pressed={status === "failed"} leadingIcon={TriangleExclamationPoint} onClick={() => changeStatus(status === "failed" ? "all" : "failed")}>{t("outbox.status.failed")}</Button>
        </div>
      </PageHeader>
      {outbox.isError ? (
        <EmptyState icon={MailX} title={t("outbox.unavailableTitle")} description={t("outbox.unavailableDescription")} isBordered />
      ) : (
        <DataTable caption={t("outbox.pageTitle")} columns={columns} rows={rows} getRowId={(row) => row.notificationDeliveryId} isLoading={outbox.isLoading} onRowClick={(row) => setSelectedId(row.notificationDeliveryId)}
          serverPagination={{ page, pageSize: 25, totalCount: needle ? rows.length : outbox.data?.totalCount ?? 0, onPageChange: setPage }} emptyState={<EmptyState icon={MailX} title={isFiltered ? t("outbox.noMatchTitle") : t("outbox.emptyTitle")} description={isFiltered ? t("outbox.noMatchDescription") : t("outbox.emptyDescription")} size="sm" />} />
      )}
      <Drawer open={selectedId !== null} onOpenChange={(open) => !open && setSelectedId(null)} title={delivery.data?.subjectLine ?? t("outbox.previewTitle")} description={delivery.data ? `${delivery.data.recipientAddress} · ${translateNotifications(`channels.${delivery.data.deliveryChannel}`, { defaultValue: delivery.data.deliveryChannel })}` : undefined} size="lg">
        {delivery.isLoading ? <Skeleton className="h-96" /> : delivery.data?.bodyHtml ? (
          <iframe title={t("outbox.previewTitle")} sandbox="" srcDoc={delivery.data.bodyHtml} className="h-[70vh] w-full rounded-md border border-hairline bg-white" />
        ) : <pre className="whitespace-pre-wrap text-body-sm text-default">{delivery.data?.bodyText ?? t("outbox.noBody")}</pre>}
      </Drawer>
    </div>
  );
}
