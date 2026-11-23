import { useEffect, useState } from "react";
import { ExternalLink, History, MessageSquareText, RotateCcw, ThumbsUp, CircleCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { useRerunInvestigation, type InvestigationDetail } from "@/api/investigationsApi";
import { isApiError } from "@/api/httpClient";
import { useSimilarIncidents } from "@/api/incidentMemoryApi";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PriorityChip } from "@/components/ui/PriorityChip";
import { StatusChip } from "@/components/ui/StatusChip";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime, formatDuration } from "@/utils/formatters";
import { investigationStatusTone } from "./investigationPresentation";
import { similarIncidentsElementId } from "./SimilarIncidentsCard";

function useNow(intervalMilliseconds: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timerId = window.setInterval(() => setNow(Date.now()), intervalMilliseconds);
    return () => window.clearInterval(timerId);
  }, [intervalMilliseconds]);
  return now;
}

function Timer({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-micro uppercase tracking-wide text-muted">{label}</span>
      <span className="text-body-sm font-semibold text-default">{value}</span>
    </div>
  );
}

interface InvestigationHeaderProps {
  detail: InvestigationDetail;
  canEdit: boolean;
  onOpenTeamsRoom: () => void;
  onResolve: () => void;
  onFeedback: () => void;
}

/** Header card: incident, priorities, status, services, timers and the page actions. */
export function InvestigationHeader({ detail, canEdit, onOpenTeamsRoom, onResolve, onFeedback }: InvestigationHeaderProps) {
  const { t } = useTranslation("investigations");
  const navigate = useNavigate();
  const { showToast } = useToast();
  const rerun = useRerunInvestigation(detail.investigationId);
  const now = useNow(30_000);
  const seenBeforeCount = useSimilarIncidents(detail.investigationId).data?.items.filter((match) => !match.isRejected).length ?? 0;
  const incident = detail.incident;
  const isOpenIncident = incident ? !["resolved", "closed"].includes(incident.incidentStatus) : false;
  const detectedAt = detail.detectedAt ? new Date(detail.detectedAt).getTime() : null;
  const endTime = incident?.resolvedAt ? new Date(incident.resolvedAt).getTime() : now;
  const keiganPriority = incident?.keiganPriority ?? (detail.keiganPriority ?? null);

  const handleRerun = () =>
    rerun.mutate(undefined, {
      onSuccess: (job) => {
        showToast({ tone: "ai", title: t("header.rerunStartedTitle"), description: t("header.rerunStartedDescription") });
        void navigate(`/investigations/${job.jobId}`);
      },
      onError: (error) => showToast({ tone: "danger", title: t("header.rerunFailed"), description: isApiError(error) ? error.detail : undefined }),
    });

  return (
    <Card accent radius="lg" className="mb-6">
      <div className="flex flex-col gap-5 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-1 basis-[40rem] flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {keiganPriority ? <PriorityChip priority={keiganPriority} /> : null}
              {incident?.servicenowPriority && incident.servicenowPriority !== keiganPriority ? (
                <span className="text-caption text-muted">{t("header.servicenowPriority", { priority: incident.servicenowPriority })}</span>
              ) : null}
              <StatusChip tone={investigationStatusTone[detail.investigationStatus]} pulse={detail.investigationStatus === "running"}>
                {t(`status.${detail.investigationStatus}`)}
              </StatusChip>
              {incident ? <StatusChip tone={isOpenIncident ? "alert" : "success"} variant="outline">{t(`incidentStatus.${incident.incidentStatus}`)}</StatusChip> : <StatusChip tone="neutral" variant="outline">{t(`trigger.${detail.investigationTrigger}`)}</StatusChip>}
              <AiGeneratedChip modelName={detail.modelNames.join(", ") || null} generatedAt={detail.completedAt} size="sm" />
              {seenBeforeCount > 0 ? (
                <button type="button" onClick={() => document.getElementById(similarIncidentsElementId)?.scrollIntoView({ behavior: "smooth", block: "start" })} className="rounded-full focus-visible:outline-2 focus-visible:outline-offset-2">
                  <StatusChip tone="info" variant="outline" icon={History}>{t("header.seenBefore", { count: seenBeforeCount })}</StatusChip>
                </button>
              ) : null}
            </div>
            <h1 className="break-words font-display text-h2 text-default">{detail.incidentTitle ?? t("header.manualTitle")}</h1>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-sm text-muted">
              {detail.incidentNumber ? (
                incident?.servicenowUrl ? (
                  <a href={incident.servicenowUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono text-action hover:underline">
                    {detail.incidentNumber}
                    <ExternalLink aria-hidden="true" size={13} />
                  </a>
                ) : (
                  <span className="font-mono">{detail.incidentNumber}</span>
                )
              ) : null}
              <span>{detail.application.applicationName}</span>
              {detail.services.length > 0 ? <span>{detail.services.map((service) => service.serviceName).join(", ")}</span> : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canEdit ? (
              <Button variant="secondary" leadingIcon={RotateCcw} onClick={handleRerun} isLoading={rerun.isPending} disabled={detail.investigationStatus === "running" || detail.investigationStatus === "queued"}>
                {t("header.rerun")}
              </Button>
            ) : null}
            {incident ? <Button variant="secondary" leadingIcon={MessageSquareText} onClick={onOpenTeamsRoom}>{t("header.openTeamsChat")}</Button> : null}
            <Button variant="secondary" leadingIcon={ThumbsUp} onClick={onFeedback} disabled={!detail.investigationStatus.startsWith("completed")}>{t("header.feedback")}</Button>
            {canEdit && incident && isOpenIncident ? <Button leadingIcon={CircleCheck} onClick={onResolve}>{t("header.resolve")}</Button> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-t border-hairline pt-4">
          <Timer label={t("header.timers.detected")} value={detail.detectedAt ? formatDateTime(detail.detectedAt) : "-"} />
          <Timer label={t("header.timers.firstUpdate")} value={detail.firstUpdateSentAt ? formatDateTime(detail.firstUpdateSentAt) : t("header.timers.notSentYet")} />
          <Timer label={isOpenIncident || !incident ? t("header.timers.elapsed") : t("header.timers.duration")} value={detectedAt ? formatDuration(Math.max(0, endTime - detectedAt), { maximumUnits: 2, unitDisplay: "short" }) : "-"} />
          {detail.userFeedbackVerdict ? <Timer label={t("header.timers.feedback")} value={t(`feedback.verdict.${detail.userFeedbackVerdict}`)} /> : null}
        </div>
      </div>
    </Card>
  );
}
