import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { RecordReference } from "@/api/askKeiganApi";
import { buttonClassName } from "@/components/ui/Button";
import { firstRecordLink } from "./toolRecordLinks";

/** "Open in Keigan": the page of the first record the tool read. Renders nothing when no record of the call has a page. */
export function ToolRecordLink({ records }: { records: readonly RecordReference[] }) {
  const { t } = useTranslation("chat");
  const link = firstRecordLink(records);
  if (!link) {
    return null;
  }
  return (
    // The name starts with the visible words (WCAG 2.5.3 label in name) and then says which record the link is about.
    <Link to={link.path} aria-label={t("tool.openInKeiganNamed", { label: link.record.label })} className={buttonClassName("secondary", "sm")}>
      <ExternalLink aria-hidden="true" size={16} strokeWidth={1.75} />
      {t("tool.openInKeigan")}
    </Link>
  );
}
