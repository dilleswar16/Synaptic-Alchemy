import { useId, useState, type ReactNode } from "react";
import { ShieldCheck, ShieldExclamationPoint, TriangleExclamationPoint } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { CopyButton } from "./CopyButton";

export type CommandRiskLevel = "low" | "medium" | "high";

export interface CommandVariant {
  key: string;
  /** Tab label: "Azure CLI", "PowerShell", "Terraform", "Portal", "KQL". */
  label: string;
  content: string;
}

export interface CommandBlockProps {
  /** One command (string) or several variants shown as tabs. */
  commands: string | CommandVariant[];
  title?: ReactNode;
  riskLevel?: CommandRiskLevel;
  defaultCommandKey?: string;
  /** Wrap long lines instead of scrolling horizontally. */
  wrapLines?: boolean;
  /** Maximum body height before it scrolls (CSS length). */
  maximumHeight?: string;
  className?: string;
}

const riskStyles: Record<CommandRiskLevel, { className: string; icon: typeof ShieldCheck }> = {
  low: { className: "bg-[rgba(164,206,78,0.16)] text-[#B6DA6E]", icon: ShieldCheck },
  medium: { className: "bg-[rgba(255,198,0,0.16)] text-[#FFD54D]", icon: ShieldExclamationPoint },
  high: { className: "bg-[rgba(212,33,35,0.22)] text-[#FF8A8C]", icon: TriangleExclamationPoint },
};

/**
 * Dark code surface (#0F1B27, mono 13.5) for commands Keigan suggests — never runs. Tabs per tool, copy with
 * "Copied" state, risk pill (high risk reads "confirm with change process").
 */
export function CommandBlock({ commands, title, riskLevel, defaultCommandKey, wrapLines = false, maximumHeight = "420px", className }: CommandBlockProps) {
  const { t } = useTranslation("common");
  const tabIdPrefix = useId();
  const commandVariants: CommandVariant[] = typeof commands === "string" ? [{ key: "command", label: "", content: commands }] : commands;
  const [activeCommandKey, setActiveCommandKey] = useState(defaultCommandKey ?? commandVariants[0]?.key ?? "");
  const activeCommand = commandVariants.find((commandVariant) => commandVariant.key === activeCommandKey) ?? commandVariants[0];
  const hasTabs = commandVariants.length > 1;
  const riskStyle = riskLevel ? riskStyles[riskLevel] : null;
  const RiskIcon = riskStyle?.icon;

  return (
    <div className={cn("overflow-hidden rounded-md border border-[#1E3044] bg-[#0F1B27] text-[#E7EDF3] shadow-xs", className)}>
      <div className="flex min-h-11 items-center gap-3 border-b border-white/8 pr-2 pl-3">
        {title ? <span className="shrink-0 text-caption font-semibold text-white/80">{title}</span> : null}
        {hasTabs ? (
          <div role="tablist" aria-label={t("commandBlock.label")} className="scrollbar-none flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {commandVariants.map((commandVariant) => {
              const isActive = commandVariant.key === activeCommand?.key;
              return (
                <button
                  key={commandVariant.key}
                  type="button"
                  role="tab"
                  id={`${tabIdPrefix}-tab-${commandVariant.key}`}
                  aria-selected={isActive}
                  aria-controls={`${tabIdPrefix}-panel`}
                  onClick={() => setActiveCommandKey(commandVariant.key)}
                  className={cn(
                    "h-7 shrink-0 rounded-xs px-2.5 text-caption font-medium transition-colors",
                    isActive ? "bg-white/12 text-white" : "text-white/60 hover:bg-white/6 hover:text-white/90",
                  )}
                >
                  {commandVariant.label}
                </button>
              );
            })}
          </div>
        ) : (
          <span className="flex-1" />
        )}
        {riskLevel && riskStyle && RiskIcon ? (
          <span className={cn("inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-micro", riskStyle.className)}>
            <RiskIcon aria-hidden="true" size={13} strokeWidth={2.25} />
            {t(`risk.${riskLevel}`)}
          </span>
        ) : null}
        <CopyButton value={() => activeCommand?.content ?? ""} label={t("commandBlock.copyCommand")} variant="onDark" />
      </div>
      <pre
        id={`${tabIdPrefix}-panel`}
        role={hasTabs ? "tabpanel" : undefined}
        aria-labelledby={hasTabs && activeCommand ? `${tabIdPrefix}-tab-${activeCommand.key}` : undefined}
        tabIndex={0}
        style={{ maxHeight: maximumHeight }}
        className={cn(
          "overflow-auto px-4 py-3.5 font-mono text-code text-[#E7EDF3] focus-visible:outline-offset-[-3px]",
          wrapLines ? "break-words whitespace-pre-wrap" : "whitespace-pre",
        )}
      >
        <code>{activeCommand?.content}</code>
      </pre>
    </div>
  );
}
