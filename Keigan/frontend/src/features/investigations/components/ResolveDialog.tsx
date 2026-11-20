import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { useResolveIncident } from "@/api/incidentsApi";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Switch } from "@/components/ui/Switch";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";

interface ResolveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  incidentId: string;
  onResolved: () => void;
}

/** Resolve the incident (also in ServiceNow) and optionally start the blameless postmortem. */
export function ResolveDialog({ open, onOpenChange, incidentId, onResolved }: ResolveDialogProps) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const resolve = useResolveIncident(incidentId);
  const [note, setNote] = useState("");
  const [generatePostmortem, setGeneratePostmortem] = useState(true);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("resolve.title")}
      description={t("resolve.description")}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("resolve.cancel")}</Button>
          <Button
            isLoading={resolve.isPending}
            onClick={() =>
              resolve.mutate({ resolutionNote: note.trim() || undefined, generatePostmortem }, {
                onSuccess: () => { showToast({ tone: "success", title: t("resolve.resolvedTitle"), description: generatePostmortem ? t("resolve.postmortemStarted") : undefined }); onOpenChange(false); onResolved(); },
                onError: (error) => showToast({ tone: "danger", title: t("resolve.failed"), description: isApiError(error) ? error.detail : undefined }),
              })
            }
          >
            {t("resolve.confirm")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Textarea label={t("resolve.note")} helperText={t("resolve.noteHelp")} isOptional rows={4} value={note} onChange={(event) => setNote(event.target.value)} maxLength={4000} />
        <Switch checked={generatePostmortem} onCheckedChange={setGeneratePostmortem} label={t("resolve.generatePostmortem")} description={t("resolve.generatePostmortemHelp")} />
      </div>
    </Dialog>
  );
}
