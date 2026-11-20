import { useState } from "react";
import { Database, Plug, Play, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useDeleteLogToolConnection,
  useLogToolConnections,
  useSaveLogToolConnection,
  useTestLogToolConnection,
  type LogToolConnection,
  type LogToolType,
} from "@/api/applicationsApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/utils/cn";
import { formatDate } from "@/utils/formatters";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

type FieldKind = "endpoint" | "config" | "select" | "textarea";
interface ToolField {
  key: string;
  kind: FieldKind;
  options?: string[];
  defaultValue?: string;
}

/** Fields per tool (spec 6.5). `endpoint` maps to `endpointUrl`, `authenticationMethod` to the column, the rest to `connectionConfiguration`. */
const toolFields: Record<LogToolType, ToolField[]> = {
  elastic: [
    { key: "endpoint", kind: "endpoint" },
    { key: "authenticationMethod", kind: "select", options: ["api_key", "basic"], defaultValue: "api_key" },
    { key: "index_pattern", kind: "config" },
    { key: "service_field", kind: "config", defaultValue: "service.name" },
    { key: "namespace_field", kind: "config" },
    { key: "time_field", kind: "config", defaultValue: "@timestamp" },
  ],
  splunk: [
    { key: "endpoint", kind: "endpoint" },
    { key: "indexes", kind: "config" },
    { key: "source_types", kind: "config" },
    { key: "host_field", kind: "config", defaultValue: "host" },
  ],
  datadog: [
    { key: "endpoint", kind: "endpoint" },
    { key: "site", kind: "config", defaultValue: "datadoghq.com" },
    { key: "application_key_reference", kind: "config" },
    { key: "default_service_tag", kind: "config" },
    { key: "env_tag", kind: "config", defaultValue: "env" },
  ],
  solarwinds: [
    { key: "platform", kind: "select", options: ["orion_swis", "observability_saas"], defaultValue: "orion_swis" },
    { key: "endpoint", kind: "endpoint" },
    { key: "node_ids", kind: "config" },
  ],
  ibm_z_log_analytics: [
    { key: "product", kind: "config" },
    { key: "endpoint", kind: "endpoint" },
    { key: "index", kind: "config" },
    { key: "smf_record_types", kind: "config" },
  ],
  vendor_api: [
    { key: "vendor", kind: "config" },
    { key: "endpoint", kind: "endpoint" },
    { key: "authenticationMethod", kind: "select", options: ["api_key", "oauth_client_credentials", "basic"], defaultValue: "api_key" },
    { key: "extra_settings", kind: "textarea" },
  ],
  other: [{ key: "holds", kind: "textarea" }],
};
const toolTypes = Object.keys(toolFields) as LogToolType[];
/** Tools Keigan can already read; the others save their details and wait for a reader. */
const readerToolTypes: LogToolType[] = ["elastic", "splunk", "datadog"];
const statusTones = { not_tested: "neutral", connected: "success", failed: "danger", reader_not_available: "ai" } as const;

function ConnectionDrawer({ applicationId, toolType, connection, onClose }: { applicationId: string; toolType: LogToolType | null; connection: LogToolConnection | null; onClose: () => void }) {
  const { t } = useTranslation("onboarding");
  const save = useSaveLogToolConnection(applicationId);
  const fields = toolType ? toolFields[toolType] : [];
  const [name, setName] = useState(connection?.connectionName ?? "");
  const [endpointUrl, setEndpointUrl] = useState(connection?.endpointUrl ?? "");
  const [authenticationMethod, setAuthenticationMethod] = useState(connection?.authenticationMethod ?? fields.find((field) => field.key === "authenticationMethod")?.defaultValue ?? "api_key");
  const [configuration, setConfiguration] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of fields) if (field.kind !== "endpoint" && field.key !== "authenticationMethod") initial[field.key] = String(connection?.connectionConfiguration?.[field.key] ?? field.defaultValue ?? "");
    return initial;
  });
  const [credentialValue, setCredentialValue] = useState("");
  const isPlaceholder = toolType ? !readerToolTypes.includes(toolType) : false;

  const submit = () => {
    if (!toolType) return;
    save.mutate(
      {
        connectionId: connection?.logToolConnectionId,
        body: {
          ...(connection ? {} : { toolType }),
          connectionName: name.trim(),
          endpointUrl: endpointUrl.trim() || null,
          authenticationMethod,
          connectionConfiguration: Object.fromEntries(Object.entries(configuration).filter(([, value]) => value.trim())),
          credentialValue: credentialValue || undefined,
        },
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Drawer
      open={toolType !== null}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title={toolType ? t(`logTools.tools.${toolType}.title`) : ""}
      description={toolType ? t(`logTools.tools.${toolType}.description`) : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t("add.cancel")}</Button>
          <Button disabled={!name.trim()} isLoading={save.isPending} onClick={submit}>{connection ? t("logTools.saveChanges") : t("logTools.saveConnection")}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {isPlaceholder ? <Banner tone="ai">{t("logTools.placeholderBanner")}</Banner> : null}
        <Input label={t("logTools.connectionName")} value={name} onChange={(event) => setName(event.target.value)} errorMessage={isApiError(save.error) ? save.error.fieldErrorFor("connectionName") : undefined} />
        {fields.map((field) => {
          const label = t(`logTools.fields.${field.key}`);
          if (field.kind === "endpoint") return <Input key={field.key} label={label} value={endpointUrl} onChange={(event) => setEndpointUrl(event.target.value)} />;
          if (field.kind === "select") {
            const isAuthentication = field.key === "authenticationMethod";
            return (
              <Select
                key={field.key}
                label={label}
                value={isAuthentication ? authenticationMethod : configuration[field.key]}
                options={(field.options ?? []).map((option) => ({ value: option, label: t(`logTools.options.${option}`) }))}
                onValueChange={(next) => (isAuthentication ? setAuthenticationMethod(next) : setConfiguration({ ...configuration, [field.key]: next }))}
              />
            );
          }
          if (field.kind === "textarea") return <Textarea key={field.key} label={label} isOptional rows={3} value={configuration[field.key] ?? ""} onChange={(event) => setConfiguration({ ...configuration, [field.key]: event.target.value })} />;
          return <Input key={field.key} label={label} isOptional value={configuration[field.key] ?? ""} onChange={(event) => setConfiguration({ ...configuration, [field.key]: event.target.value })} />;
        })}
        {toolType !== "other" ? (
          <Input
            type="password"
            autoComplete="new-password"
            label={t("logTools.credential")}
            isOptional
            helperText={connection?.hasCredential ? t("logTools.credentialSet", { date: formatDate(connection.credentialSetAt) }) : t("logTools.credentialHelp")}
            placeholder={connection?.hasCredential ? "••••••••" : undefined}
            value={credentialValue}
            onChange={(event) => setCredentialValue(event.target.value)}
          />
        ) : null}
        {save.isError ? <Banner tone="danger">{isApiError(save.error) ? save.error.detail : t("add.failed")}</Banner> : null}
      </div>
    </Drawer>
  );
}

export function LogToolsStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("onboarding");
  const connectionsQuery = useLogToolConnections(applicationId);
  const testConnection = useTestLogToolConnection(applicationId);
  const deleteConnection = useDeleteLogToolConnection(applicationId);
  const [editor, setEditor] = useState<{ toolType: LogToolType; connection: LogToolConnection | null } | null>(null);
  const [connectionToDelete, setConnectionToDelete] = useState<LogToolConnection | null>(null);

  return (
    <StepFrame stepKey="log_tools">
      {canEdit ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {toolTypes.map((toolType) => {
            const isReaderAvailable = readerToolTypes.includes(toolType);
            return (
              <button
                key={toolType}
                type="button"
                onClick={() => setEditor({ toolType, connection: null })}
                className={cn(
                  "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition-shadow hover:shadow-md focus-visible:ring-2 focus-visible:ring-action",
                  isReaderAvailable ? "border-hairline bg-surface" : "border-dashed border-hairline bg-sunken",
                )}
              >
                <span className={cn("flex size-9 items-center justify-center rounded-lg", isReaderAvailable ? "bg-brand-soft text-action" : "bg-neutral-soft text-muted")}><Database size={18} aria-hidden="true" /></span>
                <span className="text-body-sm font-semibold">{t(`logTools.tools.${toolType}.title`)}</span>
                {isReaderAvailable ? null : (
                  <>
                    <StatusChip size="sm" tone="neutral" icon={false}>{t("logTools.comingSoon")}</StatusChip>
                    <span className="text-caption text-muted">{t("logTools.comingSoonNote")}</span>
                  </>
                )}
              </button>
            );
          })}
        </div>
      ) : null}

      {connectionsQuery.isError ? (
        <ErrorState error={connectionsQuery.error} onRetry={() => void connectionsQuery.refetch()} />
      ) : connectionsQuery.isLoading ? (
        <Skeleton className="h-28 rounded-lg" />
      ) : (
        <div className="flex flex-col gap-3">
          {connectionsQuery.data?.length === 0 ? <p className="text-body-sm text-muted">{t("logTools.none")}</p> : null}
          {connectionsQuery.data?.map((connection) => (
            <Card key={connection.logToolConnectionId} dense className="flex flex-col gap-3 p-[var(--card-padding)]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-body font-semibold">{connection.connectionName}</h3>
                    <StatusChip size="sm" tone={statusTones[connection.connectionStatus]} dot>{t(`logTools.status.${connection.connectionStatus}`)}</StatusChip>
                  </div>
                  <p className="text-caption text-muted">
                    {t(`logTools.tools.${connection.toolType}.title`)}
                    {connection.hasCredential ? ` · ${t("logTools.credentialSet", { date: formatDate(connection.credentialSetAt) })}` : ""}
                  </p>
                </div>
                {canEdit ? (
                  <div className="flex gap-1">
                    {connection.readerAvailable ? (
                      <Button size="sm" variant="secondary" leadingIcon={Play} isLoading={testConnection.isPending && testConnection.variables === connection.logToolConnectionId} onClick={() => testConnection.mutate(connection.logToolConnectionId)}>{t("logTools.test")}</Button>
                    ) : (
                      <Tooltip content={t("logTools.testDisabled")}>
                        <span><Button size="sm" variant="secondary" leadingIcon={Play} disabled>{t("logTools.test")}</Button></span>
                      </Tooltip>
                    )}
                    <Button size="sm" variant="secondary" leadingIcon={Plug} onClick={() => setEditor({ toolType: connection.toolType, connection })}>{t("logTools.edit")}</Button>
                    <Button size="sm" variant="ghost" leadingIcon={Trash2} aria-label={t("logTools.delete")} onClick={() => setConnectionToDelete(connection)} />
                  </div>
                ) : null}
              </div>
              {connection.lastTestMessage ? (
                <p className="text-body-sm text-muted">
                  {connection.lastTestMessage}
                  {connection.newestLogTimestampSeenAt ? <> · {t("logTools.newestLog")} <RelativeTime value={connection.newestLogTimestampSeenAt} /></> : null}
                </p>
              ) : null}
              <p className="text-caption text-muted">{connection.usedByServiceNames.length ? t("logTools.usedBy", { names: connection.usedByServiceNames.join(", ") }) : t("logTools.notUsed")}</p>
            </Card>
          ))}
        </div>
      )}
      {editor ? <ConnectionDrawer key={editor.connection?.logToolConnectionId ?? editor.toolType} applicationId={applicationId} toolType={editor.toolType} connection={editor.connection} onClose={() => { setEditor(null); onStatusChange?.(); }} /> : null}
      <ConfirmDialog
        open={connectionToDelete !== null}
        onOpenChange={(open) => { if (!open) setConnectionToDelete(null); }}
        tone="danger"
        title={t("logTools.deleteTitle", { name: connectionToDelete?.connectionName })}
        description={t("logTools.deleteDescription")}
        confirmLabel={t("logTools.deleteConfirm")}
        onConfirm={async () => { if (connectionToDelete) await deleteConnection.mutateAsync(connectionToDelete.logToolConnectionId); onStatusChange?.(); }}
      />
      {deleteConnection.isError ? <Banner tone="danger">{isApiError(deleteConnection.error) ? deleteConnection.error.detail : t("add.failed")}</Banner> : null}
    </StepFrame>
  );
}
