import { useMemo } from "react";
import { History } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useInvestigationTimeline, type TimelineEvent as InvestigationTimelineEvent } from "@/api/investigationsApi";
import { Badge } from "@/components/ui/Badge";
import { ErrorState } from "@/components/ui/ErrorState";
import { Timeline, type TimelineEvent } from "@/components/ui/Timeline";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { isPipelineEvent, timelineEventTone } from "./investigationPresentation";

/** Pipeline steps closer together than this belong to one run and are folded into a single row. */
const pipelineRunWindowMilliseconds = 5_000;

/** Incident events, alerts, deployments and configuration changes, Keigan actions, chat facts and communications. */
export function TimelineSection({ investigationId, isRunning }: { investigationId: string; isRunning: boolean }) {
  const { t } = useTranslation("investigations");
  const { data, isLoading, isError, error, refetch } = useInvestigationTimeline(investigationId, isRunning);
  const events = useMemo<TimelineEvent[]>(() => {
    const sourceOf = (event: InvestigationTimelineEvent) => t(`timeline.source.${event.eventSource}`, { defaultValue: event.eventSource });
    const toRow = (event: InvestigationTimelineEvent, isBeforeIncident: boolean): TimelineEvent => ({
      key: event.timelineEventId,
      timestamp: event.eventOccurredAt,
      title: event.eventTitle,
      description: event.eventDetailsMarkdown ? <MarkdownView content={event.eventDetailsMarkdown} /> : undefined,
      tone: isBeforeIncident ? "warning" : timelineEventTone(event.eventType),
      icon: isBeforeIncident ? History : undefined,
      meta: (
        <>
          {isBeforeIncident ? <Badge tone="warning">{t("timeline.beforeIncident")}</Badge> : null}
          {sourceOf(event)}
        </>
      ),
    });
    const ordered = data ?? [];
    // Changes (deployments, configuration changes) that precede everything else on the timeline are the prime suspects.
    const firstOtherEvent = ordered.find((event) => event.eventType !== "change");
    const firstOtherAt = firstOtherEvent ? Date.parse(firstOtherEvent.eventOccurredAt) : Number.POSITIVE_INFINITY;
    const rows: TimelineEvent[] = [];
    for (let index = 0; index < ordered.length; index += 1) {
      const event = ordered[index]!;
      if (isPipelineEvent(event.eventType, event.eventSource)) {
        const runStart = Date.parse(event.eventOccurredAt);
        const run = [event];
        while (index + 1 < ordered.length) {
          const next = ordered[index + 1]!;
          if (!isPipelineEvent(next.eventType, next.eventSource) || Date.parse(next.eventOccurredAt) - runStart > pipelineRunWindowMilliseconds) break;
          run.push(next);
          index += 1;
        }
        if (run.length > 1) {
          rows.push({
            key: `pipeline-${event.timelineEventId}`,
            timestamp: event.eventOccurredAt,
            title: t("timeline.pipelineTitle", { count: run.length }),
            tone: "ai",
            description: (
              <details>
                <summary className="cursor-pointer text-caption font-semibold text-action">{t("timeline.pipelineShow")}</summary>
                <ol className="mt-2 flex list-decimal flex-col gap-2 pl-5">
                  {run.map((step) => (
                    <li key={step.timelineEventId}>
                      <p className="font-medium text-default">{step.eventTitle}</p>
                      {step.eventDetailsMarkdown ? <MarkdownView content={step.eventDetailsMarkdown} /> : null}
                    </li>
                  ))}
                </ol>
              </details>
            ),
            meta: sourceOf(event),
          });
          continue;
        }
      }
      rows.push(toRow(event, event.eventType === "change" && Date.parse(event.eventOccurredAt) < firstOtherAt));
    }
    return rows;
  }, [data, t]);
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;
  return <Timeline events={events} isLoading={isLoading} emptyMessage={t("timeline.empty")} />;
}
