import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatMessagePayload } from "@/api/chatApi";
import { ChartMessage } from "@/components/chat/ChartMessage";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { CommandBlock } from "@/components/ui/CommandBlock";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { cn } from "@/utils/cn";
import { formatDateTime } from "@/utils/formatters";

export interface ChatMessageViewProps {
  role: "user" | "assistant";
  text: string;
  /** Structured answer (chart, query details, citations) of a message stored before Ask Keigan. */
  payload?: ChatMessagePayload | null;
  /** Smaller type and no mark column, for the floating investigation panel. */
  isCompact?: boolean;
  className?: string;
}

/** One chat turn: user bubble on the right; Keigan prose on the left with the mark, optional chart, "How I got this" and citations. */
export function ChatMessageView({ role, text, payload, isCompact = false, className }: ChatMessageViewProps) {
  const { t } = useTranslation("chat");
  const { t: translateOnboarding } = useTranslation("onboarding");
  const [isQueryOpen, setIsQueryOpen] = useState(false);
  if (role === "user") {
    return <div className={cn("ml-10 max-w-[85%] self-end rounded-lg rounded-br-xs bg-action-subtle px-3.5 py-2.5 text-body-sm whitespace-pre-wrap text-action-subtle-text", className)}>{text}</div>;
  }
  const queryDetails = payload?.queryDetails;
  return (
    <div className={cn("flex max-w-full items-start gap-3 self-start", className)}>
      {isCompact ? null : <KeiganLogo variant="mark" size={26} className="mt-0.5 shrink-0" />}
      <div className={cn("flex min-w-0 flex-1 flex-col gap-3", isCompact ? "" : "border-l-2 border-hairline pl-4")}>
        <MarkdownView content={text} />
        {payload?.chartSpecification ? <ChartMessage specification={payload.chartSpecification} /> : null}
        {payload?.citations?.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-caption text-muted">{t("message.sources")}</span>
            {payload.citations.map((citation) => <EvidenceChip key={citation.reference} code={citation.reference} title={citation.title} />)}
          </div>
        ) : null}
        {queryDetails ? (
          <div className="text-body-sm">
            <button type="button" onClick={() => setIsQueryOpen((value) => !value)} aria-expanded={isQueryOpen} className="inline-flex items-center gap-1 rounded-sm text-muted hover:text-default focus-visible:outline-2">
              <ChevronRight size={14} className={cn("transition-transform", isQueryOpen && "rotate-90")} aria-hidden />
              {t("message.howIGotThis")}
            </button>
            {isQueryOpen ? (
              <div className="mt-2 flex flex-col gap-2">
                <p className="text-caption text-muted">
                  {t("message.queryMeta", { service: queryDetails.serviceName, source: translateOnboarding(`logSource.kinds.${queryDetails.sourceKind}`, { defaultValue: queryDetails.sourceKind }), language: queryDetails.queryLanguage.toUpperCase(), count: queryDetails.rowCount })}
                  {queryDetails.timeRange ? ` · ${formatDateTime(queryDetails.timeRange.start)} – ${formatDateTime(queryDetails.timeRange.end)}` : ""}
                  {queryDetails.isSimulated ? ` · ${t("message.simulated")}` : ""}
                </p>
                <CommandBlock commands={queryDetails.queryText} maximumHeight="240px" wrapLines />
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
