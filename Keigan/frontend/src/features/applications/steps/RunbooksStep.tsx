import { useRef, useState } from "react";
import { BookOpen, FileUp, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useServices } from "@/api/applicationsApi";
import { isApiError } from "@/api/httpClient";
import { useDeleteRunbook, useRunbooks, useSaveRunbook, type Runbook } from "@/api/knowledgeApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Checkbox";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Drawer } from "@/components/ui/Drawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

const maximumRunbookFileBytes = 512 * 1024;

function RunbookEditor({ applicationId, runbook, open, onClose }: { applicationId: string; runbook: Runbook | null; open: boolean; onClose: () => void }) {
  const { t } = useTranslation("knowledge");
  const servicesQuery = useServices(applicationId);
  const saveRunbook = useSaveRunbook(applicationId);
  const fileInputReference = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(runbook?.runbookTitle ?? "");
  const [symptoms, setSymptoms] = useState(runbook?.triggerSymptomsText ?? "");
  const [steps, setSteps] = useState(runbook?.runbookStepsMarkdown ?? "");
  const [sourceUrl, setSourceUrl] = useState(runbook?.sourceUrl ?? "");
  const [serviceIds, setServiceIds] = useState<string[]>(runbook?.appliesToServiceIds ?? []);
  const [fileError, setFileError] = useState<string | null>(null);

  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > maximumRunbookFileBytes) return setFileError(t("runbooks.fileTooLarge"));
    setFileError(null);
    setSteps(await file.text());
    if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ""));
  };

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      size="lg"
      title={runbook ? t("runbooks.editTitle") : t("runbooks.addTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t("topology.cancel")}</Button>
          <Button
            disabled={title.trim().length < 2}
            isLoading={saveRunbook.isPending}
            onClick={() =>
              saveRunbook.mutate(
                { runbookId: runbook?.runbookId, body: { runbookTitle: title.trim(), triggerSymptomsText: symptoms || null, runbookStepsMarkdown: steps || null, sourceUrl: sourceUrl || null, appliesToServiceIds: serviceIds } },
                { onSuccess: onClose },
              )
            }
          >
            {t("runbooks.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Input label={t("runbooks.titleLabel")} value={title} onChange={(event) => setTitle(event.target.value)} errorMessage={isApiError(saveRunbook.error) ? saveRunbook.error.fieldErrorFor("runbookTitle") : undefined} />
        <Textarea label={t("runbooks.symptoms")} helperText={t("runbooks.symptomsHelp")} rows={3} value={symptoms} onChange={(event) => setSymptoms(event.target.value)} />
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-body-sm font-semibold">{t("runbooks.steps")}</span>
            <Button size="sm" variant="ghost" leadingIcon={FileUp} onClick={() => fileInputReference.current?.click()}>{t("runbooks.loadFile")}</Button>
            <input ref={fileInputReference} type="file" accept=".md,.markdown,.txt" className="hidden" onChange={(event) => { void loadFile(event.target.files?.[0]); event.target.value = ""; }} />
          </div>
          {fileError ? <Banner tone="danger">{fileError}</Banner> : null}
          <Tabs defaultValue="write">
            <TabsList>
              <TabsTrigger value="write">{t("runbooks.write")}</TabsTrigger>
              <TabsTrigger value="preview">{t("runbooks.preview")}</TabsTrigger>
            </TabsList>
            <TabsContent value="write"><Textarea aria-label={t("runbooks.steps")} isMonospace rows={10} value={steps} onChange={(event) => setSteps(event.target.value)} /></TabsContent>
            <TabsContent value="preview">{steps.trim() ? <MarkdownView content={steps} /> : <p className="text-body-sm text-muted">{t("runbooks.nothingToPreview")}</p>}</TabsContent>
          </Tabs>
        </div>
        <Input label={t("runbooks.sourceLink")} isOptional type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-body-sm font-semibold">{t("runbooks.appliesTo")}</legend>
          <p className="text-caption text-muted">{t("runbooks.appliesToHelp")}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {servicesQuery.data?.map((service) => (
              <Checkbox key={service.serviceId} label={service.serviceName} checked={serviceIds.includes(service.serviceId)} onCheckedChange={(checked) => setServiceIds(checked === true ? [...serviceIds, service.serviceId] : serviceIds.filter((id) => id !== service.serviceId))} />
            ))}
          </div>
        </fieldset>
        {saveRunbook.isError && !isApiError(saveRunbook.error) ? <Banner tone="danger">{t("runbooks.saveFailed")}</Banner> : null}
      </div>
    </Drawer>
  );
}

export function RunbooksStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("knowledge");
  const runbooksQuery = useRunbooks(applicationId);
  const deleteRunbook = useDeleteRunbook(applicationId);
  const [editing, setEditing] = useState<{ runbook: Runbook | null } | null>(null);
  const [runbookToDelete, setRunbookToDelete] = useState<Runbook | null>(null);

  return (
    <StepFrame stepKey="runbooks" actions={canEdit ? <Button leadingIcon={Plus} onClick={() => setEditing({ runbook: null })}>{t("runbooks.add")}</Button> : undefined}>
      {runbooksQuery.isError ? (
        <ErrorState error={runbooksQuery.error} onRetry={() => void runbooksQuery.refetch()} />
      ) : runbooksQuery.isLoading ? (
        <Skeleton className="h-32 rounded-lg" />
      ) : runbooksQuery.data?.length === 0 ? (
        <EmptyState isBordered icon={BookOpen} title={t("runbooks.emptyTitle")} description={t("runbooks.emptyDescription")} action={canEdit ? <Button leadingIcon={Plus} onClick={() => setEditing({ runbook: null })}>{t("runbooks.add")}</Button> : undefined} />
      ) : (
        <div className="flex flex-col gap-3">
          {runbooksQuery.data?.map((runbook) => (
            <Card key={runbook.runbookId} dense className="flex flex-col gap-2 p-[var(--card-padding)]">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-body font-semibold">{runbook.runbookTitle}</h3>
                  {runbook.triggerSymptomsText ? <p className="mt-1 line-clamp-2 text-body-sm text-muted">{runbook.triggerSymptomsText}</p> : null}
                </div>
                {canEdit ? (
                  <div className="flex shrink-0 gap-1">
                    <Button size="sm" variant="secondary" leadingIcon={Pencil} onClick={() => setEditing({ runbook })}>{t("runbooks.edit")}</Button>
                    <Button size="sm" variant="ghost" leadingIcon={Trash2} aria-label={t("runbooks.delete")} onClick={() => setRunbookToDelete(runbook)} />
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {runbook.appliesToServiceNames.length ? runbook.appliesToServiceNames.map((name) => <StatusChip key={name} size="sm" icon={false} tone="neutral">{name}</StatusChip>) : <StatusChip size="sm" icon={false} tone="neutral">{t("runbooks.wholeApplication")}</StatusChip>}
                <span className="text-caption text-muted">{t("runbooks.referenced", { count: runbook.timesReferencedCount })}</span>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing ? <RunbookEditor key={editing.runbook?.runbookId ?? "new"} applicationId={applicationId} runbook={editing.runbook} open onClose={() => { setEditing(null); onStatusChange?.(); }} /> : null}
      <ConfirmDialog
        open={runbookToDelete !== null}
        onOpenChange={(open) => { if (!open) setRunbookToDelete(null); }}
        tone="danger"
        title={t("runbooks.deleteTitle", { name: runbookToDelete?.runbookTitle })}
        description={t("runbooks.deleteDescription")}
        confirmLabel={t("runbooks.deleteConfirm")}
        onConfirm={async () => { if (runbookToDelete) await deleteRunbook.mutateAsync(runbookToDelete.runbookId); onStatusChange?.(); }}
      />
    </StepFrame>
  );
}
