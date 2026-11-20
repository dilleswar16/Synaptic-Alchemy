import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { useInvestigationFeedback, type FeedbackVerdict } from "@/api/investigationsApi";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { RadioGroup } from "@/components/ui/RadioGroup";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";

interface FeedbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investigationId: string;
  currentVerdict: FeedbackVerdict | null;
}

/** RCA verdict (correct, partly correct, incorrect) with an optional comment; feeds recurring-issue memory. */
export function FeedbackDialog({ open, onOpenChange, investigationId, currentVerdict }: FeedbackDialogProps) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const feedback = useInvestigationFeedback(investigationId);
  const [verdict, setVerdict] = useState<FeedbackVerdict>(currentVerdict ?? "correct");
  const [comment, setComment] = useState("");
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("feedback.title")}
      description={t("feedback.description")}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("feedback.cancel")}</Button>
          <Button
            isLoading={feedback.isPending}
            onClick={() =>
              feedback.mutate({ verdict, comment: comment.trim() || undefined }, {
                onSuccess: () => { showToast({ tone: "success", title: t("feedback.thanks") }); onOpenChange(false); },
                onError: (error) => showToast({ tone: "danger", title: t("feedback.failed"), description: isApiError(error) ? error.detail : undefined }),
              })
            }
          >
            {t("feedback.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <RadioGroup<FeedbackVerdict>
          aria-label={t("feedback.verdictLabel")}
          value={verdict}
          onValueChange={setVerdict}
          variant="card"
          options={[
            { value: "correct", label: t("feedback.verdict.correct"), description: t("feedback.verdictHelp.correct") },
            { value: "partially_correct", label: t("feedback.verdict.partially_correct"), description: t("feedback.verdictHelp.partially_correct") },
            { value: "incorrect", label: t("feedback.verdict.incorrect"), description: t("feedback.verdictHelp.incorrect") },
          ]}
        />
        <Textarea label={t("feedback.comment")} isOptional rows={3} value={comment} onChange={(event) => setComment(event.target.value)} maxLength={4000} />
      </div>
    </Dialog>
  );
}
