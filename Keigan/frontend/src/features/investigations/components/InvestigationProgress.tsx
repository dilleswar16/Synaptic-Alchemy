import { CircleCheck, Loader } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InvestigationProgress as ProgressPayload, StageMessage } from "@/api/investigationsApi";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatTime } from "@/utils/formatters";
import { cn } from "@/utils/cn";
import { investigationStages } from "./investigationPresentation";

interface InvestigationProgressProps {
  progress: ProgressPayload | undefined;
  fallbackStage: string;
  fallbackPercent: number;
  fallbackMessages: StageMessage[];
}

/** Live progress while an investigation runs: percent, the six stages and the human-readable stage messages. */
export function InvestigationProgress({ progress, fallbackStage, fallbackPercent, fallbackMessages }: InvestigationProgressProps) {
  const { t } = useTranslation("investigations");
  const currentStage = progress?.currentStageName ?? fallbackStage;
  const percent = progress?.progressPercent ?? fallbackPercent;
  const messages = (progress?.stageMessages ?? fallbackMessages).slice(-8).reverse();
  const currentIndex = investigationStages.findIndex((stage) => stage === currentStage);
  return (
    <Card radius="lg" className="mb-6" aria-live="polite">
      <CardHeader title={t("progress.title")} description={t("progress.description")} />
      <CardBody className="flex flex-col gap-6">
        <ProgressBar value={percent} tone="ai" size="md" showValue label={t(`stage.${currentStage}`, { defaultValue: t("progress.starting") })} aria-label={t("progress.ariaLabel")} />
        <ol className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {investigationStages.map((stage, stageIndex) => {
            const isDone = currentIndex > stageIndex;
            const isCurrent = currentIndex === stageIndex;
            return (
              <li key={stage} className={cn("flex items-center gap-2 rounded-md border px-3 py-2 text-body-sm", isCurrent ? "border-transparent bg-ai-soft text-ai" : isDone ? "border-hairline bg-surface text-default" : "border-hairline bg-surface-sunken text-subtle")}>
                {isDone ? <CircleCheck aria-hidden="true" size={16} className="text-success" /> : isCurrent ? <Loader aria-hidden="true" size={16} className="animate-spin" /> : <span aria-hidden="true" className="size-4 rounded-full border border-strong" />}
                <span className="font-medium">{t(`stage.${stage}`)}</span>
              </li>
            );
          })}
        </ol>
        <div>
          <h3 className="mb-2 text-body-sm font-semibold text-default">{t("progress.activity")}</h3>
          {messages.length === 0 ? (
            <Skeleton className="h-5 w-2/3" />
          ) : (
            <ul className="flex flex-col gap-1.5">
              {messages.map((message, messageIndex) => (
                <li key={`${message.at}-${messageIndex}`} className={cn("flex gap-3 text-body-sm", messageIndex === 0 ? "text-default" : "text-muted")}>
                  <span className="w-14 shrink-0 font-mono text-caption text-subtle">{formatTime(message.at, { timeStyle: "medium" })}</span>
                  <span>{message.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
