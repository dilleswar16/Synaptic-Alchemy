import { useTranslation } from "react-i18next";
import type { AlertGroupingReason } from "@/api/alertsApi";
import { cn } from "@/utils/cn";

/** The plain sentence saying why a group's alerts belong together. The server sends a code with the names and numbers; the words come from the locale files, and a code this screen does not know yet reads as "not recorded". */
export function GroupingReasonText({ reason, className }: { reason: AlertGroupingReason; className?: string }) {
  const { t } = useTranslation("alerts");
  const sentence: string = t(`groupingReason.${reason.code}`, { ...reason.parameters, defaultValue: t("groupingReason.not_recorded") });
  return <p className={cn("text-muted", className)}>{sentence}</p>;
}
