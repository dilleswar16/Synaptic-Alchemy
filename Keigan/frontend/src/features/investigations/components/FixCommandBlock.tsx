import { useId, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FixCommand, FixParameter, FixRendering, FixRisk } from "@/api/investigationsApi";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { copyTextToClipboard } from "@/components/ui/CopyButton";
import { cn } from "@/utils/cn";
import { composeCommand } from "./fixCommandComposer";

/** The shells a command reads the same in are shown once; tabs appear only when the text really differs. */
function distinctRenderings(renderings: FixRendering[]): FixRendering[] {
  const seen = new Set<string>();
  return renderings.filter((rendering) => {
    const key = JSON.stringify(rendering.segments);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

const dialectLabels = { bash: "Bash", powershell: "PowerShell" } as const;

/** `not_found_in_E3` is one message with the code filled in. */
function reasonParts(reason: string): { key: string; code: string | undefined } {
  const match = /^not_found_in_(E\d+)$/.exec(reason);
  return match ? { key: "not_found_in_evidence", code: match[1] } : { key: reason, code: undefined };
}

function GapInput({ parameter, value, onChange, hasProblem }: { parameter: FixParameter; value: string; onChange: (value: string) => void; hasProblem: boolean }) {
  const { t } = useTranslation("investigations");
  const label = t(`fix.kind.${parameter.labelKey ?? parameter.valueKind}`, { defaultValue: parameter.valueKind });
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={label}
      aria-label={t("fix.fillInLabel", { label })}
      aria-invalid={hasProblem || undefined}
      maxLength={parameter.maximumLength ?? undefined}
      size={Math.max(label.length, value.length + 1, 8)}
      spellCheck={false}
      autoCapitalize="off"
      autoComplete="off"
      className={cn(
        "mx-0.5 rounded border bg-[#16283A] px-1.5 py-0.5 font-mono text-code text-[#E7EDF3] placeholder:text-[#8FA3B8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#6EB1FF]",
        hasProblem ? "border-[#FF8A8C]" : "border-[#35506B]",
      )}
    />
  );
}

/**
 * A suggested command as Keigan's code rendered it. A value Keigan did not have is an input in the command, never a placeholder in the text; copy stays disabled until every input holds a valid
 * value of its kind (checked with the server's own patterns). A value Keigan assumed is highlighted with the reason. A high-risk command asks for confirmation before it is copied. Keigan never runs it.
 */
export function FixCommandBlock({ command, riskLevel }: { command: FixCommand; riskLevel: FixRisk }) {
  const { t } = useTranslation("investigations");
  const identifier = useId();
  const renderings = distinctRenderings(command.renderings);
  const [activeDialect, setActiveDialect] = useState<string | undefined>(undefined);
  const [entered, setEntered] = useState<Record<string, string>>({});
  const [isConfirming, setIsConfirming] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const active = renderings.find((rendering) => rendering.dialect === activeDialect) ?? renderings[0];
  if (!active) {
    return null;
  }
  const parameterByName = new Map(command.parameters.map((parameter) => [parameter.name, parameter]));
  const result = composeCommand(active.segments, command.parameters, entered);
  const problemNames = new Set(result.kind === "invalid" ? result.problems.map((problem) => problem.parameterName) : result.kind === "not_insertable" ? [result.parameterName] : []);
  const labelOf = (name: string) => {
    const parameter = parameterByName.get(name);
    return t(`fix.kind.${parameter?.labelKey ?? parameter?.valueKind ?? ""}`, { defaultValue: name });
  };

  const copy = async () => {
    if (result.kind !== "ready" && active.text === null) {
      return;
    }
    const text = result.kind === "ready" ? result.text : (active.text ?? "");
    if (await copyTextToClipboard(text)) {
      setIsCopied(true);
      window.setTimeout(() => setIsCopied(false), 2000);
    }
  };
  const canCopy = result.kind === "ready";

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-md border border-[#1E3044] bg-[#0F1B27] text-[#E7EDF3] shadow-xs">
        {renderings.length > 1 ? (
          <div role="tablist" aria-label={t("fix.shell")} className="flex gap-1 border-b border-white/10 px-2 pt-1.5">
            {renderings.map((rendering) => (
              <button
                key={rendering.dialect}
                type="button"
                role="tab"
                id={`${identifier}-${rendering.dialect}`}
                aria-selected={rendering.dialect === active.dialect}
                onClick={() => setActiveDialect(rendering.dialect)}
                className={cn("rounded-t px-2.5 py-1 text-caption font-medium", rendering.dialect === active.dialect ? "bg-white/10 text-white" : "text-[#9FB3C8] hover:text-white")}
              >
                {dialectLabels[rendering.dialect]}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex items-start">
          <p role="group" aria-labelledby={renderings.length > 1 ? `${identifier}-${active.dialect}` : undefined} className="min-w-0 flex-1 px-4 py-3.5 font-mono text-code leading-8 break-words whitespace-pre-wrap">
            {active.segments.map((segment, position) => {
              if (segment.kind === "missing_value") {
                const parameter = parameterByName.get(segment.parameterName ?? "");
                return parameter ? (
                  <GapInput
                    key={position}
                    parameter={parameter}
                    value={entered[parameter.name] ?? ""}
                    onChange={(value) => setEntered((current) => ({ ...current, [parameter.name]: value }))}
                    hasProblem={problemNames.has(parameter.name)}
                  />
                ) : null;
              }
              if (segment.kind === "assumed_value") {
                const { key, code } = reasonParts(parameterByName.get(segment.parameterName ?? "")?.statusReason ?? "source_not_stated");
                return <span key={position} title={t("fix.assumedReason", { reason: t(`fix.reason.${key}`, { code, defaultValue: key }) })} className="rounded bg-[rgba(255,198,0,0.18)] px-0.5 text-[#FFD54D] underline decoration-dotted underline-offset-4">{segment.text}</span>;
              }
              return <span key={position}>{segment.text}</span>;
            })}
          </p>
          <div className="shrink-0 border-l border-white/8 p-1.5">
            <button
              type="button"
              disabled={!canCopy}
              onClick={() => (riskLevel === "high" ? setIsConfirming(true) : void copy())}
              aria-label={canCopy ? t("fix.copy") : t("fix.copyDisabled")}
              className="grid size-9 place-items-center rounded text-[#C9D6E3] hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isCopied ? <Check aria-hidden="true" size={16} /> : <Copy aria-hidden="true" size={16} />}
            </button>
            <span role="status" className="sr-only">{isCopied ? t("fix.copied") : ""}</span>
          </div>
        </div>
      </div>
      {result.kind === "incomplete" ? <p className="text-caption text-muted">{t("fix.fillIn", { count: result.missing.length })}</p> : null}
      {result.kind === "invalid" ? (
        <ul className="flex flex-col gap-0.5 text-caption text-danger">
          {result.problems.map((problem) => <li key={problem.parameterName}>{t(`fix.problem.${problem.problem}`, { label: labelOf(problem.parameterName) })}</li>)}
        </ul>
      ) : null}
      {result.kind === "not_insertable" ? <p className="text-caption text-danger">{t("fix.problem.not_insertable", { label: labelOf(result.parameterName) })}</p> : null}
      <ConfirmDialog
        open={isConfirming}
        onOpenChange={setIsConfirming}
        title={t("fix.confirm.title")}
        description={t("fix.confirm.description")}
        confirmLabel={t("fix.confirm.copy")}
        onConfirm={copy}
      />
    </div>
  );
}
