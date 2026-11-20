import { useTranslation } from "react-i18next";
import { useInvestigationTimeline } from "@/api/investigationsApi";
import { ErrorState } from "@/components/ui/ErrorState";
import { Timeline, type TimelineEvent } from "@/components/ui/Timeline";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { timelineEventTone } from "./investigationPresentation";

/** Incident events, alerts, deployments and configuration changes, Keigan actions, chat facts and communications. */
export function TimelineSection({ investigationId, isRunning }: { investigationId: string; isRunning: boolean }) {
  const { t } = useTranslation("investigations");
  const { data, isLoading, isError, error, refetch } = useInvestigationTimeline(investigationId, isRunning);
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const events: TimelineEvent[] = (data ?? []).map((event) => ({
    key: event.timelineEventId,
    timestamp: event.eventOccurredAt,
    title: event.eventTitle,
    description: event.eventDetailsMarkdown ? <MarkdownView content={event.eventDetailsMarkdown} /> : undefined,
    tone: timelineEventTone(event.eventType),
    meta: t(`timeline.source.${event.eventSource}`, { defaultValue: event.eventSource }),
  }));
  return <Timeline events={events} isLoading={isLoading} emptyMessage={t("timeline.empty")} />;
}
