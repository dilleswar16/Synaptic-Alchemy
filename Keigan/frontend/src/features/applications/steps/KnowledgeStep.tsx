import { useState } from "react";
import { ClipboardCopy, FileText, Terminal, Trash2, UploadCloud } from "lucide-react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { useAddRecordLink, useDeleteRecordLink, useIntegrations, useRecordLinks, useServices } from "@/api/applicationsApi";
import {
  useCapturePrompt,
  useDeleteDocument,
  useKnowledgeDocument,
  useKnowledgeDocuments,
  useUploadDocument,
  type DocumentCategory,
  type KnowledgeDocument,
} from "@/api/knowledgeApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Drawer } from "@/components/ui/Drawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { FileDrop, type FileDropItem } from "@/components/ui/FileDrop";
import { Input } from "@/components/ui/Input";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { formatFileSize } from "@/utils/formatters";
import { IntegrationCard } from "../components/IntegrationCard";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

const categories: DocumentCategory[] = ["code_context", "architecture", "operations_guide", "runbook_source", "incident_history", "other"];
const acceptedTypes = [".md", ".markdown", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp"];
const ALL_SERVICES = "__all__";
const digestTones = { pending: "info", running: "info", ready: "success", failed: "danger" } as const;

function CaptureAndUpload({ applicationId, canEdit }: { applicationId: string; canEdit: boolean }) {
  const { t } = useTranslation("knowledge");
  const servicesQuery = useServices(applicationId);
  const [serviceChoice, setServiceChoice] = useState(ALL_SERVICES);
  const [category, setCategory] = useState<DocumentCategory>("code_context");
  const [uploadItems, setUploadItems] = useState<FileDropItem[]>([]);
  const serviceId = serviceChoice === ALL_SERVICES ? null : serviceChoice;
  const promptQuery = useCapturePrompt(applicationId, serviceId);
  const upload = useUploadDocument(applicationId);

  const patchItem = (key: string, changes: Partial<FileDropItem>) => setUploadItems((items) => items.map((item) => (item.key === key ? { ...item, ...changes } : item)));
  const handleFiles = async (files: File[]) => {
    const newItems = files.map<FileDropItem>((file) => ({ key: `${file.name}-${file.size}-${Date.now()}`, fileName: file.name, fileSizeBytes: file.size, status: "pending" }));
    setUploadItems((items) => [...items, ...newItems]);
    for (const [index, file] of files.entries()) {
      const key = newItems[index]?.key ?? "";
      patchItem(key, { status: "uploading", progressPercentage: 0 });
      try {
        await upload.mutateAsync({ file, documentCategory: category, serviceId, onUploadProgress: (percent) => patchItem(key, { progressPercentage: percent }) });
        patchItem(key, { status: "done", progressPercentage: 100 });
      } catch (error) {
        patchItem(key, { status: "error", errorMessage: isApiError(error) ? error.detail : t("upload.failed") });
      }
    }
  };

  const stages = [
    { icon: ClipboardCopy, title: t("capture.stages.copy.title"), body: t("capture.stages.copy.body") },
    { icon: Terminal, title: t("capture.stages.run.title"), body: t("capture.stages.run.body") },
    { icon: UploadCloud, title: t("capture.stages.upload.title"), body: t("capture.stages.upload.body") },
  ];

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader level={3} title={t("capture.title")} description={t("capture.description")} />
      <ol className="grid gap-3 sm:grid-cols-3">
        {stages.map((stage, index) => (
          <li key={stage.title} className="flex gap-3 rounded-lg border border-hairline bg-surface p-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-action"><stage.icon size={16} aria-hidden="true" /></span>
            <div>
              <div className="text-body-sm font-semibold">{index + 1}. {stage.title}</div>
              <div className="text-caption text-muted">{stage.body}</div>
            </div>
          </li>
        ))}
      </ol>
      <Select
        label={t("capture.scope")}
        value={serviceChoice}
        options={[{ value: ALL_SERVICES, label: t("capture.wholeApplication") }, ...(servicesQuery.data ?? []).map((service) => ({ value: service.serviceId, label: service.serviceName }))]}
        onValueChange={setServiceChoice}
      />
      {promptQuery.isError ? (
        <ErrorState size="sm" error={promptQuery.error} onRetry={() => void promptQuery.refetch()} />
      ) : promptQuery.data ? (
        <CommandBlock title={t("capture.promptTitle", { version: promptQuery.data.version, lines: promptQuery.data.lineCount })} commands={promptQuery.data.promptMarkdown} wrapLines maximumHeight="260px" />
      ) : (
        <Skeleton className="h-40 rounded-lg" />
      )}
      {canEdit ? (
        <div className="flex flex-col gap-3">
          <Select label={t("upload.category")} value={category} options={categories.map((value) => ({ value, label: t(`categories.${value}`) }))} onValueChange={setCategory} />
          <FileDrop
            acceptedFileTypes={acceptedTypes}
            acceptedTypesLabel={t("upload.accepted")}
            maximumFileSizeBytes={15 * 1024 * 1024}
            isMultiple
            onFilesSelected={(files) => void handleFiles(files)}
            items={uploadItems}
            onRemoveItem={(key) => setUploadItems((items) => items.filter((item) => item.key !== key))}
          />
        </div>
      ) : null}
    </section>
  );
}

function DigestDrawer({ applicationId, documentId, onClose }: { applicationId: string; documentId: string | null; onClose: () => void }) {
  const { t } = useTranslation("knowledge");
  const detailQuery = useKnowledgeDocument(applicationId, documentId);
  const document = detailQuery.data;
  return (
    <Drawer open={documentId !== null} onOpenChange={(open) => { if (!open) onClose(); }} size="lg" title={document?.documentTitle ?? ""} description={document ? `${document.originalFileName} · ${formatFileSize(document.fileSizeBytes)}` : undefined}>
      {detailQuery.isError ? <ErrorState error={detailQuery.error} onRetry={() => void detailQuery.refetch()} /> : null}
      {document ? (
        <div className="flex flex-col gap-6">
          {document.possiblePromptInjection ? <Banner tone="warning" title={t("digest.injectionTitle")}>{t("digest.injectionBody")}</Banner> : null}
          {document.aiDigestMarkdown ? (
            <div>
              <div className="mb-2 flex items-center gap-2"><h3 className="text-h3 font-semibold">{t("digest.title")}</h3><AiGeneratedChip size="sm" generatedAt={document.uploadedAt} /></div>
              <MarkdownView content={document.aiDigestMarkdown} />
            </div>
          ) : (
            <p className="text-body-sm text-muted">{document.aiDigestErrorMessage ?? t(`digest.status.${document.aiDigestStatus}`)}</p>
          )}
          {document.headings.length ? (
            <div>
              <h3 className="mb-2 text-h3 font-semibold">{t("digest.headings", { count: document.headings.length })}</h3>
              <ul className="columns-2 gap-6 text-body-sm text-muted">{document.headings.map((heading) => <li key={heading} className="truncate">{heading}</li>)}</ul>
            </div>
          ) : null}
          <p className="text-caption text-muted">{t("digest.chunks", { count: document.chunkCount, tokens: document.estimatedTokenCount })}</p>
        </div>
      ) : null}
    </Drawer>
  );
}

function DocumentsList({ applicationId, canEdit, onChanged }: { applicationId: string; canEdit: boolean; onChanged?: () => void }) {
  const { t } = useTranslation("knowledge");
  const documentsQuery = useKnowledgeDocuments(applicationId);
  const deleteDocument = useDeleteDocument(applicationId);
  const [openDocumentId, setOpenDocumentId] = useState<string | null>(null);
  const [documentToDelete, setDocumentToDelete] = useState<KnowledgeDocument | null>(null);

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader level={3} title={t("documents.title")} />
      {documentsQuery.isError ? (
        <ErrorState error={documentsQuery.error} onRetry={() => void documentsQuery.refetch()} />
      ) : documentsQuery.isLoading ? (
        <Skeleton className="h-24 rounded-lg" />
      ) : documentsQuery.data?.length === 0 ? (
        <EmptyState isBordered icon={FileText} size="sm" title={t("documents.emptyTitle")} description={t("documents.emptyDescription")} />
      ) : (
        documentsQuery.data?.map((document) => (
          <Card key={document.knowledgeDocumentId} dense className="p-[var(--card-padding)] flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className="truncate text-body font-semibold text-action hover:underline" onClick={() => setOpenDocumentId(document.knowledgeDocumentId)}>{document.documentTitle}</button>
                <StatusChip size="sm" tone={digestTones[document.aiDigestStatus]} dot pulse={document.aiDigestStatus === "pending" || document.aiDigestStatus === "running"}>{t(`digest.status.${document.aiDigestStatus}`)}</StatusChip>
                {document.isStale ? <StatusChip size="sm" icon={false} tone="neutral">{t("documents.stale")}</StatusChip> : null}
              </div>
              <p className="mt-1 text-caption text-muted">
                {[document.serviceName ?? t("documents.wholeApplication"), t(`categories.${document.documentCategory}`), formatFileSize(document.fileSizeBytes), t("documents.headings", { count: document.headings.length })].join(" · ")}
                {" · "}
                {document.uploadedByUserPrincipalName} <RelativeTime value={document.uploadedAt} />
              </p>
            </div>
            <div className="flex gap-1">
              <Button size="sm" variant="secondary" onClick={() => setOpenDocumentId(document.knowledgeDocumentId)}>{t("documents.viewDigest")}</Button>
              {canEdit ? <Button size="sm" variant="ghost" leadingIcon={Trash2} aria-label={t("documents.delete")} onClick={() => setDocumentToDelete(document)} /> : null}
            </div>
          </Card>
        ))
      )}
      <DigestDrawer applicationId={applicationId} documentId={openDocumentId} onClose={() => setOpenDocumentId(null)} />
      <ConfirmDialog
        open={documentToDelete !== null}
        onOpenChange={(open) => { if (!open) setDocumentToDelete(null); }}
        tone="danger"
        title={t("documents.deleteTitle", { name: documentToDelete?.documentTitle })}
        description={t("documents.deleteDescription")}
        confirmLabel={t("documents.deleteConfirm")}
        onConfirm={async () => { if (documentToDelete) await deleteDocument.mutateAsync(documentToDelete.knowledgeDocumentId); onChanged?.(); }}
      />
    </section>
  );
}

function EnterpriseRecords({ applicationId, canEdit }: { applicationId: string; canEdit: boolean }) {
  const { t } = useTranslation("knowledge");
  const integrationsQuery = useIntegrations(applicationId);
  const recordLinksQuery = useRecordLinks(applicationId);
  const addRecordLink = useAddRecordLink(applicationId);
  const deleteRecordLink = useDeleteRecordLink(applicationId);
  const [recordIdentifier, setRecordIdentifier] = useState("");
  const [recordSystem, setRecordSystem] = useState<"eai" | "cmdb">("eai");

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader level={3} title={t("records.title")} description={t("records.description")} />
      <div className="flex flex-wrap gap-2">
        {recordLinksQuery.data?.map((link) => (
          <span key={link.applicationRecordLinkId} className="inline-flex items-center gap-2 rounded-full border border-hairline bg-surface py-1 pl-3 pr-1 text-body-sm">
            <span className="text-muted">{t(`records.systems.${link.recordSystem}`)}</span>
            <span className="font-mono">{link.recordIdentifier}</span>
            {canEdit ? <Button size="sm" variant="ghost" aria-label={t("records.remove", { code: link.recordIdentifier })} onClick={() => deleteRecordLink.mutate(link.applicationRecordLinkId)}>×</Button> : <span className="pr-2" />}
          </span>
        ))}
      </div>
      {canEdit ? (
        <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); if (recordIdentifier.trim()) addRecordLink.mutate({ recordSystem, recordIdentifier: recordIdentifier.trim() }, { onSuccess: () => setRecordIdentifier("") }); }}>
          <Select aria-label={t("records.system")} className="w-32" value={recordSystem} options={[{ value: "eai", label: t("records.systems.eai") }, { value: "cmdb", label: t("records.systems.cmdb") }]} onValueChange={setRecordSystem} />
          <Input aria-label={t("records.identifier")} placeholder={t("records.placeholder")} value={recordIdentifier} onChange={(event) => setRecordIdentifier(event.target.value)} errorMessage={isApiError(addRecordLink.error) ? addRecordLink.error.detail : undefined} />
          <Button type="submit" variant="secondary" isLoading={addRecordLink.isPending} disabled={!recordIdentifier.trim()}>{t("records.add")}</Button>
        </form>
      ) : null}
      <div className="flex flex-col gap-3">
        {integrationsQuery.data?.map((integration) => <IntegrationCard key={integration.integrationKind} applicationId={applicationId} integration={integration} canEdit={canEdit} />)}
      </div>
    </section>
  );
}

export function KnowledgeStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  return (
    <StepFrame stepKey="knowledge">
      <div className="flex flex-col gap-10">
        <CaptureAndUpload applicationId={applicationId} canEdit={canEdit} />
        <DocumentsList applicationId={applicationId} canEdit={canEdit} onChanged={onStatusChange} />
        <EnterpriseRecords applicationId={applicationId} canEdit={canEdit} />
      </div>
    </StepFrame>
  );
}
