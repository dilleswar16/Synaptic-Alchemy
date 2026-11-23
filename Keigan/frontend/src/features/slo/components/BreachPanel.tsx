import { useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCreateActionItem } from "@/api/actionItemsApi";
import { useWaiveBreach, type ErrorBudgetBreach } from "@/api/errorBudgetApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Textarea } from "@/components/ui/Textarea";
import { ActionItemDialog } from "@/features/action-items/components/ActionItemDialog";
import { formatNumber } from "@/utils/formatters";

function WaiveDialog({ breach, open, onOpenChange }: { breach: ErrorBudgetBreach; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const waive = useWaiveBreach();
  const [reason, setReason] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const confirm = () => {
    setFailure(null);
    waive.mutate({ breachId: breach.breachId, reasonText: reason }, {
      onSuccess: () => { setReason(""); onOpenChange(false); },
      onError: (error) => setFailure((isApiError(error) ? error.detail : undefined) ?? t("errors.actionFailed")),
    });
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("waive.title")}
      description={t("waive.description")}
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>{t("waive.cancel")}</Button><Button isLoading={waive.isPending} disabled={reason.trim().length === 0} onClick={confirm}>{t("waive.confirm")}</Button></>}
    >
      <div className="flex flex-col gap-3">
        {failure ? <Banner tone="danger" title={t("errors.actionFailed")}>{failure}</Banner> : null}
        <Textarea label={t("waive.reason")} helperText={t("waive.reasonHelp")} value={reason} autoResize maximumRows={8} onChange={(event) => setReason(event.target.value)} />
      </div>
    </Dialog>
  );
}

/** What the team's policy asks of a postmortem: provisional, open (with the two ways forward), met or waived. Nothing shows when the policy found no breach. */
export function BreachPanel({ breach, incidentId, postmortemId }: { breach: ErrorBudgetBreach; incidentId: string; postmortemId?: string }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const [isWaiving, setIsWaiving] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const create = useCreateActionItem();
  const share = formatNumber(breach.measuredSharePercent ?? 0, { maximumFractionDigits: 1 });
  const values = { share, sli: breach.sliName ?? "", threshold: formatNumber(breach.thresholdPercent ?? 0, { maximumFractionDigits: 0 }) };

  if (breach.requirementStatus === "waived") return <Banner tone="neutral" title={t("banner.waivedTitle")}>{t("banner.waived", { by: breach.waivedBy ?? "", reason: breach.waiverReasonText ?? "" })}</Banner>;
  if (breach.requirementStatus === "met") return <Banner tone="success" title={t("banner.metTitle")}>{t("banner.met", values)}</Banner>;
  if (breach.requirementStatus !== "open") return null;
  return (
    <>
      <Banner
        tone={breach.isProvisional ? "info" : "warning"}
        title={breach.isProvisional ? t("banner.provisionalTitle") : t("banner.openTitle")}
        action={breach.isProvisional ? undefined : (
          <div className="flex flex-wrap gap-2">
            {breach.canAddActionItem || breach.canWaive ? <Button size="sm" variant="secondary" leadingIcon={Plus} onClick={() => setIsAdding(true)}>{t("banner.addItem")}</Button> : null}
            {breach.canWaive ? <Button size="sm" variant="ghost" onClick={() => setIsWaiving(true)}>{t("banner.waive")}</Button> : null}
          </div>
        )}
      >
        {breach.isProvisional ? t("banner.provisional", values) : t("banner.open", values)}
      </Banner>
      <WaiveDialog breach={breach} open={isWaiving} onOpenChange={setIsWaiving} />
      <ActionItemDialog
        open={isAdding}
        onOpenChange={setIsAdding}
        mode="create"
        applicationId={breach.applicationId}
        preset={{ actionType: "prevent", actionPriority: "top" }}
        onSubmit={async (fields) => { await create.mutateAsync({ applicationId: breach.applicationId, body: { ...fields, ...(incidentId ? { incidentId } : {}), ...(postmortemId ? { postmortemId } : {}) } }); }}
      />
    </>
  );
}
