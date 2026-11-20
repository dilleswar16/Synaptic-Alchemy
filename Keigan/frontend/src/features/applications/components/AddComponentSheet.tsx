import { useState } from "react";
import { Cloud, Cpu, Network, Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import { isApiError } from "@/api/httpClient";
import {
  useAddComponent,
  useComponentJob,
  useLogToolConnections,
  usePlatformIdentity,
  type ApplicationComponent,
  type ComponentType,
  type CreateComponentBody,
  type EnvironmentName,
} from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Drawer } from "@/components/ui/Drawer";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { TokenInput } from "@/components/ui/TokenInput";
import { RoleGrantPanel } from "./RoleGrantPanel";

const environments: EnvironmentName[] = ["dev", "test", "uat", "prod"];
const guidPattern = /^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/;
const typeIcons = { azure_resource_group: Cloud, hardware: Network, mainframe: Server, saas_platform: Cpu } as const;
const hardwareCategories = ["server", "network_switch", "router", "firewall", "load_balancer", "storage_array", "other"];
const mainframeSubsystems = ["CICS", "IMS", "DB2", "MQ", "Batch"];

type FieldKind = "text" | "select" | "tokens" | "logTool" | "textarea";
interface FieldDefinition {
  key: string;
  kind: FieldKind;
  isRequired?: boolean;
  options?: string[];
}

/** Type-specific fields (spec 6.3). Keys are stored in `componentConfiguration` exactly as written here. */
const fieldsByType: Record<Exclude<ComponentType, "azure_resource_group">, FieldDefinition[]> = {
  hardware: [
    { key: "device_category", kind: "select", isRequired: true, options: hardwareCategories },
    { key: "hostname", kind: "text" },
    { key: "location", kind: "text" },
    { key: "cmdb_ci", kind: "text" },
    { key: "owner_team", kind: "text" },
    { key: "log_tool_connection_id", kind: "logTool" },
    { key: "query_host", kind: "text" },
    { key: "notes", kind: "textarea" },
  ],
  mainframe: [
    { key: "lpar", kind: "text" },
    { key: "subsystems", kind: "tokens", isRequired: true, options: mainframeSubsystems },
    { key: "job_name_prefixes", kind: "tokens" },
    { key: "log_tool_connection_id", kind: "logTool" },
    { key: "query_index", kind: "text" },
    { key: "owner_team", kind: "text" },
    { key: "batch_window", kind: "text" },
  ],
  saas_platform: [
    { key: "vendor_name", kind: "text", isRequired: true },
    { key: "product_name", kind: "text" },
    { key: "instance_url", kind: "text" },
    { key: "status_page_url", kind: "text" },
    { key: "synthetic_probe_url", kind: "text" },
    { key: "vendor_api_endpoint", kind: "text" },
    { key: "support_contact", kind: "text" },
    { key: "contractual_sla", kind: "text" },
  ],
};

interface AddComponentSheetProps {
  applicationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Phase = "type" | "details" | "access";

export function AddComponentSheet({ applicationId, open, onOpenChange }: AddComponentSheetProps) {
  const { t } = useTranslation("onboarding");
  const addComponent = useAddComponent(applicationId);
  const verifyComponent = useComponentJob(applicationId, "verify");
  const identityQuery = usePlatformIdentity();
  const logToolsQuery = useLogToolConnections(applicationId);
  const [phase, setPhase] = useState<Phase>("type");
  const [componentType, setComponentType] = useState<ComponentType>("azure_resource_group");
  const [created, setCreated] = useState<ApplicationComponent | null>(null);
  const [environmentName, setEnvironmentName] = useState<EnvironmentName>("prod");
  const [componentName, setComponentName] = useState("");
  const [scope, setScope] = useState({ tenantId: "", subscriptionId: "", subscriptionName: "", resourceGroupName: "", pastedLines: "" });
  const [values, setValues] = useState<Record<string, string>>({});
  const [tokenValues, setTokenValues] = useState<Record<string, string[]>>({});
  const [bulkError, setBulkError] = useState<string | null>(null);

  const reset = () => {
    setPhase("type");
    setCreated(null);
    setComponentName("");
    setScope({ tenantId: "", subscriptionId: "", subscriptionName: "", resourceGroupName: "", pastedLines: "" });
    setValues({});
    setTokenValues({});
    setBulkError(null);
    addComponent.reset();
  };
  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) reset();
  };
  const fieldError = (field: string) => (isApiError(addComponent.error) ? addComponent.error.fieldErrorFor(field) : undefined);

  const pastedScopes = scope.pastedLines
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [subscriptionId, resourceGroupName] = line.split("/").map((part) => part.trim());
      return { subscriptionId, resourceGroupName };
    });
  const isAzureValid =
    pastedScopes.length > 0
      ? pastedScopes.every((entry) => guidPattern.test(entry.subscriptionId ?? "") && !!entry.resourceGroupName)
      : guidPattern.test(scope.subscriptionId) && scope.resourceGroupName.trim().length > 0;

  const nonAzureFields = componentType === "azure_resource_group" ? [] : fieldsByType[componentType];
  const isNonAzureValid =
    componentName.trim().length > 0 &&
    nonAzureFields.every((field) => !field.isRequired || (field.kind === "tokens" ? (tokenValues[field.key] ?? []).length > 0 : !!values[field.key]?.trim()));

  const buildConfiguration = (): Record<string, unknown> => {
    const configuration: Record<string, unknown> = {};
    for (const field of nonAzureFields) {
      if (field.kind === "tokens" && tokenValues[field.key]?.length) configuration[field.key] = tokenValues[field.key];
      else if (values[field.key]?.trim()) configuration[field.key] = (values[field.key] ?? "").trim();
    }
    const queryScope: Record<string, string> = {};
    if (configuration.query_host) queryScope.host = String(configuration.query_host);
    if (configuration.query_index) queryScope.index = String(configuration.query_index);
    if (Object.keys(queryScope).length) configuration.query_scope = queryScope;
    return configuration;
  };

  const submitAzure = async () => {
    setBulkError(null);
    const entries = pastedScopes.length
      ? pastedScopes
      : [{ subscriptionId: scope.subscriptionId, resourceGroupName: scope.resourceGroupName.trim() }];
    let firstCreated: ApplicationComponent | null = null;
    for (const entry of entries) {
      const body: CreateComponentBody = {
        componentType: "azure_resource_group",
        componentName: entry.resourceGroupName ?? "",
        environmentName,
        azureTenantId: scope.tenantId || identityQuery.data?.tenantId || undefined,
        azureSubscriptionId: entry.subscriptionId,
        azureSubscriptionName: scope.subscriptionName || undefined,
        azureResourceGroupName: entry.resourceGroupName,
      };
      try {
        const component = await addComponent.mutateAsync(body);
        firstCreated = firstCreated ?? component;
      } catch (error) {
        setBulkError(isApiError(error) ? `${entry.resourceGroupName}: ${error.detail}` : t("add.failed"));
        return;
      }
    }
    if (firstCreated) {
      setCreated(firstCreated);
      setPhase("access");
    }
  };

  const submitOther = () =>
    addComponent.mutate(
      { componentType, componentName: componentName.trim(), environmentName, componentConfiguration: buildConfiguration() },
      { onSuccess: () => handleOpenChange(false) },
    );

  const verifyAndClose = () => {
    if (created) verifyComponent.mutate(created.componentId);
    handleOpenChange(false);
  };

  return (
    <Drawer
      open={open}
      onOpenChange={handleOpenChange}
      size="md"
      title={phase === "type" ? t("add.chooseTypeTitle") : t(`add.titles.${componentType}`)}
      description={phase === "access" ? t("add.accessDescription") : phase === "type" ? t("add.chooseTypeDescription") : t(`add.descriptions.${componentType}`)}
      footer={
        phase === "type" ? undefined : phase === "access" ? (
          <>
            <Button variant="secondary" onClick={() => handleOpenChange(false)}>{t("add.verifyLater")}</Button>
            <Button onClick={verifyAndClose} isLoading={verifyComponent.isPending}>{t("add.verifyNow")}</Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={() => setPhase("type")}>{t("add.back")}</Button>
            <Button
              disabled={componentType === "azure_resource_group" ? !isAzureValid : !isNonAzureValid}
              isLoading={addComponent.isPending}
              onClick={() => (componentType === "azure_resource_group" ? void submitAzure() : submitOther())}
            >
              {componentType === "azure_resource_group" ? t("add.continueToAccess") : t("add.addComponent")}
            </Button>
          </>
        )
      }
    >
      {phase === "type" ? (
        <div className="grid gap-3">
          {(Object.keys(typeIcons) as ComponentType[]).map((type) => {
            const Icon = typeIcons[type];
            return (
              <Card
                key={type}
                interactive
                dense
                role="button"
                tabIndex={0}
                className="flex items-start gap-4"
                onClick={() => { setComponentType(type); setPhase("details"); }}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { setComponentType(type); setPhase("details"); } }}
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-action"><Icon size={20} aria-hidden="true" /></span>
                <span>
                  <span className="block font-semibold">{t(`types.${type}.title`)}</span>
                  <span className="text-body-sm text-muted">{t(`types.${type}.description`)}</span>
                </span>
              </Card>
            );
          })}
        </div>
      ) : phase === "access" && created ? (
        <RoleGrantPanel applicationId={applicationId} component={created} />
      ) : componentType === "azure_resource_group" ? (
        <div className="flex flex-col gap-4">
          <Input label={t("add.azure.tenantId")} helperText={t("add.azure.tenantHelp")} value={scope.tenantId || identityQuery.data?.tenantId || ""} onChange={(event) => setScope({ ...scope, tenantId: event.target.value })} errorMessage={fieldError("azureTenantId")} />
          <Input
            label={t("add.azure.subscriptionId")}
            value={scope.subscriptionId}
            disabled={pastedScopes.length > 0}
            onChange={(event) => setScope({ ...scope, subscriptionId: event.target.value })}
            errorMessage={fieldError("azureSubscriptionId") ?? (scope.subscriptionId && !guidPattern.test(scope.subscriptionId) ? t("add.azure.guidInvalid") : undefined)}
          />
          <Input label={t("add.azure.subscriptionName")} isOptional value={scope.subscriptionName} onChange={(event) => setScope({ ...scope, subscriptionName: event.target.value })} />
          <Input label={t("add.azure.resourceGroup")} value={scope.resourceGroupName} disabled={pastedScopes.length > 0} onChange={(event) => setScope({ ...scope, resourceGroupName: event.target.value })} errorMessage={fieldError("azureResourceGroupName")} />
          <Select label={t("add.environment")} value={environmentName} options={environments.map((environment) => ({ value: environment, label: t(`environments.${environment}`) }))} onValueChange={setEnvironmentName} />
          <Textarea
            label={t("add.azure.addSeveral")}
            helperText={t("add.azure.addSeveralHelp")}
            isOptional
            isMonospace
            rows={3}
            placeholder="00000000-0000-0000-0000-000000000000/RG_12345_APP_PRD01"
            value={scope.pastedLines}
            onChange={(event) => setScope({ ...scope, pastedLines: event.target.value })}
          />
          {bulkError ? <Banner tone="danger">{bulkError}</Banner> : null}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <Input label={t(`add.${componentType}.name`)} value={componentName} onChange={(event) => setComponentName(event.target.value)} errorMessage={fieldError("componentName")} />
          {nonAzureFields.map((field) => {
            const label = t(`fields.${field.key}`);
            const error = fieldError(`componentConfiguration.${field.key}`);
            if (field.kind === "select") {
              return (
                <Select key={field.key} label={label} value={values[field.key]} placeholder={t("add.choose")} errorMessage={error} options={(field.options ?? []).map((option) => ({ value: option, label: t(`options.${option}`) }))} onValueChange={(next) => setValues({ ...values, [field.key]: next })} />
              );
            }
            if (field.kind === "tokens") {
              return <TokenInput key={field.key} label={label} isOptional={!field.isRequired} placeholder={field.options ? field.options.join(", ") : undefined} value={tokenValues[field.key] ?? []} onValueChange={(next) => setTokenValues({ ...tokenValues, [field.key]: next })} errorMessage={error} />;
            }
            if (field.kind === "logTool") {
              const connections = logToolsQuery.data ?? [];
              return (
                <Select
                  key={field.key}
                  label={label}
                  isOptional
                  helperText={connections.length === 0 ? t("add.noLogTools") : undefined}
                  value={values[field.key]}
                  placeholder={t("add.choose")}
                  options={connections.map((connection) => ({ value: connection.logToolConnectionId, label: connection.connectionName }))}
                  onValueChange={(next) => setValues({ ...values, [field.key]: next })}
                />
              );
            }
            if (field.kind === "textarea") {
              return <Textarea key={field.key} label={label} isOptional rows={2} value={values[field.key] ?? ""} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} />;
            }
            return <Input key={field.key} label={label} isOptional={!field.isRequired} value={values[field.key] ?? ""} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} errorMessage={error} />;
          })}
          <Select label={t("add.environment")} value={environmentName} options={environments.map((environment) => ({ value: environment, label: t(`environments.${environment}`) }))} onValueChange={setEnvironmentName} />
          {addComponent.isError && !fieldError("componentName") ? <Banner tone="danger">{isApiError(addComponent.error) ? addComponent.error.detail : t("add.failed")}</Banner> : null}
        </div>
      )}
    </Drawer>
  );
}
