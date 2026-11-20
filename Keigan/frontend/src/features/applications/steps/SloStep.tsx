import { useEffect, useState } from "react";
import { Info, Loader2, Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useServices } from "@/api/applicationsApi";
import { useAcceptSloProposals, useCreateCustomSli, useMeasureSloProposals, useSloProposals, type AcceptedProposalBody, type SliProposal } from "@/api/sloApi";
import { Sparkline } from "@/components/charts";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Checkbox";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { Tooltip } from "@/components/ui/Tooltip";
import { useToast } from "@/components/ui/Toast";
import { formatNumber } from "@/utils/formatters";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

interface RowState { isChecked: boolean; target: number; windowDays: 7 | 28 | 30 }
const measuringStages = ["Reading metric definitions", "Reading 30 days of data", "Calculating baselines"];

/** Step 8: Keigan measures 30 days, proposes SLIs and targets, and one click accepts them (sample plan 7.3). */
export function SloStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("slo");
  const { t: translateOnboarding } = useTranslation("onboarding");
  const { showToast } = useToast();
  const proposalsQuery = useSloProposals(applicationId);
  const measure = useMeasureSloProposals(applicationId);
  const accept = useAcceptSloProposals(applicationId);
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const proposals = proposalsQuery.data;
  const status = proposals?.measurementStatus;

  useEffect(() => {
    if (status === "not_started" && canEdit && !measure.isPending && !measure.isSuccess) measure.mutate();
  }, [status, canEdit]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!proposals || proposals.measurementStatus !== "ready") return;
    setRows((current) => {
      const next = { ...current };
      for (const group of proposals.groups) for (const proposal of group.proposals) {
        if (!next[proposal.proposalKey]) next[proposal.proposalKey] = { isChecked: proposal.isAvailable && proposal.isEnabledByDefault && proposal.proposedTargetPercentage !== null, target: proposal.proposedTargetPercentage ?? 99, windowDays: 30 };
      }
      return next;
    });
  }, [proposals]);

  const allProposals = proposals?.groups.flatMap((group) => group.proposals) ?? [];
  const toBody = (proposal: SliProposal): AcceptedProposalBody => ({ catalogEntryKey: proposal.catalogEntryKey, serviceId: proposal.serviceId, targetPercentage: rows[proposal.proposalKey]?.target ?? proposal.proposedTargetPercentage ?? 99, rollingWindowDays: rows[proposal.proposalKey]?.windowDays ?? 30, latencyThresholdMilliseconds: proposal.proposedLatencyThresholdMilliseconds });
  const selected = allProposals.filter((proposal) => rows[proposal.proposalKey]?.isChecked && proposal.isAvailable);
  const acceptSelected = () => accept.mutate(selected.map(toBody), { onSuccess: () => { showToast({ tone: "success", title: t("proposals.accepted", { count: selected.length }) }); onStatusChange?.(); } });
  const update = (key: string, patch: Partial<RowState>) => setRows((current) => ({ ...current, [key]: { isChecked: false, target: 99, windowDays: 30, ...current[key], ...patch } }));

  return (
    <StepFrame stepKey="slo">
      {proposalsQuery.isError ? <ErrorState error={proposalsQuery.error} onRetry={() => proposalsQuery.refetch()} /> : null}
      {status === "measuring" || status === "not_started" ? (
        <Card><CardBody className="flex flex-col gap-3">
          <p className="flex items-center gap-2 font-semibold"><Loader2 className="size-4 animate-spin" aria-hidden />{t("proposals.measuring")}</p>
          <ol className="flex flex-col gap-1 text-body-sm">
            {measuringStages.map((stage, index) => {
              const currentIndex = Math.max(0, measuringStages.indexOf(proposals?.progressStage ?? "Reading metric definitions"));
              return <li key={stage} className={index <= currentIndex ? "font-semibold" : "text-muted"}>{t(`proposals.stages.${index}`)}</li>;
            })}
          </ol>
          <p className="text-caption text-muted">{t("proposals.measuringHelp")}</p>
        </CardBody></Card>
      ) : null}
      {status === "failed" ? <Banner tone="danger" title={t("proposals.failed")} action={canEdit ? <Button size="sm" variant="secondary" onClick={() => measure.mutate()}>{t("proposals.retry")}</Button> : undefined}>{proposals?.errorMessage}</Banner> : null}
      {status === "ready" && proposals ? (
        <div className="flex flex-col gap-6">
          <SectionHeader level={3} title={t("proposals.suggests", { slos: proposals.suggestedSloCount, services: proposals.serviceCount })} description={proposals.explanation}
            actions={canEdit ? <div className="flex gap-2"><Button variant="ghost" size="sm" onClick={() => measure.mutate()} isLoading={measure.isPending}>{t("proposals.remeasure")}</Button><Button isLoading={accept.isPending} disabled={selected.length === 0} onClick={acceptSelected}>{t("proposals.acceptSuggested")}</Button></div> : undefined} />
          {proposals.headlineProposal ? (
            <Card accent radius="lg"><CardBody className="flex flex-wrap items-center justify-between gap-3">
              <div><StatusChip tone="brand" size="sm" icon={Target}>{t("proposals.headline")}</StatusChip><p className="mt-1 font-semibold">{proposals.headlineProposal.serviceName}: {proposals.headlineProposal.sliName}</p><p className="text-body-sm text-muted">{proposals.headlineProposal.explanation}</p></div>
              <div className="text-end"><p className="text-h2 font-semibold">{proposals.headlineProposal.proposedTargetPercentage} %</p><p className="text-caption text-muted">{proposals.headlineProposal.errorBudgetText}</p></div>
            </CardBody></Card>
          ) : null}
          {proposals.groups.map((group) => (
            <details key={group.serviceId} open className="rounded-md border border-hairline">
              <summary className="cursor-pointer px-4 py-3 font-semibold">{group.serviceName} <span className="text-caption font-normal text-muted">{translateOnboarding(`serviceTypes.${group.serviceType}`, { defaultValue: group.serviceType })}</span></summary>
              <div className="overflow-x-auto">
                <table className="w-full text-body-sm">
                  <thead><tr className="text-left text-caption text-muted"><th className="px-4 py-2" /><th>{t("proposals.columns.sli")}</th><th>{t("proposals.columns.measured")}</th><th>{t("proposals.columns.target")}</th></tr></thead>
                  <tbody>
                    {group.proposals.map((proposal) => {
                      const row = rows[proposal.proposalKey];
                      return (
                        <tr key={proposal.proposalKey} className="border-t border-hairline align-top">
                          <td className="px-4 py-3"><Checkbox aria-label={proposal.sliName} checked={Boolean(row?.isChecked) && !proposal.alreadyAccepted} disabled={!canEdit || !proposal.isAvailable || proposal.alreadyAccepted} onCheckedChange={(value) => update(proposal.proposalKey, { isChecked: value === true })} /></td>
                          <td className="py-3 pr-3">
                            <span className="flex flex-wrap items-center gap-1.5 font-semibold">{proposal.sliName}
                              <Tooltip content={proposal.explanation}><button type="button" aria-label={t("proposals.explain")} className="text-muted"><Info className="size-3.5" /></button></Tooltip>
                              {proposal.isApproximate ? <StatusChip tone="neutral" size="sm" variant="outline" icon={false}>{t("proposals.approximate")}</StatusChip> : null}
                              {proposal.alreadyAccepted ? <StatusChip tone="success" size="sm" icon={false}>{t("proposals.alreadyAccepted")}</StatusChip> : null}
                            </span>
                            <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 font-normal">
                              <StatusChip tone="neutral" size="sm" variant="outline" icon={false}>{proposal.sourceChip}</StatusChip>
                              {proposal.isAvailable && row ? (
                                <span className="flex items-center gap-1.5 text-caption text-muted">
                                  {t("proposals.columns.window")}
                                  <Select size="sm" aria-label={t("proposals.columns.window")} disabled={!canEdit || proposal.alreadyAccepted} value={String(row.windowDays)} onValueChange={(value) => update(proposal.proposalKey, { windowDays: Number(value) as 7 | 28 | 30 })} options={["7", "28", "30"].map((days) => ({ value: days, label: t("proposals.days", { days }) }))} className="w-28" />
                                </span>
                              ) : null}
                              {proposal.errorBudgetText ? <span className="text-caption text-muted">{t("proposals.columns.budget")}: {proposal.errorBudgetText}</span> : null}
                            </span>
                            {proposal.disabledReason ? <span className="mt-1 block text-caption text-muted">{proposal.disabledReason}</span> : null}
                            {proposal.warning ? <span className="block text-caption text-warning">{proposal.warning}</span> : null}
                          </td>
                          <td className="py-3 pr-3">{proposal.measuredPercentage === null ? "–" : <span className="flex items-center gap-2 whitespace-nowrap">{formatNumber(proposal.measuredPercentage, { maximumFractionDigits: 3 })} %<Sparkline values={proposal.sparkline} width={72} height={22} ariaLabel={t("proposals.sparkline", { name: proposal.sliName })} /></span>}</td>
                          <td className="py-3 pr-3">{proposal.isAvailable && row ? <Input size="sm" type="number" step="0.01" aria-label={t("proposals.columns.target")} disabled={!canEdit || proposal.alreadyAccepted} value={row.target} onChange={(event) => update(proposal.proposalKey, { target: Number(event.target.value) })} containerClassName="w-28" trailingContent="%" /> : "–"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {group.supportingSignals.length > 0 ? (
                <details className="border-t border-hairline px-4 py-2"><summary className="cursor-pointer text-body-sm font-semibold">{t("proposals.supporting", { count: group.supportingSignals.length })}</summary>
                  <ul className="mt-2 list-disc pl-5 text-body-sm text-muted">{group.supportingSignals.map((signal) => <li key={signal.signalKey}>{signal.signalName}{signal.description ? `: ${signal.description}` : ""}</li>)}</ul></details>
              ) : null}
            </details>
          ))}
          {proposals.groups.length === 0 ? <EmptyState isBordered title={t("proposals.emptyTitle")} description={t("proposals.emptyDescription")} /> : null}
          {canEdit ? <CustomSliForm applicationId={applicationId} onSaved={onStatusChange} /> : null}
        </div>
      ) : null}
    </StepFrame>
  );
}

function CustomSliForm({ applicationId, onSaved }: { applicationId: string; onSaved?: () => void }) {
  const { t } = useTranslation("slo");
  const createSli = useCreateCustomSli(applicationId);
  const [name, setName] = useState("");
  const [kql, setKql] = useState("");
  const [target, setTarget] = useState(99.5);
  const servicesQuery = useServices(applicationId);
  const [serviceId, setServiceId] = useState<string>("");
  return (
    <details className="rounded-md border border-hairline px-4 py-3">
      <summary className="cursor-pointer font-semibold">{t("custom.title")}</summary>
      <div className="mt-3 flex flex-col gap-3">
        <p className="text-body-sm text-muted">{t("custom.description")}</p>
        <Select label={t("custom.service")} value={serviceId || undefined} onValueChange={setServiceId} placeholder={t("custom.servicePlaceholder")} options={(servicesQuery.data ?? []).map((service) => ({ value: service.serviceId, label: service.serviceName }))} />
        <Input label={t("custom.name")} value={name} onChange={(event) => setName(event.target.value)} />
        <Textarea label={t("custom.query")} helperText={t("custom.queryHelp")} isMonospace rows={5} value={kql} onChange={(event) => setKql(event.target.value)} />
        <Input label={t("custom.target")} type="number" step="0.01" value={target} onChange={(event) => setTarget(Number(event.target.value))} containerClassName="w-40" trailingContent="%" />
        <div><Button size="sm" isLoading={createSli.isPending} disabled={name.trim().length < 2 || !kql.trim() || !serviceId} onClick={() => createSli.mutate({ serviceId, sliName: name, sliKind: "availability", dataSourceKind: "log_query", queryDefinition: { kql }, targetPercentage: target, rollingWindowDays: 30 }, { onSuccess: () => { setName(""); setKql(""); onSaved?.(); } })}>{t("custom.save")}</Button></div>
      </div>
    </details>
  );
}
