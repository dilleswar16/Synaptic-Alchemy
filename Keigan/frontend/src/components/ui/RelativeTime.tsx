import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { formatIsoWithZone, formatRelativeTime, toDate, type DateInput } from "@/utils/formatters";

export interface RelativeTimeProps {
  value: DateInput | null | undefined;
  /** Re-render interval (default 30 s) so "2 min ago" stays true. */
  refreshIntervalMilliseconds?: number;
  className?: string;
}

/**
 * `<time>` showing "12 min ago" under 24 h and the locale date-time after; hovering shows ISO 8601 with time zone.
 */
export function RelativeTime({ value, refreshIntervalMilliseconds = 30_000, className }: RelativeTimeProps) {
  useTranslation();
  const [now, setNow] = useState(() => new Date());
  const date = toDate(value);

  useEffect(() => {
    const intervalHandle = window.setInterval(() => setNow(new Date()), refreshIntervalMilliseconds);
    return () => window.clearInterval(intervalHandle);
  }, [refreshIntervalMilliseconds]);

  if (!date) {
    return null;
  }
  return (
    <time dateTime={date.toISOString()} title={formatIsoWithZone(date)} className={cn("tabular-numbers", className)}>
      {formatRelativeTime(date, now)}
    </time>
  );
}
