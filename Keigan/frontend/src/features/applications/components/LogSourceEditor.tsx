import { useState } from "react";
import { CheckCircle2, CircleDashed, Play, Plus, Star, Trash2, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useLogToolConnections,
  useReplaceLogSources,
  useTestLogSource,
  type LogSource,
  type LogSourceInput,
  type LogSourceKind,
  type MonitoredServiceRow,
} from "@/api/applicationsApi";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import { useToast } from "@/components/ui/Toast";

const sourceKinds: LogSourceKind[] = ["log_analytics", "application_insights", "azure_monitor_metrics", "log_tool", "synthetic_probe"];

function toInput(source: LogSource): LogSourceInput {
  return {
    sourceKind: source.sourceKind,
    logToolConnectionId: source.logToolConnectionId,
    logAnalyticsWorkspaceResourceId: source.logAnalyticsWorkspaceResourceId,
    logAnalyticsWorkspaceCustomerId: source.logAnalyticsWorkspaceCustomerId,
    queryScope: source.queryScope,
    isPrimarySource: source.isPrimarySource,
  };
}

/** Form for one new log source. Reused by the service drawer and by the bulk "Add log source" action. */
export function LogSourceForm({ applicationId, onSubmit, isSubmitting }: { applicationId: string; onSubmit: (source: LogSourceInput) => void; isSubmitting?: boolean }) {
  const { t } = useTranslation("onboarding");
  const connectionsQuery = useLogToolConnections(applicationId);
  const [sourceKind, setSourceKind] = useState<LogSourceKind>("log_analytics");
  const [workspaceResourceId, setWorkspaceResourceId] = useState("");
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [scope, setScope] = useState({ index: "", namespace: "", host: "", labels: "", probeUrl: "" });

  const buildSource = (): LogSourceInput => {
    const queryScope = Object.fromEntries(
      [["index", scope.index], ["namespace", scope.namespace], ["host", scope.host], ["labels", scope.labels], ["probe_url", scope.probeUrl]].filter(([, value]) => (value ?? "").trim()),
    );
    return {
      sourceKind,
      logToolConnectionId: sourceKind === "log_tool" ? connectionId : null,
      logAnalyticsWorkspaceResourceId: sourceKind === "log_analytics" || sourceKind === "application_insights" ? workspaceResourceId.trim() || null : null,
      queryScope: Object.keys(queryScope).length ? queryScope : null,
      isPrimarySource: false,
    };
  };
  const isValid =
    (sourceKind === "log_analytics" && workspaceResourceId.trim().length > 0) ||
    (sourceKind === "log_tool" && connectionId !== null) ||
    (sourceKind === "synthetic_probe" && scope.probeUrl.trim().length > 0) ||
    sourceKind === "application_insights" ||
    sourceKind === "azure_monitor_metrics";

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-hairline bg-sunken p-4">
      <Select label={t("logSource.kind")} value={sourceKind} options={sourceKinds.map((kind) => ({ value: kind, label: t(`logSource.kinds.${kind}`) }))} onValueChange={setSourceKind} />
      {sourceKind === "log_analytics" || sourceKind === "application_insights" ? (
        <Input label={t("logSource.workspaceResourceId")} isOptional={sourceKind === "application_insights"} value={workspaceResourceId} onChange={(event) => setWorkspaceResourceId(event.target.value)} />
      ) : null}
      {sourceKind === "log_tool" ? (
        <>
          <Select
            label={t("logSource.connection")}
            value={connectionId ?? undefined}
            placeholder={t("logSource.chooseConnection")}
            helperText={(connectionsQuery.data ?? []).length === 0 ? t("logSource.noConnections") : undefined}
            options={(connectionsQuery.data ?? []).map((connection) => ({ value: connection.logToolConnectionId, label: connection.connectionName }))}
            onValueChange={setConnectionId}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <Input label={t("logSource.scope.index")} isOptional value={scope.index} onChange={(event) => setScope({ ...scope, index: event.target.value })} />
            <Input label={t("logSource.scope.namespace")} isOptional value={scope.namespace} onChange={(event) => setScope({ ...scope, namespace: event.target.value })} />
            <Input label={t("logSource.scope.host")} isOptional value={scope.host} onChange={(event) => setScope({ ...scope, host: event.target.value })} />
            <Input label={t("logSource.scope.labels")} isOptional value={scope.labels} onChange={(event) => setScope({ ...scope, labels: event.target.value })} />
          </div>
        </>
      ) : null}
      {sourceKind === "synthetic_probe" ? <Input label={t("logSource.scope.probeUrl")} value={scope.probeUrl} onChange={(event) => setScope({ ...scope, probeUrl: event.target.value })} /> : null}
      <Button className="self-start" size="sm" leadingIcon={Plus} disabled={!isValid} isLoading={isSubmitting} onClick={() => onSubmit(buildSource())}>{t("logSource.add")}</Button>
    </div>
  );
}

/** Log sources of one service: chips with read-test status, primary marker, add and remove (spec 6.4). */
export function LogSourceEditor({ applicationId, service, canEdit }: { applicationId: string; service: MonitoredServiceRow; canEdit: boolean }) {
  const { t } = useTranslation("onboarding");
  const { showToast } = useToast();
  const replaceLogSources = useReplaceLogSources(applicationId);
  const testLogSource = useTestLogSource(applicationId);
  const [isAdding, setIsAdding] = useState(false);
  const sources = service.logSources;

  const save = (next: LogSourceInput[]) => replaceLogSources.mutate({ serviceId: service.serviceId, sources: next }, { onSuccess: () => setIsAdding(false) });
  const runTest = (source: LogSource) =>
    testLogSource.mutate(
      { serviceId: service.serviceId, logSourceId: source.serviceLogSourceId },
      { onSuccess: (result) => showToast({ tone: result.succeeded ? "success" : "danger", title: result.succeeded ? t("logSource.testPassed") : t("logSource.testFailed"), description: result.message }) },
    );

  return (
    <div className="flex flex-col gap-3">
      {sources.length === 0 ? <p className="text-body-sm text-muted">{t("logSource.none")}</p> : null}
      <ul className="flex flex-col gap-2">
        {sources.map((source) => {
          const StatusIcon = source.lastReadTestStatus === "passed" ? CheckCircle2 : source.lastReadTestStatus === "failed" ? XCircle : CircleDashed;
          return (
            <li key={source.serviceLogSourceId} className="flex items-center gap-3 rounded-lg border border-hairline px-3 py-2">
              <StatusIcon size={18} aria-hidden="true" className={source.lastReadTestStatus === "passed" ? "text-success" : source.lastReadTestStatus === "failed" ? "text-danger" : "text-muted"} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-body-sm font-medium">
                  {t(`logSource.kinds.${source.sourceKind}`)}
                  {source.isPrimarySource ? <StatusChip size="sm" icon={Star} tone="brand">{t("logSource.primary")}</StatusChip> : null}
                  {source.wasAutoDetected ? <StatusChip size="sm" icon={false} tone="neutral">{t("logSource.autoDetected")}</StatusChip> : null}
                </div>
                <div className="truncate text-caption text-muted">
                  {source.logToolConnectionName ?? source.logAnalyticsWorkspaceResourceId?.split("/").pop() ?? t(`logSource.testStatus.${source.lastReadTestStatus}`)}
                </div>
              </div>
              {canEdit ? (
                <>
                  <Button size="sm" variant="ghost" leadingIcon={Play} isLoading={testLogSource.isPending && testLogSource.variables?.logSourceId === source.serviceLogSourceId} onClick={() => runTest(source)}>{t("logSource.test")}</Button>
                  <Button size="sm" variant="ghost" leadingIcon={Trash2} aria-label={t("logSource.remove")} onClick={() => save(sources.filter((candidate) => candidate.serviceLogSourceId !== source.serviceLogSourceId).map(toInput))} />
                </>
              ) : null}
            </li>
          );
        })}
      </ul>
      {canEdit ? (
        isAdding ? (
          <LogSourceForm applicationId={applicationId} isSubmitting={replaceLogSources.isPending} onSubmit={(newSource) => save([...sources.map(toInput), { ...newSource, isPrimarySource: sources.length === 0 }])} />
        ) : (
          <Button className="self-start" size="sm" variant="secondary" leadingIcon={Plus} onClick={() => setIsAdding(true)}>{t("logSource.addSource")}</Button>
        )
      ) : null}
    </div>
  );
}
