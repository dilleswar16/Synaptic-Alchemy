import { useState } from "react";
import { KeyRound, Pause, Play, Plus, Send, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useAlertSources, useAzureAlertRules, useDeleteAlertSource, useRotateAlertSourceSecret, useSendTestAlert, useUpdateAlertSource, type AlertSource, type SecretRotation,
} from "@/api/alertsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CountWithInfo } from "@/components/ui/CountWithInfo";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { useToast } from "@/components/ui/Toast";
import type { StatusTone } from "@/components/ui/toneStyles";
import { AddAlertSourceSheet } from "./AddAlertSourceSheet";

const statusTones: Record<AlertSource["sourceStatus"], StatusTone> = { waiting_for_first_alert: "neutral", receiving: "success", authentication_failures: "danger", paused: "warning" };

/** Step 7b: alert sources list, discovered Azure alert rules and the Add alert source sheet. */
export function AlertSourcesSection({ applicationId, canEdit, onChanged }: { applicationId: string; canEdit: boolean; onChanged?: () => void }) {
  const { t } = useTranslation("alerts");
  const { showToast } = useToast();
  const sourcesQuery = useAlertSources(applicationId);
  const rulesQuery = useAzureAlertRules(applicationId);
  const updateSource = useUpdateAlertSource(applicationId);
  const deleteSource = useDeleteAlertSource(applicationId);
  const rotateSecret = useRotateAlertSourceSecret(applicationId);
  const sendTest = useSendTestAlert(applicationId);
  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const [sourceToRemove, setSourceToRemove] = useState<AlertSource | null>(null);
  const [rotation, setRotation] = useState<SecretRotation | null>(null);
  const rules = rulesQuery.data;

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader level={3} title={t("sources.title")} description={t("sources.description")}
        actions={canEdit ? <Button leadingIcon={Plus} size="sm" onClick={() => setIsSheetOpen(true)}>{t("sources.add")}</Button> : undefined} />
      {rules && rules.totalRuleCount > 0 ? (
        <CountWithInfo count={rules.totalRuleCount} label={t("sources.rulesFound", { sending: rules.sendingToKeiganCount })} title={t("sources.rulesTitle")}
          items={rules.rules.map((rule) => ({ key: rule.ruleName, label: rule.ruleName, secondary: rule.sendsToKeigan ? t("sources.sendsToKeigan") : t("sources.doesNotSend") }))} maximumItems={8} />
      ) : null}
      {rules?.isSimulated ? <p className="text-caption text-muted">{t("sources.simulatedRules")}</p> : null}
      {sourcesQuery.isLoading ? <Skeleton className="h-24 w-full" /> : null}
      {sourcesQuery.isError ? <ErrorState size="sm" error={sourcesQuery.error} onRetry={() => sourcesQuery.refetch()} /> : null}
      {sourcesQuery.data?.length === 0 ? <EmptyState isBordered size="sm" title={t("sources.emptyTitle")} description={t("sources.emptyDescription")} /> : null}
      <div className="grid gap-3">
        {sourcesQuery.data?.map((source) => (
          <Card key={source.alertSourceId} dense>
            <CardBody className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="font-semibold">{source.sourceName}</span>
                  <StatusChip tone="neutral" variant="outline" size="sm" icon={false}>{t(`tools.${source.sourceTool}`)}</StatusChip>
                  <StatusChip tone={statusTones[source.sourceStatus]} size="sm" dot>
                    {source.sourceStatus === "receiving" ? <>{t("sources.status.receiving")} <RelativeTime value={source.lastReceivedAt} /></> : t(`sources.status.${source.sourceStatus}`)}
                  </StatusChip>
                </div>
                {canEdit ? (
                  <div className="flex flex-wrap gap-1">
                    <Button variant="ghost" size="sm" leadingIcon={Send} isLoading={sendTest.isPending} onClick={() => sendTest.mutate(source.alertSourceId, { onSuccess: () => showToast({ tone: "success", title: t("sources.testSent") }) })}>{t("sources.test")}</Button>
                    <Button variant="ghost" size="sm" leadingIcon={KeyRound} onClick={() => rotateSecret.mutate(source.alertSourceId, { onSuccess: setRotation })}>{t("sources.rotate")}</Button>
                    <Button variant="ghost" size="sm" leadingIcon={source.sourceStatus === "paused" ? Play : Pause} onClick={() => updateSource.mutate({ alertSourceId: source.alertSourceId, body: { isPaused: source.sourceStatus !== "paused" } })}>
                      {source.sourceStatus === "paused" ? t("sources.resume") : t("sources.pause")}
                    </Button>
                    <Button variant="ghost" size="sm" leadingIcon={Trash2} onClick={() => setSourceToRemove(source)}>{t("sources.remove")}</Button>
                  </div>
                ) : null}
              </div>
              <p className="text-body-sm text-muted">{t("sources.counts", { alerts: source.sevenDayAlertCount, groups: source.sevenDayGroupCount, investigated: source.sevenDayInvestigatedCount })}</p>
              {source.authenticationFailureCount > 0 ? <p className="text-caption text-danger">{t("sources.authFailures", { count: source.authenticationFailureCount })}</p> : null}
            </CardBody>
          </Card>
        ))}
      </div>
      <AddAlertSourceSheet applicationId={applicationId} open={isSheetOpen} onOpenChange={setIsSheetOpen} onFinished={onChanged} />
      <ConfirmDialog open={sourceToRemove !== null} onOpenChange={(isOpen) => (isOpen ? undefined : setSourceToRemove(null))} title={t("sources.removeTitle")} description={t("sources.removeBody", { name: sourceToRemove?.sourceName ?? "" })}
        confirmLabel={t("sources.removeConfirm")} tone="danger" onConfirm={async () => { if (sourceToRemove) { await deleteSource.mutateAsync(sourceToRemove.alertSourceId); onChanged?.(); } }} />
      <Dialog open={rotation !== null} onOpenChange={(isOpen) => (isOpen ? undefined : setRotation(null))} title={t("sources.rotatedTitle")} footer={<Button onClick={() => setRotation(null)}>{t("sheet.done")}</Button>}>
        {rotation ? (
          <div className="flex flex-col gap-3">
            <Banner tone="warning">{t("sources.rotatedBody")}</Banner>
            <KeyValueList layout="stacked" items={[{ key: "secret", label: t("sheet.secret"), value: rotation.webhookSecret, copyValue: rotation.webhookSecret, isMonospace: true }, { key: "url", label: t("sheet.webhookUrl"), value: rotation.webhookUrl, copyValue: rotation.webhookUrl, isMonospace: true }]} />
          </div>
        ) : null}
      </Dialog>
    </section>
  );
}
