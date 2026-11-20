import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { formatDate, formatIsoWithZone, formatTime, toDate, type DateInput } from "@/utils/formatters";
import { Skeleton } from "./Skeleton";
import { toneFillClasses, toneSoftClasses, type StatusTone } from "./toneStyles";

export interface TimelineEvent {
  key: string;
  timestamp: DateInput;
  title: ReactNode;
  description?: ReactNode;
  /** Dot colour per event type (alert → alert, deployment → info, Keigan action → ai, …). */
  tone?: StatusTone;
  /** Icon in a small circle instead of a dot. */
  icon?: LucideIcon;
  /** Chips or source labels under the title. */
  meta?: ReactNode;
}

export interface TimelineProps {
  events: TimelineEvent[];
  isLoading?: boolean;
  emptyMessage?: ReactNode;
  className?: string;
}

/** Vertical timeline: 88 px tabular time column, 2 px rail, coloured dot per event (doc 04 §5). */
export function Timeline({ events, isLoading = false, emptyMessage, className }: TimelineProps) {
  const { t } = useTranslation("common");

  if (isLoading) {
    return (
      <div className={cn("flex flex-col gap-5", className)}>
        {Array.from({ length: 4 }, (_, skeletonIndex) => (
          <div key={skeletonIndex} className="grid grid-cols-[88px_24px_1fr] gap-x-3">
            <Skeleton className="h-4 w-14" />
            <Skeleton shape="circle" className="mx-auto size-2.5" />
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3.5 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return <p className={cn("py-6 text-center text-body-sm text-muted", className)}>{emptyMessage ?? t("timeline.empty")}</p>;
  }

  return (
    <ol className={cn("relative", className)}>
      {events.map((event, eventIndex) => {
        const eventDate = toDate(event.timestamp);
        const previousDate = eventIndex > 0 ? toDate(events[eventIndex - 1]?.timestamp) : null;
        const isNewDay = !previousDate || !eventDate || previousDate.toDateString() !== eventDate.toDateString();
        const tone = event.tone ?? "neutral";
        const EventIcon = event.icon;
        const isLast = eventIndex === events.length - 1;
        return (
          <li key={event.key} className="relative grid grid-cols-[88px_24px_1fr] gap-x-3 pb-5 last:pb-0">
            <div className="pt-0.5 text-right">
              {eventDate ? (
                <time dateTime={eventDate.toISOString()} title={formatIsoWithZone(eventDate)} className="block text-body-sm font-medium tabular-numbers text-default">
                  {formatTime(eventDate)}
                </time>
              ) : null}
              {eventDate && isNewDay ? <span className="block text-caption text-subtle">{formatDate(eventDate, { month: "short", day: "numeric" })}</span> : null}
            </div>
            <div className="relative flex justify-center">
              {!isLast ? <span aria-hidden="true" className="absolute top-3 bottom-[-12px] w-0.5 rounded-full bg-hairline" /> : null}
              {EventIcon ? (
                <span className={cn("relative z-[1] grid size-6 place-items-center rounded-full ring-4 ring-surface", toneSoftClasses[tone])}>
                  <EventIcon aria-hidden="true" size={13} strokeWidth={2} />
                </span>
              ) : (
                <span aria-hidden="true" className={cn("relative z-[1] mt-1.5 size-2.5 rounded-full ring-4 ring-surface", toneFillClasses[tone])} />
              )}
            </div>
            <div className="min-w-0 pt-0.5">
              <div className="text-body font-medium text-default">{event.title}</div>
              {event.description ? <div className="mt-0.5 text-body-sm text-muted">{event.description}</div> : null}
              {event.meta ? <div className="mt-2 flex flex-wrap items-center gap-1.5">{event.meta}</div> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
