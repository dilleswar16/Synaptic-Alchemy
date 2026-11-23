import { useEffect, useState } from "react";
import { Scale } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useErrorBudgetPolicy, useSaveErrorBudgetPolicy, type ErrorBudgetPolicy } from "@/api/errorBudgetApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { Switch } from "@/components/ui/Switch";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";

/** An empty box means "use the default". */
function numberOrNull(text: string): number | null {
  const trimmed = text.trim();
  return trimmed === "" ? null : Number(trimmed);
}

function initialText(value: number, usesDefault: boolean): string {
  return usesDefault ? "" : String(value);
}

function Form({ policy, applicationId }: { policy: ErrorBudgetPolicy; applicationId: string }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const { showToast } = useToast();
  const save = useSaveErrorBudgetPolicy(applicationId);
  const [isEnabled, setIsEnabled] = useState(policy.isEnabled);
  const [singleThreshold, setSingleThreshold] = useState(initialText(policy.singleIncidentThresholdPercent, policy.usesDefault.singleIncidentThreshold));
  const [classThreshold, setClassThreshold] = useState(initialText(policy.outageClassThresholdPercent, policy.usesDefault.outageClassThreshold));
  const [classWindow, setClassWindow] = useState(initialText(policy.outageClassWindowDays, policy.usesDefault.outageClassWindow));
  const [guidance, setGuidance] = useState(policy.exhaustedBudgetGuidanceText ?? "");
  const [failure, setFailure] = useState<string | null>(null);
  useEffect(() => {
    setIsEnabled(policy.isEnabled);
    setGuidance(policy.exhaustedBudgetGuidanceText ?? "");
  }, [policy.isEnabled, policy.exhaustedBudgetGuidanceText]);

  const readOnly = !policy.canEdit;
  const single = numberOrNull(singleThreshold) ?? policy.defaults.singleIncidentThresholdPercent;
  const windowDays = numberOrNull(classWindow) ?? policy.defaults.outageClassWindowDays;
  const onSave = () => {
    setFailure(null);
    save.mutate(
      {
        isEnabled,
        singleIncidentThresholdPercent: numberOrNull(singleThreshold),
        outageClassThresholdPercent: numberOrNull(classThreshold),
        outageClassWindowDays: numberOrNull(classWindow),
        exhaustedBudgetGuidanceText: guidance.trim() === "" ? null : guidance,
      },
      {
        onSuccess: () => showToast({ tone: "success", title: t("policy.saved") }),
        onError: (error) => setFailure((isApiError(error) ? error.detail : undefined) ?? t("errors.actionFailed")),
      },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {failure ? <Banner tone="danger" title={t("errors.actionFailed")}>{failure}</Banner> : null}
      <Switch checked={isEnabled} disabled={readOnly} onCheckedChange={setIsEnabled} label={t("policy.holdUs")} description={isEnabled ? undefined : t("policy.offHelp")} />
      <div className="grid gap-4 sm:grid-cols-3">
        <Input
          label={t("policy.singleThreshold")} type="number" min={1} max={100} step="any" disabled={readOnly} value={singleThreshold} onChange={(event) => setSingleThreshold(event.target.value)}
          placeholder={String(policy.defaults.singleIncidentThresholdPercent)} helperText={t("policy.defaultHint", { value: policy.defaults.singleIncidentThresholdPercent })} trailingContent="%"
        />
        <Input
          label={t("policy.classThreshold")} type="number" min={1} max={100} step="any" disabled={readOnly} value={classThreshold} onChange={(event) => setClassThreshold(event.target.value)}
          placeholder={String(policy.defaults.outageClassThresholdPercent)} helperText={t("policy.defaultHint", { value: policy.defaults.outageClassThresholdPercent })} trailingContent="%"
        />
        <Input
          label={t("policy.classWindow")} type="number" min={7} max={policy.maximumOutageClassWindowDays} disabled={readOnly} value={classWindow} onChange={(event) => setClassWindow(event.target.value)}
          placeholder={String(policy.defaults.outageClassWindowDays)} helperText={t("policy.windowHint", { default: policy.defaults.outageClassWindowDays, maximum: policy.maximumOutageClassWindowDays })}
        />
      </div>
      <Textarea
        label={t("policy.guidance")} helperText={t("policy.guidanceHelp", { maximum: policy.guidanceMaximumCharacters })} placeholder={t("policy.guidancePlaceholder")} maxLength={policy.guidanceMaximumCharacters}
        disabled={readOnly} isOptional autoResize maximumRows={8} value={guidance} onChange={(event) => setGuidance(event.target.value)}
      />
      <p className="rounded-md bg-surface-sunken px-4 py-3 text-body-sm text-muted">
        {isEnabled ? t("policy.sentenceOn", { threshold: single, window: windowDays }) : t("policy.sentenceOff")}
      </p>
      {readOnly ? null : <div><Button isLoading={save.isPending} onClick={onSave}>{t("policy.save")}</Button></div>}
    </div>
  );
}

/** The team's agreement about error budgets: off until the team turns it on, with Google's example thresholds as the defaults. */
export function ErrorBudgetPolicySection({ applicationId }: { applicationId: string }) {
  const { t } = useTranslation("errorBudgetPolicy");
  const { data, isLoading, isError, error, refetch } = useErrorBudgetPolicy(applicationId);
  return (
    <Card radius="lg">
      <CardHeader title={t("policy.title")} description={t("policy.description")} actions={<Scale size={18} aria-hidden className="text-muted" />} />
      <CardBody>
        {isLoading ? <Skeleton className="h-48 w-full" /> : null}
        {isError ? <ErrorState error={error} onRetry={() => void refetch()} /> : null}
        {data ? <Form policy={data} applicationId={applicationId} /> : null}
      </CardBody>
    </Card>
  );
}
