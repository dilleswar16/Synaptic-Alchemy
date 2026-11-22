import { useEffect, useState } from "react";
import { Download, FilePenLine, FileText, Printer, Send, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useFinalizePostmortem, useGeneratePostmortem, usePostmortem, useSendPostmortem, useUpdatePostmortem } from "@/api/incidentsApi";
import { isApiError } from "@/api/httpClient";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime } from "@/utils/formatters";
import { PostmortemActionItems } from "./PostmortemActionItems";

function downloadMarkdown(fileName: string, markdown: string) {
  const objectUrl = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

/** Blameless postmortem: generate, edit, finalise, send, download as Markdown or print to PDF. */
export function PostmortemSection({ detail, canEdit }: { detail: InvestigationDetail; canEdit: boolean }) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const incidentId = detail.incidentId ?? "";
  const { data: postmortem, isLoading, isError, error, refetch } = usePostmortem(detail.incidentId ?? undefined);
  const generate = useGeneratePostmortem(incidentId);
  const update = useUpdatePostmortem(incidentId);
  const finalize = useFinalizePostmortem(incidentId);
  const send = useSendPostmortem(incidentId);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [isFinalizeOpen, setIsFinalizeOpen] = useState(false);
  useEffect(() => {
    if (!isEditing) setDraft(postmortem?.reportMarkdown ?? "");
  }, [postmortem?.reportMarkdown, isEditing]);
  const reportError = (failure: unknown) => showToast({ tone: "danger", title: t("postmortem.actionFailed"), description: isApiError(failure) ? failure.detail : undefined });

  if (!detail.incidentId) return <EmptyState icon={FileText} title={t("postmortem.noIncidentTitle")} description={t("postmortem.noIncidentDescription")} isBordered />;
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;

  if (!postmortem) {
    const isResolved = detail.incident ? ["resolved", "closed"].includes(detail.incident.incidentStatus) : false;
    return (
      <EmptyState
        icon={FileText}
        title={t("postmortem.emptyTitle")}
        description={isResolved ? t("postmortem.emptyResolved") : t("postmortem.emptyOpen", { action: t("header.resolve") })}
        // While the incident is open the header's "Resolve and write postmortem" is the main action, so this one is the lesser "draft only" choice.
        action={canEdit ? <Button variant={isResolved ? "primary" : "secondary"} leadingIcon={Sparkles} isLoading={generate.isPending} onClick={() => generate.mutate(undefined, { onError: reportError })}>{isResolved ? t("postmortem.generate") : t("postmortem.generateDraft")}</Button> : undefined}
        isBordered
      />
    );
  }
  if (postmortem.reportStatus === "generating") {
    return (
      <Card><CardBody className="flex items-center gap-4 py-10"><Spinner /><div><p className="font-semibold text-default">{t("postmortem.generatingTitle")}</p><p className="text-body-sm text-muted">{t("postmortem.generatingDescription")}</p></div></CardBody></Card>
    );
  }
  const isFinal = postmortem.reportStatus === "final";
  const markdown = postmortem.reportMarkdown ?? "";
  return (
    <div className="flex flex-col gap-4">
      {postmortem.reportStatus === "failed" ? <Banner tone="danger" title={t("postmortem.failedTitle")}>{markdown || t("postmortem.failedDescription")}</Banner> : null}
      <Card radius="lg">
        <CardHeader
          title={postmortem.reportTitle}
          description={isFinal && postmortem.finalizedAt ? t("postmortem.finalizedAt", { time: formatDateTime(postmortem.finalizedAt) }) : t("postmortem.draftHelp")}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <AiGeneratedChip size="sm" generatedAt={postmortem.createdAt} />
              <StatusChip tone={isFinal ? "success" : "neutral"} size="sm">{t(`postmortem.status.${postmortem.reportStatus}`)}</StatusChip>
            </div>
          }
        />
        <CardBody className="flex flex-col gap-5">
          <div className="flex flex-wrap gap-2 print:hidden">
            {canEdit && !isFinal && postmortem.reportStatus === "draft" ? (
              isEditing ? (
                <>
                  <Button size="sm" isLoading={update.isPending} onClick={() => update.mutate({ postmortemId: postmortem.postmortemId, reportMarkdown: draft }, { onSuccess: () => setIsEditing(false), onError: reportError })}>{t("postmortem.save")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => { setIsEditing(false); setDraft(markdown); }}>{t("postmortem.cancel")}</Button>
                </>
              ) : (
                <>
                  <Button size="sm" variant="secondary" leadingIcon={FilePenLine} onClick={() => setIsEditing(true)}>{t("postmortem.edit")}</Button>
                  <Button size="sm" variant="secondary" leadingIcon={Sparkles} isLoading={generate.isPending} onClick={() => generate.mutate(undefined, { onError: reportError })}>{t("postmortem.regenerate")}</Button>
                  <Button size="sm" onClick={() => setIsFinalizeOpen(true)}>{t("postmortem.finalize")}</Button>
                </>
              )
            ) : null}
            {canEdit && isFinal ? (
              <Button
                size="sm"
                leadingIcon={Send}
                isLoading={send.isPending}
                disabled={Boolean(postmortem.sentAt)}
                onClick={() => send.mutate(postmortem.postmortemId, { onSuccess: (result) => showToast({ tone: result.deliveriesQueued > 0 ? "success" : "info", title: result.deliveriesQueued > 0 ? t("postmortem.sentTitle") : t("postmortem.notSentTitle"), description: result.message }), onError: reportError })}
              >
                {postmortem.sentAt ? t("postmortem.sent") : t("postmortem.send")}
              </Button>
            ) : null}
            <Button size="sm" variant="secondary" leadingIcon={Download} onClick={() => downloadMarkdown(`postmortem-${detail.incidentNumber ?? incidentId}.md`, markdown)}>{t("postmortem.download")}</Button>
            <Button size="sm" variant="secondary" leadingIcon={Printer} onClick={() => window.print()}>{t("postmortem.print")}</Button>
          </div>
          {isEditing ? <Textarea label={t("postmortem.editorLabel")} value={draft} onChange={(event) => setDraft(event.target.value)} autoResize maximumRows={40} isMonospace /> : <MarkdownView content={markdown} size="large" />}
        </CardBody>
      </Card>
      {postmortem.reportStatus === "draft" || isFinal ? <PostmortemActionItems postmortemId={postmortem.postmortemId} isFinal={isFinal} /> : null}
      <ConfirmDialog
        open={isFinalizeOpen}
        onOpenChange={setIsFinalizeOpen}
        title={t("postmortem.finalizeTitle")}
        description={t("postmortem.finalizeDescription")}
        confirmLabel={t("postmortem.finalize")}
        tone="primary"
        onConfirm={async () => {
          try {
            await finalize.mutateAsync(postmortem.postmortemId);
          } catch (failure) {
            reportError(failure);
          }
        }}
      />
    </div>
  );
}
