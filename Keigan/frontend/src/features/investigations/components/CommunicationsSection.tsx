import { useEffect, useMemo, useState } from "react";
import { CircleCheck, Mail, Send, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useApproveCommunication, useCommunications, useGenerateCommunications, useSendCommunication, useUpdateCommunication,
  type Communication, type CommunicationType, type InvestigationDetail,
} from "@/api/investigationsApi";
import { isApiError } from "@/api/httpClient";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { Select } from "@/components/ui/Select";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime } from "@/utils/formatters";
import { communicationLanguageLabel } from "./investigationPresentation";

const typeOrder: CommunicationType[] = ["initial_update", "executive_summary", "preliminary_report", "progress_update", "resolution_update"];
const statusTone = { draft: "neutral", approved: "info", sent: "success" } as const;

function CommunicationCard({ communication, investigationId, canEdit }: { communication: Communication; investigationId: string; canEdit: boolean }) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const [subject, setSubject] = useState(communication.subjectLine);
  const [body, setBody] = useState(communication.bodyMarkdown);
  const update = useUpdateCommunication(investigationId);
  const approve = useApproveCommunication(investigationId);
  const send = useSendCommunication(investigationId);
  useEffect(() => {
    setSubject(communication.subjectLine);
    setBody(communication.bodyMarkdown);
  }, [communication.subjectLine, communication.bodyMarkdown, communication.updatedAt]);
  const isSent = communication.communicationStatus === "sent";
  const isDirty = subject !== communication.subjectLine || body !== communication.bodyMarkdown;
  const reportError = (error: unknown) => showToast({ tone: "danger", title: t("communications.actionFailed"), description: isApiError(error) ? error.detail : undefined });

  return (
    <Card>
      <CardHeader
        title={t(`communications.type.${communication.communicationType}`)}
        description={t(`communications.audience.${communication.audienceType}`, { defaultValue: communication.audienceType })}
        actions={
          <div className="flex items-center gap-2">
            <AiGeneratedChip size="sm" generatedAt={communication.createdAt} />
            <StatusChip tone={statusTone[communication.communicationStatus]} size="sm">{t(`communications.status.${communication.communicationStatus}`)}</StatusChip>
          </div>
        }
      />
      <CardBody className="flex flex-col gap-3">
        {canEdit && !isSent ? (
          <>
            <Input label={t("communications.subject")} value={subject} onChange={(event) => setSubject(event.target.value)} lang={communication.languageCode} />
            <Textarea label={t("communications.body")} value={body} onChange={(event) => setBody(event.target.value)} autoResize maximumRows={14} lang={communication.languageCode} />
          </>
        ) : (
          <div lang={communication.languageCode} className="flex flex-col gap-2">
            <p className="text-body font-semibold text-default">{communication.subjectLine}</p>
            <MarkdownView content={communication.bodyMarkdown} />
          </div>
        )}
        {isSent && communication.sentAt ? <p className="text-caption text-muted">{t("communications.sentAt", { time: formatDateTime(communication.sentAt) })}</p> : null}
        {communication.communicationStatus === "approved" && communication.approvedByUserPrincipalName ? <p className="text-caption text-muted">{t("communications.approvedBy", { name: communication.approvedByUserPrincipalName })}</p> : null}
      </CardBody>
      {canEdit && !isSent ? (
        <CardFooter className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" size="sm" disabled={!isDirty} isLoading={update.isPending} onClick={() => update.mutate({ communicationId: communication.communicationId, subjectLine: subject, bodyMarkdown: body }, { onError: reportError })}>
            {t("communications.save")}
          </Button>
          <Button variant="subtle" size="sm" leadingIcon={CircleCheck} disabled={isDirty || communication.communicationStatus === "approved"} isLoading={approve.isPending} onClick={() => approve.mutate(communication.communicationId, { onError: reportError })}>
            {t("communications.approve")}
          </Button>
          <Button
            size="sm"
            leadingIcon={Send}
            disabled={communication.communicationStatus !== "approved" || isDirty}
            isLoading={send.isPending}
            onClick={() =>
              send.mutate(communication.communicationId, {
                onSuccess: (result) => showToast({ tone: result.deliveriesQueued > 0 ? "success" : "info", title: result.deliveriesQueued > 0 ? t("communications.sentTitle") : t("communications.notSentTitle"), description: result.message }),
                onError: reportError,
              })
            }
          >
            {t("communications.send")}
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}

/** EN / 日本語 (and stakeholder languages) drafts: edit, approve and send; generate more drafts on demand. */
export function CommunicationsSection({ detail, canEdit }: { detail: InvestigationDetail; canEdit: boolean }) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const { data: communications, isLoading, isError, error, refetch } = useCommunications(detail.investigationId);
  const generate = useGenerateCommunications(detail.investigationId);
  const [language, setLanguage] = useState("en");
  const [generateType, setGenerateType] = useState<CommunicationType>("progress_update");
  const languages = useMemo(() => [...new Set((communications ?? []).map((communication) => communication.languageCode))].sort((first, second) => (first === "en" ? -1 : second === "en" ? 1 : first.localeCompare(second))), [communications]);
  const activeLanguage = languages.includes(language) ? language : (languages[0] ?? "en");
  const visible = (communications ?? []).filter((communication) => communication.languageCode === activeLanguage).sort((first, second) => typeOrder.indexOf(first.communicationType) - typeOrder.indexOf(second.communicationType));
  const isCompleted = detail.investigationStatus.startsWith("completed");

  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;
  return (
    <div className="flex flex-col gap-5">
      <Banner tone="info" icon={Mail}>{t("communications.policy")}</Banner>
      <div className="flex flex-wrap items-end justify-between gap-3">
        {languages.length > 1 ? (
          <SegmentedControl aria-label={t("communications.languageLabel")} value={activeLanguage} onValueChange={setLanguage} options={languages.map((code) => ({ value: code, label: communicationLanguageLabel(code) }))} />
        ) : <span />}
        {canEdit && isCompleted ? (
          <div className="flex flex-wrap items-end gap-2">
            <Select<CommunicationType> aria-label={t("communications.generateType")} size="sm" value={generateType} onValueChange={setGenerateType} options={typeOrder.map((type) => ({ value: type, label: t(`communications.type.${type}`) }))} />
            <Button
              variant="secondary"
              size="sm"
              leadingIcon={Sparkles}
              isLoading={generate.isPending}
              onClick={() => generate.mutate({ communicationType: generateType, languageCodes: languages.length > 0 ? languages : ["en", "ja"] }, { onSuccess: () => showToast({ tone: "ai", title: t("communications.generating") }), onError: (generateError) => showToast({ tone: "danger", title: t("communications.actionFailed"), description: isApiError(generateError) ? generateError.detail : undefined }) })}
            >
              {t("communications.generate")}
            </Button>
          </div>
        ) : null}
      </div>
      {visible.length === 0 ? (
        <EmptyState icon={Mail} title={t("communications.emptyTitle")} description={isCompleted ? t("communications.emptyDescription") : t("communications.emptyRunning")} isBordered />
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
          {visible.map((communication) => <CommunicationCard key={communication.communicationId} communication={communication} investigationId={detail.investigationId} canEdit={canEdit} />)}
        </div>
      )}
    </div>
  );
}
