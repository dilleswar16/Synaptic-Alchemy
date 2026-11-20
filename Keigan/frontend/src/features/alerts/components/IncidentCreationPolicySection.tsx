import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useApplication, useServiceNowGroups, useUpdateApplication, type IncidentCreationPolicy } from "@/api/applicationsApi";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Select } from "@/components/ui/Select";

/** Step 7d: when an alert group scores high enough, suggest or automatically create a ServiceNow incident. */
export function IncidentCreationPolicySection({ applicationId, canEdit, onChanged }: { applicationId: string; canEdit: boolean; onChanged?: () => void }) {
  const { t } = useTranslation("alerts");
  const applicationQuery = useApplication(applicationId);
  const groupsQuery = useServiceNowGroups(applicationId);
  const updateApplication = useUpdateApplication(applicationId);
  const [draft, setDraft] = useState<IncidentCreationPolicy>({ mode: "suggest", minimumScore: 70, assignmentGroupName: null });
  const [isDirty, setIsDirty] = useState(false);
  const stored = applicationQuery.data?.incidentCreationPolicy;
  useEffect(() => { if (stored && !isDirty) setDraft(stored); }, [stored, isDirty]);
  const edit = (patch: Partial<IncidentCreationPolicy>) => { setDraft({ ...draft, ...patch }); setIsDirty(true); };
  const groupOptions = [{ value: "none", label: t("incidentPolicy.noGroup") }, ...(groupsQuery.data ?? []).map((group) => ({ value: group.groupName, label: group.groupName }))];

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader level={3} title={t("incidentPolicy.title")} description={t("incidentPolicy.description")} />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-body">
        {t("incidentPolicy.whenScore")}
        <Input size="sm" type="number" min={0} max={100} aria-label={t("incidentPolicy.threshold")} disabled={!canEdit} value={draft.minimumScore} onChange={(event) => edit({ minimumScore: Number(event.target.value) })} containerClassName="inline-flex w-24" />
        {t("incidentPolicy.thenDo")}
        <Select size="sm" aria-label={t("incidentPolicy.mode")} disabled={!canEdit} value={draft.mode} onValueChange={(value) => edit({ mode: value })} className="w-56"
          options={[{ value: "suggest", label: t("incidentPolicy.suggest") }, { value: "automatic", label: t("incidentPolicy.automatic") }]} />
        {t("incidentPolicy.inGroup")}
        <Select size="sm" aria-label={t("incidentPolicy.group")} disabled={!canEdit} value={draft.assignmentGroupName ?? "none"} onValueChange={(value) => edit({ assignmentGroupName: value === "none" ? null : value })} className="w-60" options={groupOptions} />
      </div>
      {isDirty && canEdit ? <div><Button size="sm" isLoading={updateApplication.isPending} onClick={() => updateApplication.mutate({ incidentCreationPolicy: draft }, { onSuccess: () => { setIsDirty(false); onChanged?.(); } })}>{t("incidentPolicy.save")}</Button></div> : null}
    </section>
  );
}
