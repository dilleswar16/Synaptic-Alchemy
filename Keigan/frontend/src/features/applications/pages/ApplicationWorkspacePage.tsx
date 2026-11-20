import { useCallback, useMemo, type ComponentType } from "react";
import { ArrowLeft, ArrowRight, Network } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { applicationQueryKeys, useApplication, useReadiness, type StepKey } from "@/api/applicationsApi";
import { PageHeader } from "@/components/layout/PageHeader";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ReadinessBar } from "@/components/ui/ReadinessBar";
import { SaveIndicator } from "@/components/ui/SaveIndicator";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusChip } from "@/components/ui/StatusChip";
import { Stepper, type StepperStage } from "@/components/ui/Stepper";
import { cn } from "@/utils/cn";
import { lifecycleTone } from "../components/lifecycle";
import { useSaveStatus } from "../hooks/useSaveStatus";
import { isStepKey, stageOrder, stepDefinitions, type StepProps } from "../stepRegistry";
import { AccessStep } from "../steps/AccessStep";
import { ComponentsStep } from "../steps/ComponentsStep";
import { IncidentsAndAlertsStep } from "../steps/IncidentsAndAlertsStep";
import { KnowledgeStep } from "../steps/KnowledgeStep";
import { LogToolsStep } from "../steps/LogToolsStep";
import { NotificationsStep } from "../steps/NotificationsStep";
import { ReviewStep } from "../steps/ReviewStep";
import { RunbooksStep } from "../steps/RunbooksStep";
import { ServicesStep } from "../steps/ServicesStep";
import { SloStep } from "../steps/SloStep";
import { TopologyStep } from "../steps/TopologyStep";

const stepComponents: Record<StepKey, ComponentType<StepProps>> = {
  components: ComponentsStep,
  services: ServicesStep,
  log_tools: LogToolsStep,
  knowledge: KnowledgeStep,
  topology: TopologyStep,
  runbooks: RunbooksStep,
  incidents: IncidentsAndAlertsStep,
  slo: SloStep,
  notifications: NotificationsStep,
  access: AccessStep,
  review: ReviewStep,
};

/**
 * Application workspace (spec 6.2): header with readiness bar, stage stepper and one step at a time at
 * `/applications/:applicationId/:stepKey`. Wizard mode (Back / Continue bar) until go-live, page mode afterwards.
 */
export default function ApplicationWorkspacePage() {
  const { t } = useTranslation("applications");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const parameters = useParams();
  const applicationId = parameters.applicationId ?? "";
  const stepKey = (parameters["*"] ?? "").split("/")[0];
  const applicationQuery = useApplication(applicationId);
  const readinessQuery = useReadiness(applicationId);
  const saveStatus = useSaveStatus();
  const refreshReadiness = useCallback(() => void queryClient.invalidateQueries({ queryKey: applicationQueryKeys.readiness(applicationId) }), [queryClient, applicationId]);

  const readiness = readinessQuery.data;
  const stages = useMemo<StepperStage[]>(
    () =>
      stageOrder.map((stage) => ({
        key: stage,
        label: t(`stages.${stage}`),
        steps: stepDefinitions
          .filter((definition) => definition.stage === stage)
          .map((definition) => ({
            key: definition.key,
            label: t(`steps.${definition.key}.label`),
            description: t(`requirement.${definition.requirement}`),
            status: readiness?.steps.find((entry) => entry.stepKey === definition.key)?.status ?? "not_started",
          })),
      })),
    [readiness, t],
  );

  if (!stepKey || !isStepKey(stepKey)) return <Navigate to={`/applications/${applicationId}/components`} replace />;
  if (applicationQuery.isError) return <ErrorState error={applicationQuery.error} onRetry={() => void applicationQuery.refetch()} />;
  if (applicationQuery.isLoading || !applicationQuery.data) return <Skeleton className="h-96 rounded-lg" />;

  const application = applicationQuery.data;
  const isLive = application.lifecycleStatus === "live" || application.lifecycleStatus === "paused";
  const mode: StepProps["mode"] = isLive ? "page" : "wizard";
  const canEdit = application.canEdit && application.lifecycleStatus !== "requested";
  const stepIndex = stepDefinitions.findIndex((definition) => definition.key === stepKey);
  const previousStep = stepDefinitions[stepIndex - 1];
  const nextStep = stepDefinitions[stepIndex + 1];
  const currentDefinition = stepDefinitions[stepIndex];
  if (!currentDefinition) return <Navigate to={`/applications/${applicationId}/components`} replace />;
  const StepComponent = stepComponents[stepKey];
  const requiredDoneCount = readiness?.required.filter((requirement) => requirement.isDone).length ?? 0;
  const nextRequirement = readiness?.required.find((requirement) => !requirement.isDone);
  const goToStep = (target: string) => navigate(`/applications/${applicationId}/${target}`);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: t("pageTitle"), to: "/applications" }, { label: application.applicationName }]}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {application.applicationName}
            <span className="rounded bg-sunken px-2 py-0.5 font-mono text-body-sm font-medium text-muted">{application.applicationCode}</span>
            <StatusChip tone={lifecycleTone[application.lifecycleStatus]} dot>{t(`lifecycle.${application.lifecycleStatus}`)}</StatusChip>
          </span>
        }
        description={[application.businessUnitName, application.regionCode ? t(`regions.${application.regionCode}`, { defaultValue: application.regionCode }) : null].filter(Boolean).join(" · ") || undefined}
        actions={<Button variant="secondary" leadingIcon={Network} onClick={() => goToStep("topology")}>{t("viewTopology")}</Button>}
      >
        {readiness && !isLive ? (
          <ReadinessBar
            className="mt-4"
            completedRequiredCount={requiredDoneCount}
            requiredCount={readiness.required.length}
            nextStepLabel={nextRequirement ? t(`readinessNext.${nextRequirement.requirementKey}`) : undefined}
            onSeeAll={() => goToStep("review")}
          />
        ) : null}
      </PageHeader>

      {application.lifecycleStatus === "requested" ? <Banner tone="info" className="mb-4" title={t("banners.requestedTitle")}>{t("banners.requestedBody")}</Banner> : null}
      {application.lifecycleStatus === "paused" ? <Banner tone="warning" className="mb-4" title={t("banners.pausedTitle")}>{t("banners.pausedBody")}</Banner> : null}
      {!canEdit && application.lifecycleStatus !== "requested" ? <Banner tone="neutral" className="mb-4">{t("banners.readOnly")}</Banner> : null}

      <div className="grid items-start gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-20">
          <Stepper aria-label={t("stepperLabel")} stages={stages} currentStepKey={stepKey} onStepSelect={(selectedKey) => goToStep(selectedKey)} />
        </aside>
        <section aria-live="polite" className="min-w-0">
          <div className={cn("pb-24", currentDefinition.isWide ? "" : "max-w-[760px]")}>
            <StepComponent applicationId={applicationId} mode={mode} canEdit={canEdit} onStatusChange={refreshReadiness} />
          </div>
          {mode === "wizard" ? (
            <div className="sticky bottom-0 -mx-1 mt-6 flex items-center justify-between gap-4 border-t border-hairline bg-canvas/90 px-1 py-3 backdrop-blur">
              <Button variant="ghost" leadingIcon={ArrowLeft} disabled={!previousStep} onClick={() => previousStep && goToStep(previousStep.key)}>{t("actions.back")}</Button>
              <SaveIndicator status={saveStatus.status} savedAt={saveStatus.savedAt} />
              <Button trailingIcon={ArrowRight} disabled={!nextStep} onClick={() => nextStep && goToStep(nextStep.key)}>{t("actions.continue")}</Button>
            </div>
          ) : (
            <div className="sticky bottom-0 mt-6 flex justify-end border-t border-hairline bg-canvas/90 px-1 py-3 backdrop-blur">
              <SaveIndicator status={saveStatus.status} savedAt={saveStatus.savedAt} />
            </div>
          )}
        </section>
      </div>
    </>
  );
}
