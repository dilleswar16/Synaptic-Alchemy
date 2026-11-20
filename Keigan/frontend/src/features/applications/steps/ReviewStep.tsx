import { useState, type ReactNode } from "react";
import { CheckCircle2, ChevronDown, Circle, Info, PauseCircle, PlayCircle, Rocket } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { isApiError } from "@/api/httpClient";
import { useApplication, useApplicationLifecycleAction, useReadiness, type Requirement } from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StepStatusIcon } from "@/components/ui/Stepper";
import { cn } from "@/utils/cn";
import { StepFrame } from "../components/StepFrame";
import { stepDefinitions, type StepProps } from "../stepRegistry";

function RequirementRow({ requirement, applicationId, isNeutral }: { requirement: Requirement; applicationId: string; isNeutral: boolean }) {
  const { t } = useTranslation("applications");
  const Icon = requirement.isDone ? CheckCircle2 : isNeutral ? Info : Circle;
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span className="flex items-center gap-2.5 text-body-sm">
        <Icon size={18} aria-hidden="true" className={cn("shrink-0", requirement.isDone ? "text-success" : "text-muted")} />
        <span>
          {t(`${isNeutral ? "goodToKnow" : "requirements"}.${requirement.requirementKey}${isNeutral && requirement.isDone ? "_done" : ""}`, { count: requirement.count ?? 0 })}
        </span>
      </span>
      {!requirement.isDone || isNeutral ? <Link className="text-body-sm text-action hover:underline" to={`/applications/${applicationId}/${requirement.stepKey}`}>{t("review.edit")}</Link> : null}
    </li>
  );
}

/** Collapsed by default: the full checklist and the per-step summary are reference, not what the reader has to act on. */
function Disclosure({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <details className="group">
      <summary className="inline-flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-xs text-body-sm font-medium text-action outline-none hover:underline focus-visible:ring-2 focus-visible:ring-action [&::-webkit-details-marker]:hidden">
        <ChevronDown aria-hidden="true" size={16} className="transition-transform group-open:rotate-180" />
        {label}
      </summary>
      <div className="mt-4 flex flex-col gap-6">{children}</div>
    </details>
  );
}

/** Step 11: read-only summary per step with Edit links, the required checklist (only these block go-live) and the go-live confirmation. */
export function ReviewStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("applications");
  const applicationQuery = useApplication(applicationId);
  const readinessQuery = useReadiness(applicationId);
  const lifecycleAction = useApplicationLifecycleAction(applicationId);
  const [isConfirmingGoLive, setIsConfirmingGoLive] = useState(false);
  const application = applicationQuery.data;
  const readiness = readinessQuery.data;

  if (readinessQuery.isError) return <ErrorState error={readinessQuery.error} onRetry={() => void readinessQuery.refetch()} />;
  if (!application || !readiness) return <Skeleton className="h-80 rounded-lg" />;

  const isLive = application.lifecycleStatus === "live";
  const isPaused = application.lifecycleStatus === "paused";
  const blockers = readiness.required.filter((requirement) => !requirement.isDone);
  const hasBlockers = blockers.length > 0;
  const requirementsCard = (requirements: Requirement[]) => (
    <Card>
      <CardHeader title={t("review.requiredTitle")} description={t("review.requiredDescription")} />
      <CardBody><ul className="divide-y divide-hairline">{requirements.map((requirement) => <RequirementRow key={requirement.requirementKey} requirement={requirement} applicationId={applicationId} isNeutral={false} />)}</ul></CardBody>
    </Card>
  );
  const goodToKnowCard = (
    <Card>
      <CardHeader title={t("review.goodToKnowTitle")} description={t("review.goodToKnowDescription")} />
      <CardBody><ul className="divide-y divide-hairline">{readiness.goodToKnow.map((requirement) => <RequirementRow key={requirement.requirementKey} requirement={requirement} applicationId={applicationId} isNeutral />)}</ul></CardBody>
    </Card>
  );
  const summaryCard = (
    <Card>
      <CardHeader title={t("review.summaryTitle")} />
      <CardBody>
        <ul className="divide-y divide-hairline">
          {stepDefinitions.filter((definition) => definition.key !== "review").map((definition) => {
            const status = readiness.steps.find((entry) => entry.stepKey === definition.key)?.status ?? "not_started";
            return (
              <li key={definition.key} className="flex items-center justify-between gap-3 py-2">
                <span className="flex items-center gap-2.5 text-body-sm"><StepStatusIcon status={status} size={18} />{t(`steps.${definition.key}.label`)}<span className="text-muted">· {t(`status.${status}`)}</span></span>
                <Link className="text-body-sm text-action hover:underline" to={`/applications/${applicationId}/${definition.key}`}>{t("review.edit")}</Link>
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
  const goLiveBar =
    !isLive && !isPaused && canEdit ? (
      <div className="flex flex-col items-start gap-2">
        <Button size="lg" leadingIcon={Rocket} disabled={!readiness.canGoLive} onClick={() => setIsConfirmingGoLive(true)}>{t("actions.goLive")}</Button>
        {!readiness.canGoLive ? <p className="text-body-sm text-muted">{t("review.goLiveBlocked")}</p> : null}
      </div>
    ) : null;

  return (
    <StepFrame stepKey="review">
      {isLive || isPaused ? (
        <Banner tone={isPaused ? "warning" : "success"} title={isPaused ? t("review.pausedTitle") : t("review.liveTitle")}
          action={canEdit ? (
            <Button size="sm" variant="secondary" leadingIcon={isPaused ? PlayCircle : PauseCircle} isLoading={lifecycleAction.isPending} onClick={() => lifecycleAction.mutate(isPaused ? "resume" : "pause", { onSuccess: onStatusChange })}>
              {isPaused ? t("actions.resume") : t("actions.pause")}
            </Button>
          ) : undefined}
        >
          {isPaused ? t("review.pausedBody") : t("review.liveBody")}
        </Banner>
      ) : null}

      {hasBlockers ? (
        <>
          {requirementsCard(blockers)}
          {goLiveBar}
          <Disclosure label={t("review.moreDetails")}>
            {requirementsCard(readiness.required)}
            {goodToKnowCard}
            {summaryCard}
          </Disclosure>
        </>
      ) : (
        <>
          {requirementsCard(readiness.required)}
          {goodToKnowCard}
          {goLiveBar}
          <Disclosure label={t("review.showSummary")}>{summaryCard}</Disclosure>
        </>
      )}
      {lifecycleAction.isError ? <Banner tone="danger">{isApiError(lifecycleAction.error) ? lifecycleAction.error.detail : t("review.actionFailed")}</Banner> : null}

      <ConfirmDialog
        open={isConfirmingGoLive}
        onOpenChange={setIsConfirmingGoLive}
        tone="primary"
        title={t("review.goLiveTitle", { name: application.applicationName })}
        description={t("review.goLiveDescription")}
        confirmLabel={t("actions.goLive")}
        onConfirm={async () => { await lifecycleAction.mutateAsync("go-live"); onStatusChange?.(); }}
      >
        <ul className="list-disc pl-5 text-body-sm">
          {(["polling", "alerts", "sli", "predictive", "notifications"] as const).map((item) => <li key={item}>{t(`review.starts.${item}`)}</li>)}
        </ul>
      </ConfirmDialog>
    </StepFrame>
  );
}
