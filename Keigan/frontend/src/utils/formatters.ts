import i18n from "i18next";

/**
 * Locale-aware formatting (doc 01 §14, doc 04 §7). Every function uses the current i18n language,
 * so components re-render with the right format after a language switch (they re-render via useTranslation).
 */

export type DateInput = string | number | Date;

const formatterCache = new Map<string, Intl.NumberFormat | Intl.DateTimeFormat | Intl.RelativeTimeFormat>();

function cachedFormatter<FormatterType extends Intl.NumberFormat | Intl.DateTimeFormat | Intl.RelativeTimeFormat>(
  cacheKey: string,
  createFormatter: () => FormatterType,
): FormatterType {
  const existingFormatter = formatterCache.get(cacheKey);
  if (existingFormatter) {
    return existingFormatter as FormatterType;
  }
  const createdFormatter = createFormatter();
  formatterCache.set(cacheKey, createdFormatter);
  return createdFormatter;
}

/** BCP 47 locale used for Intl formatting (`en`, `ja`, `zh-CN`, `es-MX`, …). */
export function currentLocale(): string {
  return i18n.resolvedLanguage ?? i18n.language ?? "en";
}

/** Parses an ISO string, epoch milliseconds or Date. Returns null for missing or invalid input. */
export function toDate(value: DateInput | null | undefined): Date | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsedDate = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsedDate.getTime()) ? null : parsedDate;
}

function dateTimeFormatter(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const locale = currentLocale();
  return cachedFormatter(`date:${locale}:${JSON.stringify(options)}`, () => new Intl.DateTimeFormat(locale, options));
}

/** "19 Nov 2026, 13:12" in the user's locale and time zone. Empty string for missing values. */
export function formatDateTime(
  value: DateInput | null | undefined,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" },
): string {
  const date = toDate(value);
  return date ? dateTimeFormatter(options).format(date) : "";
}

/** "19 Nov 2026". */
export function formatDate(value: DateInput | null | undefined, options: Intl.DateTimeFormatOptions = { dateStyle: "medium" }): string {
  return formatDateTime(value, options);
}

/** "13:12" (or "1:12 PM"). */
export function formatTime(value: DateInput | null | undefined, options: Intl.DateTimeFormatOptions = { timeStyle: "short" }): string {
  return formatDateTime(value, options);
}

/** ISO 8601 with offset and zone name, used in timestamp tooltips: "2026-11-19T13:12:00+09:00 (Asia/Tokyo)". */
export function formatIsoWithZone(value: DateInput | null | undefined): string {
  const date = toDate(value);
  if (!date) {
    return "";
  }
  const offsetMinutes = -date.getTimezoneOffset();
  const offsetSign = offsetMinutes >= 0 ? "+" : "-";
  const absoluteOffsetMinutes = Math.abs(offsetMinutes);
  const pad = (numberValue: number) => String(numberValue).padStart(2, "0");
  const localIso =
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${offsetSign}${pad(Math.floor(absoluteOffsetMinutes / 60))}:${pad(absoluteOffsetMinutes % 60)}`;
  const timeZoneName = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return `${localIso} (${timeZoneName})`;
}

const relativeTimeThresholds: Array<{ unit: Intl.RelativeTimeFormatUnit; seconds: number }> = [
  { unit: "hour", seconds: 3600 },
  { unit: "minute", seconds: 60 },
  { unit: "second", seconds: 1 },
];

/**
 * Relative for less than 24 hours ("12 min ago", "in 3 hr"), absolute date-time otherwise (doc 04 §7).
 */
export function formatRelativeTime(value: DateInput | null | undefined, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) {
    return "";
  }
  const differenceSeconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const absoluteDifferenceSeconds = Math.abs(differenceSeconds);
  if (absoluteDifferenceSeconds >= 24 * 3600) {
    return formatDateTime(date);
  }
  const locale = currentLocale();
  const relativeFormatter = cachedFormatter(
    `relative:${locale}`,
    () => new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "short" }),
  );
  if (absoluteDifferenceSeconds < 45) {
    return relativeFormatter.format(0, "second");
  }
  for (const threshold of relativeTimeThresholds) {
    if (absoluteDifferenceSeconds >= threshold.seconds) {
      return relativeFormatter.format(Math.trunc(differenceSeconds / threshold.seconds), threshold.unit);
    }
  }
  return relativeFormatter.format(0, "second");
}

const durationUnits: Array<{ unit: "day" | "hour" | "minute" | "second"; milliseconds: number }> = [
  { unit: "day", milliseconds: 86_400_000 },
  { unit: "hour", milliseconds: 3_600_000 },
  { unit: "minute", milliseconds: 60_000 },
  { unit: "second", milliseconds: 1000 },
];

/**
 * Human duration with the largest units first: "1h 12m", "3d 4h", "45s" (narrow units, localised by Intl).
 * `maximumUnits` limits precision (default 2).
 */
export function formatDuration(
  milliseconds: number | null | undefined,
  options: { maximumUnits?: number; unitDisplay?: "narrow" | "short" | "long" } = {},
): string {
  if (milliseconds === null || milliseconds === undefined || !Number.isFinite(milliseconds)) {
    return "";
  }
  const { maximumUnits = 2, unitDisplay = "narrow" } = options;
  const locale = currentLocale();
  let remainingMilliseconds = Math.max(0, Math.round(milliseconds));
  const parts: string[] = [];
  for (const durationUnit of durationUnits) {
    if (parts.length >= maximumUnits) {
      break;
    }
    const unitCount = Math.floor(remainingMilliseconds / durationUnit.milliseconds);
    if (unitCount > 0 || (durationUnit.unit === "second" && parts.length === 0)) {
      const unitFormatter = cachedFormatter(
        `duration:${locale}:${durationUnit.unit}:${unitDisplay}`,
        () => new Intl.NumberFormat(locale, { style: "unit", unit: durationUnit.unit, unitDisplay }),
      );
      parts.push(unitFormatter.format(unitCount));
      remainingMilliseconds -= unitCount * durationUnit.milliseconds;
    } else if (parts.length > 0) {
      // Stop at the first empty unit after a non-empty one ("2h" rather than "2h 0m").
      break;
    }
  }
  return parts.join(" ");
}

/** "12,345" / "12.345" / "12 345" depending on locale. */
export function formatNumber(value: number | null | undefined, options: Intl.NumberFormatOptions = {}): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "";
  }
  const locale = currentLocale();
  return cachedFormatter(`number:${locale}:${JSON.stringify(options)}`, () => new Intl.NumberFormat(locale, options)).format(value);
}

/** "12K", "1.2M", "3.4万" … */
export function formatCompactNumber(value: number | null | undefined, maximumFractionDigits = 1): string {
  return formatNumber(value, { notation: "compact", maximumFractionDigits });
}

/**
 * Formats a percentage given on a 0–100 scale: `formatPercentage(99.95, { maximumFractionDigits: 2 })` → "99.95%".
 */
export function formatPercentage(
  percentValue: number | null | undefined,
  options: { minimumFractionDigits?: number; maximumFractionDigits?: number; signDisplay?: "auto" | "always" | "exceptZero" } = {},
): string {
  if (percentValue === null || percentValue === undefined || !Number.isFinite(percentValue)) {
    return "";
  }
  const { minimumFractionDigits = 0, maximumFractionDigits = 1, signDisplay = "auto" } = options;
  return formatNumber(percentValue / 100, { style: "percent", minimumFractionDigits, maximumFractionDigits, signDisplay });
}

/** "12.4K tokens" (pluralised through i18n). */
export function formatTokens(tokenCount: number | null | undefined): string {
  if (tokenCount === null || tokenCount === undefined || !Number.isFinite(tokenCount)) {
    return "";
  }
  return i18n.t("common:units.tokens", { count: tokenCount, formattedCount: formatCompactNumber(tokenCount) });
}

/** "1.4 MB" using the locale's number format. */
export function formatFileSize(byteCount: number | null | undefined): string {
  if (byteCount === null || byteCount === undefined || !Number.isFinite(byteCount)) {
    return "";
  }
  const units = ["byte", "kilobyte", "megabyte", "gigabyte"] as const;
  let unitIndex = 0;
  let scaledValue = byteCount;
  while (scaledValue >= 1024 && unitIndex < units.length - 1) {
    scaledValue /= 1024;
    unitIndex += 1;
  }
  return formatNumber(scaledValue, {
    style: "unit",
    unit: units[unitIndex],
    unitDisplay: "short",
    maximumFractionDigits: unitIndex === 0 ? 0 : 1,
  });
}
