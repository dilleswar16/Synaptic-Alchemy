import { useEffect, useRef, useState } from "react";
import { useBlocker } from "react-router";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import { useOperatingNotes, useSaveOperatingNotes } from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ErrorState } from "@/components/ui/ErrorState";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { Textarea } from "@/components/ui/Textarea";
import { cn } from "@/utils/cn";

/** The server trims and counts characters (code points), so the counter does the same. */
const countCharacters = (text: string) => [...text.trim()].length;

/** A short note the application's team writes for the AI. Guidance, not evidence: it never changes alert rules or noise policy. */
export function OperatingNotesSection({ applicationId, canEdit }: { applicationId: string; canEdit: boolean }) {
  const { t } = useTranslation("applications");
  const notesQuery = useOperatingNotes(applicationId);
  const saveNotes = useSaveOperatingNotes(applicationId);
  const [draft, setDraft] = useState<string | null>(null);
  const [hasJustSaved, setHasJustSaved] = useState(false);
  const isProceeding = useRef(false);

  const stored = notesQuery.data;
  const value = draft ?? stored?.text ?? "";
  const isDirty = canEdit && draft !== null && draft.trim() !== (stored?.text ?? "");
  const characterCount = countCharacters(value);
  const maximumCharacters = stored?.maximumCharacters ?? 0;
  const isOverLimit = stored !== undefined && characterCount > maximumCharacters;
  const serverMessage = saveNotes.isError ? (isApiError(saveNotes.error) ? (saveNotes.error.fieldErrors[0]?.message ?? saveNotes.error.detail) : t("operatingNotes.saveFailed")) : undefined;

  // Unsaved text is lost on reload, tab close and when the person moves to another step, so both are guarded.
  const blocker = useBlocker(isDirty);
  useEffect(() => {
    if (!isDirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty]);

  useEffect(() => { if (blocker.state === "unblocked") isProceeding.current = false; }, [blocker.state]);

  const edit = (text: string) => {
    setDraft(text);
    setHasJustSaved(false);
    saveNotes.reset();
  };
  const save = () => saveNotes.mutate(value, { onSuccess: () => { setDraft(null); setHasJustSaved(true); } });
  const discard = () => { setDraft(null); saveNotes.reset(); };

  return (
    <section className="flex flex-col gap-3" aria-labelledby="operating-notes-title">
      <SectionHeader level={3} title={<span id="operating-notes-title">{t("operatingNotes.title")}</span>} description={t("operatingNotes.description")} />
      {notesQuery.isError ? (
        <ErrorState size="sm" error={notesQuery.error} onRetry={() => void notesQuery.refetch()} />
      ) : !stored ? (
        <Skeleton className="h-36 rounded-lg" />
      ) : (
        <>
          <Textarea
            label={t("operatingNotes.label")}
            rows={7}
            autoResize
            maximumRows={16}
            value={value}
            readOnly={!canEdit}
            placeholder={canEdit ? t("operatingNotes.placeholder") : t("operatingNotes.empty")}
            onChange={(event) => edit(event.target.value)}
            errorMessage={isOverLimit ? t("operatingNotes.overLimit", { excess: characterCount - maximumCharacters }) : undefined}
            helperText={t("operatingNotes.helper")}
          />
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-caption text-muted">
            <span>
              {stored.updatedAt && stored.updatedBy ? (
                <>{t("operatingNotes.lastEditedBy", { name: stored.updatedBy })} <RelativeTime value={stored.updatedAt} /></>
              ) : (
                t("operatingNotes.neverEdited")
              )}
            </span>
            <span className={cn("tabular-numbers", isOverLimit && "font-semibold text-danger")} aria-live={isOverLimit ? "polite" : "off"}>
              {t("operatingNotes.counter", { used: characterCount, maximum: maximumCharacters })}
            </span>
          </div>
          {!canEdit ? <p className="text-caption text-muted">{t("operatingNotes.readOnly")}</p> : null}
          {serverMessage ? <Banner tone="danger" title={t("operatingNotes.saveFailedTitle")}>{serverMessage}</Banner> : null}
          {hasJustSaved && !isDirty ? <Banner tone="success" title={t("operatingNotes.savedTitle")} onDismiss={() => setHasJustSaved(false)}>{t("operatingNotes.savedBody")}</Banner> : null}
          {canEdit ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={!isDirty || isOverLimit} isLoading={saveNotes.isPending} onClick={save}>{t("operatingNotes.save")}</Button>
              {isDirty ? <Button size="sm" variant="ghost" disabled={saveNotes.isPending} onClick={discard}>{t("operatingNotes.discard")}</Button> : null}
              {isDirty ? <span className="text-caption text-muted">{t("operatingNotes.unsaved")}</span> : null}
            </div>
          ) : null}
        </>
      )}
      <ConfirmDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => { if (!open && !isProceeding.current && blocker.state === "blocked") blocker.reset(); }}
        tone="primary"
        title={t("operatingNotes.leaveTitle")}
        description={t("operatingNotes.leaveBody")}
        confirmLabel={t("operatingNotes.leaveConfirm")}
        cancelLabel={t("operatingNotes.leaveStay")}
        onConfirm={() => { isProceeding.current = true; if (blocker.state === "blocked") blocker.proceed(); }}
      />
    </section>
  );
}
