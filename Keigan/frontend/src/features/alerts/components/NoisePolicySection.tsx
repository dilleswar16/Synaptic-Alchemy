import { useState, type ReactNode } from "react";
import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useCreateMaintenanceWindow, useCreateMuteRule, useDeleteMaintenanceWindow, useDeleteMuteRule, useMaintenanceWindows, useMuteRules, useNoisePolicy, usePreviewNoisePolicy, useUpdateNoisePolicy,
  type Funnel, type MaintenanceWindow, type MuteRule, type NoisePolicySettings,
} from "@/api/alertsApi";
import { useServices } from "@/api/applicationsApi";
import { FunnelChart } from "@/components/charts";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Switch } from "@/components/ui/Switch";
import { Textarea } from "@/components/ui/Textarea";
import { formatDateTime } from "@/utils/formatters";
import { useFunnelStepLabel } from "./AlertBadges";

/** Environment sets an admin can pick for "only investigate alerts from"; the empty selection means all. */
const environmentGroups = [["prod"], ["prod", "uat"], ["prod", "uat", "test", "dev"]];
const severityOptions = (label: (level: number) => string) => [0, 1, 2, 3, 4].map((level) => ({ value: String(level), label: label(level) }));
const toLocalInputValue = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);

function InlineNumber({ value, onChange, disabled, label, suffix }: { value: number; onChange: (value: number) => void; disabled: boolean; label: string; suffix?: string }) {
  return <Input size="sm" type="number" min={0} aria-label={label} disabled={disabled} value={value} onChange={(event) => onChange(Number(event.target.value))} containerClassName="inline-flex w-24 align-middle" trailingContent={suffix} />;
}

/** Step 7c: the noise policy as editable sentences, maintenance windows, mute rules and the 7-day preview funnel. */
export function NoisePolicySection({ applicationId, canEdit, onChanged }: { applicationId: string; canEdit: boolean; onChanged?: () => void }) {
  const { t } = useTranslation("alerts");
  const { t: translateCommon } = useTranslation("common");
  const minutesSuffix = translateCommon("units.minutesShort");
  const policyQuery = useNoisePolicy(applicationId);
  const updatePolicy = useUpdateNoisePolicy(applicationId);
  const previewPolicy = usePreviewNoisePolicy(applicationId);
  const windowsQuery = useMaintenanceWindows(applicationId);
  const muteRulesQuery = useMuteRules(applicationId);
  const deleteWindow = useDeleteMaintenanceWindow(applicationId);
  const deleteMuteRule = useDeleteMuteRule(applicationId);
  const stepLabel = useFunnelStepLabel();
  const [draft, setDraft] = useState<NoisePolicySettings | null>(null);
  const [preview, setPreview] = useState<Funnel | null>(null);
  const [isWindowOpen, setIsWindowOpen] = useState(false);
  const [isMuteOpen, setIsMuteOpen] = useState(false);
  const policy = policyQuery.data;
  const settings = draft ?? policy?.policySettings;
  const change = (patch: Partial<NoisePolicySettings>) => settings && setDraft({ ...settings, ...patch });
  const sevLabel = (level: number) => t("severity", { level });

  if (policyQuery.isLoading) return <Skeleton className="h-64 w-full" />;
  if (policyQuery.isError || !policy || !settings) return <ErrorState size="sm" error={policyQuery.error} onRetry={() => policyQuery.refetch()} />;
  const disabled = !canEdit;
  const toggleSeverity = (level: number) => change({ noDelaySeverities: settings.noDelaySeverities.includes(level) ? settings.noDelaySeverities.filter((item) => item !== level) : [...settings.noDelaySeverities, level].sort() });

  const sentences: Array<{ key: string; content: ReactNode }> = [
    { key: "severity", content: <>{t("policy.minSeverityA")} <Select size="sm" aria-label={t("policy.minSeverityA")} disabled={disabled} value={String(settings.minSeverity)} onValueChange={(value) => change({ minSeverity: Number(value) })} options={severityOptions(sevLabel)} className="inline-flex w-28 align-middle" /> {t("policy.minSeverityB")}</> },
    { key: "environments", content: <>{t("policy.environmentsA")} <Select size="sm" aria-label={t("policy.environmentsA")} disabled={disabled} value={settings.investigateEnvironments.join(",") || "all"} onValueChange={(value) => change({ investigateEnvironments: value === "all" ? [] : value.split(",") })}
      options={[...environmentGroups.map((group) => ({ value: group.join(","), label: group.map((environment) => translateCommon(`environment.${environment}`)).join(", ") })), { value: "all", label: t("policy.allEnvironments") }]} className="inline-flex w-44 align-middle" /> {t("policy.environmentsB")}</> },
    { key: "settle", content: <>{t("policy.settleA")} <InlineNumber label={t("policy.settleA")} value={settings.settleDelayMinutes} disabled={disabled} onChange={(value) => change({ settleDelayMinutes: value })} suffix={minutesSuffix} /> {t("policy.settleB")}{" "}
      {[0, 1, 2].map((level) => <Button key={level} variant={settings.noDelaySeverities.includes(level) ? "primary" : "secondary"} size="sm" disabled={disabled} onClick={() => toggleSeverity(level)} className="mx-0.5">{sevLabel(level)}</Button>)}</> },
    { key: "reopen", content: <>{t("policy.reopenA")} <InlineNumber label={t("policy.reopenA")} value={settings.reopenWindowMinutes} disabled={disabled} onChange={(value) => change({ reopenWindowMinutes: value })} suffix={minutesSuffix} /> {t("policy.reopenB")}</> },
    { key: "group", content: <>{t("policy.groupA")} <InlineNumber label={t("policy.groupA")} value={settings.groupWindowMinutes} disabled={disabled} onChange={(value) => change({ groupWindowMinutes: Math.max(1, value) })} suffix={minutesSuffix} /> {t("policy.groupB")}</> },
    { key: "flap", content: <>{t("policy.flapA")} <InlineNumber label={t("policy.flapA")} value={settings.flapCount} disabled={disabled} onChange={(value) => change({ flapCount: Math.max(2, value) })} /> {t("policy.flapB")} <InlineNumber label={t("policy.flapB")} value={settings.flapWindowMinutes} disabled={disabled} onChange={(value) => change({ flapWindowMinutes: Math.max(1, value) })} suffix={minutesSuffix} /> {t("policy.flapC")}</> },
    { key: "rate", content: <>{t("policy.rateA")} <InlineNumber label={t("policy.rateA")} value={settings.maxInvestigationsPerHour} disabled={disabled} onChange={(value) => change({ maxInvestigationsPerHour: Math.max(1, value) })} /> {t("policy.rateB")}</> },
    { key: "threshold", content: <>{t("policy.thresholdA")} <InlineNumber label={t("policy.thresholdA")} value={settings.investigateScoreThreshold} disabled={disabled} onChange={(value) => change({ investigateScoreThreshold: value })} /> {t("policy.thresholdB")}</> },
  ];

  const save = () => updatePolicy.mutate({ policySettings: settings }, { onSuccess: () => { setDraft(null); onChanged?.(); } });
  const windowColumns: DataTableColumn<MaintenanceWindow>[] = [
    { key: "name", header: t("windows.name"), cell: (row) => <span className="font-semibold">{row.windowName}</span> },
    { key: "scope", header: t("windows.scope"), cell: (row) => row.appliesToServiceNames.join(", ") || t("windows.wholeApplication") },
    { key: "when", header: t("windows.when"), cell: (row) => `${formatDateTime(row.startsAt)} – ${formatDateTime(row.endsAt)}` },
    { key: "repeat", header: t("windows.repeat"), cell: (row) => (row.repeatsWeekly ? t("windows.weekly") : t("windows.once")) },
    { key: "active", header: t("windows.state"), cell: (row) => (row.isActiveNow ? <StatusChip tone="warning" size="sm" dot>{t("windows.active")}</StatusChip> : null) },
    { key: "actions", header: "", cell: (row) => canEdit ? <Button variant="ghost" size="sm" aria-label={t("windows.delete")} leadingIcon={Trash2} onClick={() => deleteWindow.mutate(row.maintenanceWindowId)} /> : null },
  ];
  const muteColumns: DataTableColumn<MuteRule>[] = [
    { key: "name", header: t("mute.name"), cell: (row) => <span className="font-semibold">{row.ruleName}</span> },
    { key: "matcher", header: t("mute.matcher"), cell: (row) => Object.entries(row.matcher).map(([key, value]) => `${key}: ${String(value)}`).join(", ") },
    { key: "reason", header: t("mute.reason"), cell: (row) => <span className="line-clamp-2 text-body-sm">{row.muteReason}</span> },
    { key: "expires", header: t("mute.expires"), cell: (row) => (row.isExpired ? <StatusChip tone="neutral" size="sm" icon={false}>{t("mute.expired")}</StatusChip> : formatDateTime(row.expiresAt)) },
    { key: "actions", header: "", cell: (row) => canEdit ? <Button variant="ghost" size="sm" aria-label={t("mute.delete")} leadingIcon={Trash2} onClick={() => deleteMuteRule.mutate(row.muteRuleId)} /> : null },
  ];

  return (
    <section className="flex flex-col gap-5">
      <SectionHeader level={3} title={t("policy.title")} description={t("policy.description")} actions={canEdit ? <Button variant="ghost" size="sm" leadingIcon={RotateCcw} onClick={() => updatePolicy.mutate({ resetToDefaults: true }, { onSuccess: () => { setDraft(null); onChanged?.(); } })}>{t("policy.reset")}</Button> : undefined} />
      <ul className="flex flex-col gap-3">
        {sentences.map((sentence) => <li key={sentence.key} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-body">{sentence.content}</li>)}
        <li className="flex flex-wrap items-center gap-2 text-body">
          {t("policy.modeA")}
          <Switch aria-label={t("policy.modeActive")} disabled={disabled} checked={policy.policyMode === "active"} onCheckedChange={(isActive) => updatePolicy.mutate({ policyMode: isActive ? "active" : "observe" }, { onSuccess: onChanged })} label={policy.policyMode === "active" ? t("policy.modeActive") : t("policy.modeObserve")} />
        </li>
      </ul>
      {policy.policyMode === "observe" && policy.observedEffect ? <Banner tone="info" title={t("policy.beforeSwitch")}>{policy.observedEffect.summarySentence}</Banner> : null}
      {policy.dependencyHint ? <p className="text-caption text-muted">{policy.dependencyHint}</p> : null}
      {draft ? <div className="flex gap-2"><Button size="sm" isLoading={updatePolicy.isPending} onClick={save}>{t("policy.save")}</Button><Button size="sm" variant="ghost" onClick={() => setDraft(null)}>{t("policy.discard")}</Button></div> : null}

      <div className="flex flex-col gap-3">
        <SectionHeader level={3} title={t("windows.title")} description={t("windows.description")} actions={canEdit ? <Button size="sm" variant="secondary" leadingIcon={Plus} onClick={() => setIsWindowOpen(true)}>{t("windows.add")}</Button> : undefined} />
        <DataTable columns={windowColumns} rows={windowsQuery.data ?? []} getRowId={(row) => row.maintenanceWindowId} caption={t("windows.title")} isLoading={windowsQuery.isLoading} density="dense" emptyState={<EmptyState size="sm" title={t("windows.empty")} />} />
      </div>
      <div className="flex flex-col gap-3">
        <SectionHeader level={3} title={t("mute.title")} description={t("mute.description")} actions={canEdit ? <Button size="sm" variant="secondary" leadingIcon={Plus} onClick={() => setIsMuteOpen(true)}>{t("mute.add")}</Button> : undefined} />
        <DataTable columns={muteColumns} rows={muteRulesQuery.data ?? []} getRowId={(row) => row.muteRuleId} caption={t("mute.title")} isLoading={muteRulesQuery.isLoading} density="dense" emptyState={<EmptyState size="sm" title={t("mute.empty")} />} />
      </div>
      <div className="flex flex-col gap-3">
        <SectionHeader level={3} title={t("preview.title")} description={t("preview.description")} actions={<Button size="sm" variant="secondary" isLoading={previewPolicy.isPending} onClick={() => previewPolicy.mutate(settings, { onSuccess: setPreview })}>{t("preview.run")}</Button>} />
        {preview ? (
          <div className="flex flex-col gap-2">
            {preview.isIllustration ? <Banner tone="neutral">{t("preview.illustration")}</Banner> : <p className="text-body-sm">{preview.summarySentence}</p>}
            <FunnelChart ariaLabel={t("preview.title")} stages={preview.steps.map((step) => ({ key: step.stepKey, label: stepLabel(step), count: step.count }))} />
          </div>
        ) : null}
      </div>
      <MaintenanceWindowDialog applicationId={applicationId} open={isWindowOpen} onOpenChange={setIsWindowOpen} />
      <MuteRuleDialog applicationId={applicationId} open={isMuteOpen} onOpenChange={setIsMuteOpen} />
    </section>
  );
}

function MaintenanceWindowDialog({ applicationId, open, onOpenChange }: { applicationId: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation("alerts");
  const create = useCreateMaintenanceWindow(applicationId);
  const servicesQuery = useServices(applicationId);
  const [name, setName] = useState("");
  const [serviceId, setServiceId] = useState("all");
  const [startsAt, setStartsAt] = useState(toLocalInputValue(new Date()));
  const [endsAt, setEndsAt] = useState(toLocalInputValue(new Date(Date.now() + 3_600_000)));
  const [repeatsWeekly, setRepeatsWeekly] = useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("windows.add")} footer={<Button isLoading={create.isPending} disabled={name.trim().length < 2} onClick={() => create.mutate({ windowName: name, appliesToServiceIds: serviceId === "all" ? [] : [serviceId], startsAt: new Date(startsAt).toISOString(), endsAt: new Date(endsAt).toISOString(), repeatsWeekly }, { onSuccess: () => onOpenChange(false) })}>{t("windows.create")}</Button>}>
      <div className="flex flex-col gap-3">
        <Input label={t("windows.name")} value={name} onChange={(event) => setName(event.target.value)} />
        <Select label={t("windows.scope")} value={serviceId} onValueChange={setServiceId} options={[{ value: "all", label: t("windows.wholeApplication") }, ...(servicesQuery.data ?? []).map((service) => ({ value: service.serviceId, label: service.serviceName }))]} />
        <Input label={t("windows.starts")} type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} />
        <Input label={t("windows.ends")} type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} />
        <Switch label={t("windows.weekly")} checked={repeatsWeekly} onCheckedChange={setRepeatsWeekly} />
      </div>
    </Dialog>
  );
}

function MuteRuleDialog({ applicationId, open, onOpenChange }: { applicationId: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation("alerts");
  const create = useCreateMuteRule(applicationId);
  const [name, setName] = useState("");
  const [contains, setContains] = useState("");
  const [severity, setSeverity] = useState("any");
  const [reason, setReason] = useState("");
  const [expiresAt, setExpiresAt] = useState(toLocalInputValue(new Date(Date.now() + 7 * 86_400_000)));
  const isValid = name.trim().length >= 2 && reason.trim().length >= 3 && (contains.trim() !== "" || severity !== "any");
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("mute.add")} footer={<Button isLoading={create.isPending} disabled={!isValid} onClick={() => create.mutate({ ruleName: name, matcher: { ruleNameContains: contains || null, severity: severity === "any" ? null : Number(severity) }, muteReason: reason, expiresAt: new Date(expiresAt).toISOString() }, { onSuccess: () => onOpenChange(false) })}>{t("mute.create")}</Button>}>
      <div className="flex flex-col gap-3">
        <Input label={t("mute.name")} value={name} onChange={(event) => setName(event.target.value)} />
        <Input label={t("mute.ruleContains")} value={contains} onChange={(event) => setContains(event.target.value)} />
        <Select label={t("mute.severity")} value={severity} onValueChange={setSeverity} options={[{ value: "any", label: t("mute.anySeverity") }, ...severityOptions((level) => t("severity", { level }))]} />
        <Textarea label={t("mute.reason")} rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
        <Input label={t("mute.expires")} type="datetime-local" helperText={t("mute.expiresHelp")} value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
      </div>
    </Dialog>
  );
}
