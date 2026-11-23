import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { useResolveIncident, type KeiganHelp } from "@/api/incidentsApi";
import type { FeedbackVerdict } from "@/api/investigationsApi";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { RadioGroup } from "@/components/ui/RadioGroup";
import { Switch } from "@/components/ui/Switch";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";

interface ResolveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  incidentId: string;
  onResolved: () => void;
  /** The rating already given to the analysis, which suggests the answer to "how did Keigan help?". */
  analysisVerdict?: FeedbackVerdict | null;
}

type HelpChoice = KeiganHelp | "none";
const helpAnswers: KeiganHelp[] = ["found_cause", "helped_partly", "did_not_help", "not_used"];
const helpSuggestedByVerdict: Record<FeedbackVerdict, KeiganHelp> = { correct: "found_cause", partially_correct: "helped_partly", incorrect: "did_not_help" };

/** Resolve the incident (also in ServiceNow) and optionally start the blameless postmortem. */
export function ResolveDialog({ open, onOpenChange, incidentId, onResolved, analysisVerdict }: ResolveDialogProps) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const resolve = useResolveIncident(incidentId);
  const [note, setNote] = useState("");
  const [generatePostmortem, setGeneratePostmortem] = useState(true);
  const suggestedHelp: HelpChoice = analysisVerdict ? helpSuggestedByVerdict[analysisVerdict] : "none";
  const [help, setHelp] = useState<HelpChoice>(suggestedHelp);
  useEffect(() => {
    if (open) setHelp(suggestedHelp);
  }, [open, suggestedHelp]);
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
              resolve.mutate({ resolutionNote: note.trim() || undefined, generatePostmortem, keiganHelp: help === "none" ? undefined : help }, {
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
        <RadioGroup<HelpChoice>
          label={t("resolve.keiganHelp.label")}
          helperText={analysisVerdict ? t("resolve.keiganHelp.helpWithRating") : t("resolve.keiganHelp.help")}
          isOptional
          value={help}
          onValueChange={setHelp}
          variant="card"
          options={[
            ...helpAnswers.map((answer) => ({ value: answer, label: t(`resolve.keiganHelp.answer.${answer}`), description: t(`resolve.keiganHelp.description.${answer}`) })),
            { value: "none" as const, label: t("resolve.keiganHelp.answer.none") },
          ]}
        />
        <Switch checked={generatePostmortem} onCheckedChange={setGeneratePostmortem} label={t("resolve.generatePostmortem")} description={t("resolve.generatePostmortemHelp")} />
      </div>
    </Dialog>
  );
}
