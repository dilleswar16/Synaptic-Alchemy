import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { useHideMemoryEntry, type SimilarIncident } from "@/api/incidentMemoryApi";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";

interface HideSimilarIncidentDialogProps {
  investigationId: string;
  match: SimilarIncident | null;
  onOpenChange: (open: boolean) => void;
}

/** An application admin stops a past incident being suggested to anyone, and says why (kept with the entry, masked, never repeated in the audit trail). */
export function HideSimilarIncidentDialog({ investigationId, match, onOpenChange }: HideSimilarIncidentDialogProps) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const hide = useHideMemoryEntry(investigationId);
  const [reason, setReason] = useState("");
  const close = () => {
    setReason("");
    onOpenChange(false);
  };
  return (
    <Dialog
      open={match !== null}
      onOpenChange={(open) => (open ? undefined : close())}
      title={t("similarIncidents.hide.title")}
      description={t("similarIncidents.hide.description", { title: match?.incidentTitle ?? "" })}
      footer={
        <>
          <Button variant="ghost" onClick={close}>{t("similarIncidents.hide.cancel")}</Button>
          <Button
            variant="danger"
            isLoading={hide.isPending}
            disabled={reason.trim().length === 0}
            onClick={() =>
              match &&
              hide.mutate({ memoryEntryId: match.memoryEntryId, reason: reason.trim() }, {
                onSuccess: () => { showToast({ tone: "success", title: t("similarIncidents.hide.done") }); close(); },
                onError: (error) => showToast({ tone: "danger", title: t("similarIncidents.hide.failed"), description: isApiError(error) ? error.detail : undefined }),
              })
            }
          >
            {t("similarIncidents.hide.confirm")}
          </Button>
        </>
      }
    >
      <Textarea label={t("similarIncidents.hide.reason")} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
    </Dialog>
  );
}
