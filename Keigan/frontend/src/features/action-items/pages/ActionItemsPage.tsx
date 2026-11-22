import { useState } from "react";
import { ListChecks, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useActionItems, useCreateActionItem, type ActionItemFields, type ActionItemFilters, type ActionItemStatus, type ActionItemType } from "@/api/actionItemsApi";
import { useAccessControl } from "@/auth/accessControl";
import { useApplicationScope } from "@/auth/applicationScope";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { ActionItemDialog } from "../components/ActionItemDialog";
import { ActionItemList } from "../components/ActionItemList";

type StatusView = "tracked" | "finished" | "suggested";
type OwnerView = "all" | "me" | "unassigned";
const statusesByView: Record<StatusView, ActionItemStatus[]> = {
  tracked: ["open", "in_progress", "blocked"],
  finished: ["done", "wont_do"],
  suggested: ["proposed"],
};

/** Follow-ups after incidents, across the applications the user can read. A new item is created for the one application chosen in the scope switcher. */
export default function ActionItemsPage() {
  const { t } = useTranslation("actionItems");
  const { applicationIds, availableApplications } = useApplicationScope();
  const { canEdit } = useAccessControl();
  const [statusView, setStatusView] = useState<StatusView>("tracked");
  const [ownerView, setOwnerView] = useState<OwnerView>("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [isCreating, setIsCreating] = useState(false);
  const create = useCreateActionItem();
  const filters: ActionItemFilters = { applicationIds, statuses: statusesByView[statusView], owner: ownerView === "all" ? null : ownerView, overdueOnly, page };
  const { data, isLoading, isError, error, refetch } = useActionItems(filters);

  const scopedApplicationIds = applicationIds.length > 0 ? applicationIds : availableApplications.map((application) => application.applicationId);
  const createForApplication = scopedApplicationIds.length === 1 ? (scopedApplicationIds[0] ?? null) : null;
  const mayCreate = createForApplication !== null && canEdit(createForApplication);
  const resetPage = <Value,>(setter: (value: Value) => void) => (value: Value) => { setter(value); setPage(1); };
  const totalPages = data ? Math.max(1, Math.ceil(data.totalCount / data.pageSize)) : 1;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pageTitle")}
        description={t("pageDescription")}
        actions={mayCreate ? <Button leadingIcon={Plus} onClick={() => setIsCreating(true)}>{t("page.new")}</Button> : undefined}
      />
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <SegmentedControl
          aria-label={t("page.statusFilter")}
          value={statusView}
          onValueChange={resetPage(setStatusView)}
          options={[{ value: "tracked", label: t("page.tracked") }, { value: "finished", label: t("page.finished") }, { value: "suggested", label: t("page.suggested") }]}
        />
        <SegmentedControl
          aria-label={t("page.ownerFilter")}
          value={ownerView}
          onValueChange={resetPage(setOwnerView)}
          options={[{ value: "all", label: t("page.ownerAll") }, { value: "me", label: t("page.ownerMe") }, { value: "unassigned", label: t("page.ownerUnassigned") }]}
        />
        {statusView === "tracked" ? <Checkbox label={t("page.overdueOnly")} checked={overdueOnly} onCheckedChange={(checked) => { setOverdueOnly(checked === true); setPage(1); }} /> : null}
      </div>
      {isLoading ? <Skeleton className="h-64 w-full" /> : null}
      {isError ? <ErrorState error={error} onRetry={() => void refetch()} /> : null}
      {data && data.items.length === 0 ? <EmptyState icon={ListChecks} title={t(`page.empty.${statusView}.title`)} description={t(`page.empty.${statusView}.description`)} isBordered /> : null}
      {data && data.items.length > 0 ? (
        <>
          <ActionItemList items={data.items} showApplication={availableApplications.length > 1} />
          {totalPages > 1 ? (
            <div className="flex items-center justify-between text-body-sm text-muted">
              <span>{t("page.pageOf", { page, total: totalPages })}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("page.previous")}</Button>
                <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>{t("page.next")}</Button>
              </div>
            </div>
          ) : null}
        </>
      ) : null}
      {createForApplication ? (
        <ActionItemDialog
          open={isCreating}
          onOpenChange={setIsCreating}
          mode="create"
          applicationId={createForApplication}
          onSubmit={async (fields: ActionItemFields & { itemTitle: string; actionType: ActionItemType; dueOn: string }) => {
            await create.mutateAsync({ applicationId: createForApplication, body: fields });
          }}
        />
      ) : null}
    </div>
  );
}
