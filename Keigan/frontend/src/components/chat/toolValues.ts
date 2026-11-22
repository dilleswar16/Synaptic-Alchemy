import type { TFunction } from "i18next";
import { formatDateTime, formatList, formatNumber } from "@/utils/formatters";

/** Reading tool arguments and output previews: both are the tool's own JSON, so every reader checks the shape before it trusts it. */

const isoDateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.flatMap((item): Array<Record<string, unknown>> => { const record = asRecord(item); return record ? [record] : []; }) : [];
}

export function isScalar(value: unknown): value is string | number | boolean | null {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

/** "service_name" -> "Service name": the label of a field that has no translation. */
function humaniseFieldName(fieldName: string): string {
  const words = fieldName.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** A field or argument name in the user's language (`chat:<group>.<name>`), or its humanised name when no translation exists. */
export function fieldLabel(translate: TFunction, fieldName: string, group: "fields" | "arguments" = "fields"): string {
  return translate(`${group}.${fieldName}`, { defaultValue: humaniseFieldName(fieldName) });
}

/** A lower-case word or snake_case token: the shape of the status and kind values the tools send (`at_risk`, `configuration_change`). */
const enumTokenPattern = /^[a-z][a-z0-9_]*$/;

/**
 * A status or kind token in the user's language (`chat:values.<token>`); a token without a translation, and any other text, comes back as it is. With
 * `asWords` a token without a translation has its underscores read as spaces ("tier_1" as "tier 1"), for fields that are only ever such tokens.
 */
export function formatEnumToken(translate: TFunction, value: string, asWords = false): string {
  return enumTokenPattern.test(value) ? translate(`values.${value}`, { defaultValue: asWords ? value.replaceAll("_", " ") : value }) : value;
}

/** One tool value as text: dates and numbers in the user's locale, yes/no for booleans, lists joined, anything nested as compact JSON. */
export function formatFieldValue(translate: TFunction, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return translate("tool.noValue");
  }
  if (typeof value === "boolean") {
    return translate(value ? "tool.yes" : "tool.no");
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (typeof value === "string") {
    return isoDateTimePattern.test(value) ? formatDateTime(value) || value : formatEnumToken(translate, value);
  }
  if (Array.isArray(value) && value.every(isScalar)) {
    return formatList(value.map((item) => formatFieldValue(translate, item)));
  }
  return JSON.stringify(value);
}
