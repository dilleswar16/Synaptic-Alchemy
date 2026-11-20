import { useState } from "react";
import { ChevronRight, Eye, EyeOff, FlaskConical, PlugZap, Play, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAdministrationSettings, useConnectionTest, useSimulationScenarios, useTriggerScenario, type ConnectionTestOutcome, type IntegrationStatus, type SettingsGroup } from "@/api/administrationApi";
import { isApiError } from "@/api/httpClient";
import { useApplicationScope } from "@/auth/applicationScope";
import { PageHeader } from "@/components/layout/PageHeader";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { useToast } from "@/components/ui/Toast";
import { useFeatureFlag } from "@/config/runtimeConfiguration";
import { cn } from "@/utils/cn";

/** Integrations that have a connection test, keyed by the integration card they belong to. */
const testableIntegrations: Record<string, string> = { servicenow: "servicenow", llm: "llm", azure: "azure", email: "email", teams: "graph" };

function displaySettingValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** The backend already replaces values of fields named like a secret with "•••• set" / "not set"; these are shown as they are. */
const backendMaskedValues = new Set(["•••• set", "not set"]);
const secretNamePattern = /secret|password|passphrase|token|credential|private_key|api_key|headers|dsn|sas_|_key$/;
/** A value that still carries a password or key (the server redacts known ones; this catches anything it missed) is hidden for good, with no way to reveal it. */
const credentialInValuePattern = /^[a-z][a-z0-9+.-]*:\/\/[^\s/@]*:[^\s/@]+@|(?:^|;)\s*(?:pwd|password|accountkey|sharedaccesskey)\s*=\s*(?!••••)/i;
const pathNamePattern = /_(?:directory|dir|path)$/;
const pathValuePattern = /^(?:[A-Za-z]:[\\/]|\\\\|\/(?:[^\s/]+\/)+|~\/|file:)/;

/**
 * Secret-like values are hidden for good; file paths are hidden until someone asks to see them (connection strings arrive from the server with the password already removed).
 * Only text is considered: numbers and flags are never sensitive.
 */
function sensitivityOf(name: string, value: unknown): "secret" | "sensitive" | null {
  if (typeof value !== "string" || value.trim() === "" || ["{}", "[]"].includes(value.trim()) || backendMaskedValues.has(value)) return null;
  if (secretNamePattern.test(name) || credentialInValuePattern.test(value)) return "secret";
  if (pathNamePattern.test(name) || pathValuePattern.test(value)) return "sensitive";
  return null;
}

function SettingValue({ name, value }: { name: string; value: unknown }) {
  const { t } = useTranslation("administration");
  const [isRevealed, setIsRevealed] = useState(false);
  const sensitivity = sensitivityOf(name, value);
  if (!sensitivity) return <>{displaySettingValue(value)}</>;
  if (isRevealed) {
    return (
      <span className="flex items-start gap-1">
        <span className="min-w-0 flex-1 break-all">{displaySettingValue(value)}</span>
        <IconButton icon={EyeOff} label={t("settings.hideValue")} variant="ghost" size="sm" className="-my-1" onClick={() => setIsRevealed(false)} />
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-muted">
      <span aria-hidden="true">••••••••</span>
      <span className="sr-only">{t("settings.hiddenValue")}</span>
      {sensitivity === "sensitive" ? <IconButton icon={Eye} label={t("settings.showValue")} variant="ghost" size="sm" className="-my-1" onClick={() => setIsRevealed(true)} /> : null}
    </span>
  );
}

/** One group of raw settings: collapsed unless it is the first group or a search is narrowing the list. */
function SettingsGroupCard({ group, entries, isOpenByDefault, isFiltering }: { group: SettingsGroup; entries: Array<[string, unknown]>; isOpenByDefault: boolean; isFiltering: boolean }) {
  const { t } = useTranslation("administration");
  const [isOpenState, setIsOpenState] = useState(isOpenByDefault);
  const isOpen = isFiltering || isOpenState;
  const bodyId = `settings-group-${group.groupKey}`;
  return (
    <Card>
      <h3>
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={isOpen ? bodyId : undefined}
          aria-disabled={isFiltering || undefined}
          onClick={() => !isFiltering && setIsOpenState(!isOpenState)}
          className="flex w-full items-center gap-3 rounded-md px-[var(--card-padding)] py-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-action"
        >
          <ChevronRight aria-hidden="true" size={18} className={cn("shrink-0 text-muted transition-transform", isOpen && "rotate-90")} />
          <span className="min-w-0 flex-1 font-display text-h3 text-default">{t(`settings.groups.${group.groupKey}`, { defaultValue: group.groupTitle })}</span>
          <StatusChip size="sm" tone="neutral" icon={false}>{entries.length}</StatusChip>
        </button>
      </h3>
      {isOpen ? (
        <CardBody id={bodyId} className="pt-0">
          <KeyValueList dense items={entries.map(([name, value]) => ({ key: name, label: <span className="font-mono text-caption">{name.toUpperCase()}</span>, value: <SettingValue name={name} value={value} /> }))} />
        </CardBody>
      ) : null}
    </Card>
  );
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
  const [query, setQuery] = useState("");
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  const data = settings.data;
  const needle = query.trim().toLowerCase();
  const visibleGroups = (data?.groups ?? [])
    .map((group) => ({ group, entries: Object.entries(group.settings).filter(([name]) => !needle || name.toLowerCase().includes(needle)) }))
    .filter(({ entries }) => entries.length > 0);
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
          <Input aria-label={t("settings.searchLabel")} placeholder={t("settings.searchPlaceholder")} leadingIcon={Search} size="sm" value={query} onChange={(event) => setQuery(event.target.value)} containerClassName="w-72 max-w-full" />
          {visibleGroups.map(({ group, entries }) => (
            <SettingsGroupCard key={group.groupKey} group={group} entries={entries} isOpenByDefault={group.groupKey === data.groups[0]?.groupKey} isFiltering={needle !== ""} />
          ))}
          {needle && visibleGroups.length === 0 ? <p className="text-body-sm text-muted">{t("settings.noMatches", { query: query.trim() })}</p> : null}
        </>
      )}
    </div>
  );
}
