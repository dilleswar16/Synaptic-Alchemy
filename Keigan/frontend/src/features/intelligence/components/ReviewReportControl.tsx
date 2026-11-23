import { useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useReviewReport, type IntelligenceReport } from "@/api/intelligenceApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Textarea } from "@/components/ui/Textarea";
import { formatDateTime } from "@/utils/formatters";

/** Who went through the weekly digest and when, and (for admins) the button that records it. Only a weekly digest is reviewed. */
export function ReviewReportControl({ report, canReview }: { report: IntelligenceReport; canReview: boolean }) {
  const { t } = useTranslation("intelligence");
  const review = useReviewReport();
  const [isOpen, setIsOpen] = useState(false);
  const [note, setNote] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  if (report.reportType !== "weekly_digest") return null;

  if (report.reviewedAt) {
    return (
      <Banner tone="success" title={t("reports.review.reviewedTitle")} icon={ClipboardCheck}>
        {t("reports.review.reviewedBy", { name: report.reviewedBy ?? "", date: formatDateTime(report.reviewedAt) })}
        {report.reviewNote ? <span className="mt-1 block">{t("reports.review.note", { text: report.reviewNote })}</span> : null}
      </Banner>
    );
  }
  const confirm = () => {
    setFailure(null);
    review.mutate({ reportId: report.intelligenceReportId, noteText: note.trim() === "" ? null : note }, {
      onSuccess: () => { setNote(""); setIsOpen(false); },
      onError: (error) => setFailure((isApiError(error) ? error.detail : undefined) ?? t("reports.review.failed")),
    });
  };
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-hairline px-4 py-3">
        <p className="text-body-sm text-muted">{t("reports.review.notReviewed")}</p>
        {canReview ? <Button size="sm" variant="secondary" leadingIcon={ClipboardCheck} onClick={() => setIsOpen(true)}>{t("reports.review.mark")}</Button> : null}
      </div>
      <Dialog
        open={isOpen}
        onOpenChange={setIsOpen}
        title={t("reports.review.dialogTitle")}
        description={t("reports.review.dialogDescription")}
        footer={<><Button variant="ghost" onClick={() => setIsOpen(false)}>{t("reports.review.cancel")}</Button><Button isLoading={review.isPending} onClick={confirm}>{t("reports.review.confirm")}</Button></>}
      >
        <div className="flex flex-col gap-3">
          {failure ? <Banner tone="danger" title={t("reports.review.failed")}>{failure}</Banner> : null}
          <Textarea label={t("reports.review.noteLabel")} helperText={t("reports.review.noteHelp")} isOptional autoResize maximumRows={8} value={note} onChange={(event) => setNote(event.target.value)} />
        </div>
      </Dialog>
    </>
  );
}
