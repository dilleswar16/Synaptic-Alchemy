import { useState } from "react";
import { FlaskConical, PlugZap, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAdministrationSettings, useConnectionTest, useSimulationScenarios, useTriggerScenario, type ConnectionTestOutcome, type IntegrationStatus } from "@/api/administrationApi";
import { isApiError } from "@/api/httpClient";
import { useApplicationScope } from "@/auth/applicationScope";
import { PageHeader } from "@/components/layout/PageHeader";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { useToast } from "@/components/ui/Toast";
import { useFeatureFlag } from "@/config/runtimeConfiguration";

/** Integrations that have a connection test, keyed by the integration card they belong to. */
const testableIntegrations: Record<string, string> = { servicenow: "servicenow", llm: "llm", azure: "azure", email: "email", teams: "graph" };

function displaySettingValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function IntegrationCard({ integration }: { integration: IntegrationStatus }) {
  const { t } = useTranslation("administration");
  const connectionTest = useConnectionTest();
  const [outcome, setOutcome] = useState<ConnectionTestOutcome | null>(null);
  const testKey = testableIntegrations[integration.integrationKey];
  const runTest = () => { if (testKey) connectionTest.mutate(testKey, { onSuccess: setOutcome }); };
  return (
    <Card dense className="flex flex-col gap-3 p-[var(--card-padding)]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-body font-semibold text-default">{t(`settings.integrations.${integration.integrationKey}`, { defaultValue: integration.integrationKey })}</h3>
          <p className="truncate text-caption text-muted">{integration.summary}</p>
        </div>
        <StatusChip tone={integration.isSimulated ? "info" : integration.isConfigured ? "success" : "warning"} size="sm">{integration.isSimulated ? t("settings.simulated") : integration.isConfigured ? t("settings.configured") : t("settings.notConfigured")}</StatusChip>
      </div>
      <p className="font-mono text-caption text-muted">{integration.mode}</p>
      {testKey ? <Button variant="secondary" size="sm" leadingIcon={PlugZap} isLoading={connectionTest.isPending} onClick={runTest}>{t("settings.testConnection")}</Button> : null}
      {connectionTest.isError ? <Banner tone="danger">{isApiError(connectionTest.error) ? (connectionTest.error.detail ?? connectionTest.error.title) : t("settings.testFailed")}</Banner> : null}
      {outcome ? <Banner tone={outcome.succeeded ? "success" : "danger"}>{outcome.message}</Banner> : null}
    </Card>
  );
}

function SimulationControlsCard() {
  const { t } = useTranslation("administration");
  const { availableApplications } = useApplicationScope();
  const scenarios = useSimulationScenarios(true);
  const trigger = useTriggerScenario();
  const { showToast } = useToast();
  const [applicationId, setApplicationId] = useState<string>("");
  const [scenarioKey, setScenarioKey] = useState<string>("");
  const start = () =>
    trigger.mutate({ scenarioKey, applicationId }, {
      onSuccess: (result) => showToast({ tone: "success", title: t("simulation.started"), description: t("simulation.startedDescription", { number: result.servicenowIncidentNumber ?? "—" }) }),
      onError: (error) => showToast({ tone: "danger", title: t("simulation.failed"), description: isApiError(error) ? (error.detail ?? error.title) : undefined }),
    });
  return (
    <Card>
      <CardHeader icon={FlaskConical} iconTone="ai" title={t("simulation.title")} description={t("simulation.description")} />
      <CardBody className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Select label={t("simulation.application")} value={applicationId} onValueChange={setApplicationId} placeholder={t("simulation.pickApplication")} options={availableApplications.map((application) => ({ value: application.applicationId, label: `${application.applicationName} (${application.applicationCode})` }))} />
          <Select label={t("simulation.scenario")} value={scenarioKey} onValueChange={setScenarioKey} placeholder={t("simulation.pickScenario")} options={(scenarios.data ?? []).map((scenario) => ({ value: scenario.scenarioKey, label: scenario.title, description: scenario.category }))} />
        </div>
        <div><Button leadingIcon={Play} onClick={start} isLoading={trigger.isPending} disabled={!applicationId || !scenarioKey}>{t("simulation.start")}</Button></div>
      </CardBody>
    </Card>
  );
}

export default function PlatformSettingsPage() {
  const { t } = useTranslation("administration");
  const settings = useAdministrationSettings();
  const isSimulationEnabled = useFeatureFlag("simulationControls");
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  const data = settings.data;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("settings.pageTitle")} description={t("settings.pageDescription")} />
      {!data ? <Skeleton className="h-64" /> : (
        <>
          <section aria-labelledby="integrations-heading">
            <h2 id="integrations-heading" className="mb-3 text-h3 font-semibold text-default">{t("settings.integrationsTitle")}</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{data.integrations.map((integration) => <IntegrationCard key={integration.integrationKey} integration={integration} />)}</div>
          </section>
          {isSimulationEnabled && data.simulationControlsAvailable ? <SimulationControlsCard /> : null}
          <Card>
            <CardHeader title={t("settings.identityTitle")} description={t("settings.identityDescription")} />
            <CardBody>
              <KeyValueList items={[
                { key: "name", label: t("settings.identity.name"), value: data.keiganIdentity.managedIdentityDisplayName },
                { key: "object", label: t("settings.identity.objectId"), value: data.keiganIdentity.managedIdentityObjectId, copyValue: data.keiganIdentity.managedIdentityObjectId, isMonospace: true },
                { key: "client", label: t("settings.identity.clientId"), value: data.keiganIdentity.managedIdentityClientId, copyValue: data.keiganIdentity.managedIdentityClientId, isMonospace: true },
                ...(data.keiganIdentity.multiTenantAppClientId ? [{ key: "multi", label: t("settings.identity.multiTenant"), value: data.keiganIdentity.multiTenantAppClientId, copyValue: data.keiganIdentity.multiTenantAppClientId, isMonospace: true }] : []),
              ]} />
            </CardBody>
          </Card>
          {data.groups.map((group) => (
            <Card key={group.groupKey}>
              <CardHeader title={t(`settings.groups.${group.groupKey}`, { defaultValue: group.groupTitle })} />
              <CardBody>
                <KeyValueList dense items={Object.entries(group.settings).map(([name, value]) => ({ key: name, label: <span className="font-mono text-caption">{name.toUpperCase()}</span>, value: displaySettingValue(value) }))} />
              </CardBody>
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
