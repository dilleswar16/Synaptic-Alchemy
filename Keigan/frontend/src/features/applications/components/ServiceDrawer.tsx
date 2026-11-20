import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  fetchDiagnosticSettingCommand,
  useReplaceDependencies,
  useServiceDependencies,
  useServices,
  useUpdateService,
  type MonitoredServiceRow,
  type ServiceUpdateBody,
} from "@/api/applicationsApi";
import { Checkbox } from "@/components/ui/Checkbox";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { Drawer } from "@/components/ui/Drawer";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { LogSourceEditor } from "./LogSourceEditor";

/** Input that saves when it loses focus and the value changed, so the workspace save indicator tells the story. */
function AutosaveInput({ label, value, onSave, disabled, helperText }: { label: string; value: string | null; onSave: (value: string | null) => void; disabled?: boolean; helperText?: string }) {
  const [draft, setDraft] = useState(value ?? "");
  useEffect(() => setDraft(value ?? ""), [value]);
  return (
    <Input
      label={label}
      helperText={helperText}
      value={draft}
      disabled={disabled}
      isOptional
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => { if (draft !== (value ?? "")) onSave(draft.trim() || null); }}
    />
  );
}

const repositoryProviders = ["azure_devops", "github", "gitlab", "bitbucket", "other"];

interface ServiceDrawerProps {
  applicationId: string;
  serviceId: string | null;
  canEdit: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ServiceDrawer({ applicationId, serviceId, canEdit, onOpenChange }: ServiceDrawerProps) {
  const { t } = useTranslation("onboarding");
  const servicesQuery = useServices(applicationId);
  const dependenciesQuery = useServiceDependencies(applicationId);
  const updateService = useUpdateService(applicationId);
  const replaceDependencies = useReplaceDependencies(applicationId);
  const service: MonitoredServiceRow | undefined = servicesQuery.data?.find((candidate) => candidate.serviceId === serviceId);
  const lacksDiagnostics = service?.hasDiagnosticSetting === false;
  const commandQuery = useQuery({
    queryKey: ["applications", applicationId, "diagnostic-command", serviceId],
    queryFn: () => fetchDiagnosticSettingCommand(applicationId, serviceId ?? ""),
    enabled: !!serviceId && lacksDiagnostics,
  });

  const save = (body: ServiceUpdateBody) => service && updateService.mutate({ serviceId: service.serviceId, body });
  const otherServices = (servicesQuery.data ?? []).filter((candidate) => candidate.serviceId !== serviceId);
  const dependencies = dependenciesQuery.data ?? [];
  const dependsOn = new Set(dependencies.filter((dependency) => dependency.upstreamServiceId === serviceId).map((dependency) => dependency.downstreamServiceId));

  const toggleDependency = (downstreamServiceId: string, isChecked: boolean) => {
    const next = new Set(dependsOn);
    if (isChecked) next.add(downstreamServiceId);
    else next.delete(downstreamServiceId);
    const untouched = dependencies.filter((dependency) => dependency.upstreamServiceId !== serviceId);
    replaceDependencies.mutate([
      ...untouched.map(({ upstreamServiceId, downstreamServiceId: downstream, dependencyKind }) => ({ upstreamServiceId, downstreamServiceId: downstream, dependencyKind })),
      ...[...next].map((downstream) => ({ upstreamServiceId: serviceId ?? "", downstreamServiceId: downstream, dependencyKind: "calls" })),
    ]);
  };

  return (
    <Drawer
      open={serviceId !== null}
      onOpenChange={onOpenChange}
      size="md"
      title={service?.serviceName ?? ""}
      description={service ? `${t(`serviceTypes.${service.serviceType}`, { defaultValue: service.serviceType })}${service.componentName ? ` · ${service.componentName}` : ""}` : undefined}
    >
      {service ? (
        <div className="flex flex-col gap-8">
          <section className="flex flex-col gap-4">
            <SectionHeader level={3} title={t("serviceDrawer.basics")} />
            <AutosaveInput label={t("serviceDrawer.displayName")} value={service.serviceName} disabled={!canEdit} onSave={(value) => value && save({ serviceName: value })} />
            {service.serviceType === "aks" ? <AutosaveInput label={t("serviceDrawer.namespace")} helperText={t("serviceDrawer.namespaceHelp")} value={service.aksNamespaceFilter} disabled={!canEdit} onSave={(value) => save({ aksNamespaceFilter: value })} /> : null}
            <Textarea label={t("serviceDrawer.description")} isOptional rows={2} disabled={!canEdit} defaultValue={service.serviceDescription ?? ""} onBlur={(event) => { if (event.target.value !== (service.serviceDescription ?? "")) save({ serviceDescription: event.target.value || null }); }} />
          </section>

          <section className="flex flex-col gap-4">
            <SectionHeader level={3} title={t("serviceDrawer.repository")} description={t("serviceDrawer.repositoryHelp")} />
            <Select
              label={t("serviceDrawer.provider")}
              isOptional
              disabled={!canEdit}
              value={service.repositoryProvider ?? undefined}
              placeholder={t("add.choose")}
              options={repositoryProviders.map((provider) => ({ value: provider, label: t(`repositoryProviders.${provider}`) }))}
              onValueChange={(provider) => save({ repositoryProvider: provider })}
            />
            <AutosaveInput label={t("serviceDrawer.repositoryUrl")} value={service.repositoryUrl} disabled={!canEdit} onSave={(value) => save({ repositoryUrl: value })} />
            <div className="grid gap-4 sm:grid-cols-2">
              <AutosaveInput label={t("serviceDrawer.branch")} value={service.repositoryDefaultBranch} disabled={!canEdit} onSave={(value) => save({ repositoryDefaultBranch: value })} />
              <AutosaveInput label={t("serviceDrawer.path")} value={service.repositoryPath} disabled={!canEdit} onSave={(value) => save({ repositoryPath: value })} />
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <SectionHeader level={3} title={t("serviceDrawer.dependsOn")} description={t("serviceDrawer.dependsOnHelp")} />
            {otherServices.length === 0 ? <p className="text-body-sm text-muted">{t("serviceDrawer.noOtherServices")}</p> : null}
            <div className="grid gap-2 sm:grid-cols-2">
              {otherServices.map((candidate) => (
                <Checkbox key={candidate.serviceId} label={candidate.serviceName} disabled={!canEdit} checked={dependsOn.has(candidate.serviceId)} onCheckedChange={(checked) => toggleDependency(candidate.serviceId, checked === true)} />
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <SectionHeader level={3} title={t("serviceDrawer.logSources")} />
            <LogSourceEditor applicationId={applicationId} service={service} canEdit={canEdit} />
            {lacksDiagnostics && commandQuery.data ? (
              <details className="rounded-lg border border-hairline px-4 py-3">
                <summary className="cursor-pointer text-body-sm text-muted">{t("serviceDrawer.noDiagnosticSetting")}</summary>
                <p className="mt-2 text-body-sm text-muted">{commandQuery.data.explanation}</p>
                <CommandBlock
                  className="mt-3"
                  riskLevel="low"
                  commands={[
                    { key: "cli", label: t("roleGrant.tabs.cli"), content: commandQuery.data.cliCommand },
                    { key: "powershell", label: t("roleGrant.tabs.powershell"), content: commandQuery.data.powershellCommand },
                  ]}
                  wrapLines
                />
              </details>
            ) : null}
          </section>

          {service.availableMetrics?.length ? (
            <section className="flex flex-col gap-2">
              <SectionHeader level={3} title={t("serviceDrawer.metrics", { count: service.availableMetrics.length })} />
              <ul className="grid gap-x-6 gap-y-1 text-body-sm sm:grid-cols-2">
                {service.availableMetrics.map((metric) => (
                  <li key={metric.name} className="flex justify-between gap-2 border-b border-hairline py-1">
                    <span className="truncate">{metric.displayName}</span>
                    <span className="shrink-0 text-muted">{metric.unit}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
