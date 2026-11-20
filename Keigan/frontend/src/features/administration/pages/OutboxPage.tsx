import { useState } from "react";
import { MailX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOutbox, useOutboxDelivery, type OutboxDeliverySummary } from "@/api/administrationApi";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Drawer } from "@/components/ui/Drawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDateTime } from "@/utils/formatters";

/** Emails and Teams messages Keigan sent or simulated, with the rendered HTML in a sandboxed frame. */
export default function OutboxPage() {
  const { t } = useTranslation("administration");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const outbox = useOutbox(page);
  const delivery = useOutboxDelivery(selectedId);
  const columns: DataTableColumn<OutboxDeliverySummary>[] = [
    { key: "created", header: t("outbox.columns.created"), cell: (row) => formatDateTime(row.createdAt, { dateStyle: "short", timeStyle: "short" }), width: "10rem" },
    { key: "subject", header: t("outbox.columns.subject"), cell: (row) => <span className="block max-w-96 truncate font-medium">{row.subjectLine ?? row.notificationType}</span> },
    { key: "recipient", header: t("outbox.columns.recipient"), cell: (row) => row.recipientAddress },
    { key: "application", header: t("outbox.columns.application"), cell: (row) => row.applicationName ?? "—" },
    { key: "channel", header: t("outbox.columns.channel"), cell: (row) => row.deliveryChannel },
    { key: "status", header: t("outbox.columns.status"), cell: (row) => <StatusChip size="sm" tone={row.deliveryStatus === "sent" || row.deliveryStatus === "simulated" ? "success" : row.deliveryStatus === "failed" ? "danger" : "info"}>{row.deliveryStatus}</StatusChip> },
  ];
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("outbox.pageTitle")} description={t("outbox.pageDescription")} />
      {outbox.isError ? (
        <EmptyState icon={MailX} title={t("outbox.unavailableTitle")} description={t("outbox.unavailableDescription")} isBordered />
      ) : (
        <DataTable caption={t("outbox.pageTitle")} columns={columns} rows={outbox.data?.items ?? []} getRowId={(row) => row.notificationDeliveryId} isLoading={outbox.isLoading} onRowClick={(row) => setSelectedId(row.notificationDeliveryId)}
          serverPagination={{ page, pageSize: 25, totalCount: outbox.data?.totalCount ?? 0, onPageChange: setPage }} emptyState={<EmptyState icon={MailX} title={t("outbox.emptyTitle")} description={t("outbox.emptyDescription")} size="sm" />} />
      )}
      <Drawer open={selectedId !== null} onOpenChange={(open) => !open && setSelectedId(null)} title={delivery.data?.subjectLine ?? t("outbox.previewTitle")} description={delivery.data ? `${delivery.data.recipientAddress} · ${delivery.data.deliveryChannel}` : undefined} size="lg">
        {delivery.isLoading ? <Skeleton className="h-96" /> : delivery.data?.bodyHtml ? (
          <iframe title={t("outbox.previewTitle")} sandbox="" srcDoc={delivery.data.bodyHtml} className="h-[70vh] w-full rounded-md border border-hairline bg-white" />
        ) : <pre className="whitespace-pre-wrap text-body-sm text-default">{delivery.data?.bodyText ?? t("outbox.noBody")}</pre>}
      </Drawer>
    </div>
  );
}
