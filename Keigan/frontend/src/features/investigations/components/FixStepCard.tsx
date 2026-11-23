import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FixAction, FixParameter, FixRisk, FixStepV2 } from "@/api/investigationsApi";
import { Badge } from "@/components/ui/Badge";
import type { StatusTone } from "@/components/ui/toneStyles";
import { cn } from "@/utils/cn";
import { FixCommandBlock } from "./FixCommandBlock";

const riskTones: Record<FixRisk, StatusTone> = { low: "success", medium: "warning", high: "danger" };

function ValueText({ parameter }: { parameter: FixParameter | null }) {
  const { t } = useTranslation("investigations");
  if (parameter === null || parameter.value === null) {
    return <span className="text-muted">{t("fix.valueNotKnown")}</span>;
  }
  return <span className={cn("font-mono", parameter.status === "assumed" && "rounded bg-warning-fill px-1 text-metlife-darkest-gray")} title={parameter.status === "assumed" ? t("fix.assumedValue") : undefined}>{parameter.value}</span>;
}

/** One action: what to do, the exact command or edit, why it was not shown, and what the person should see when it worked. */
function FixActionView({ action, label, stepRisk }: { action: FixAction; label: string | null; stepRisk: FixRisk }) {
  const { t } = useTranslation("investigations");
  const change = action.configurationChange;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-sm text-default">
        {label ? <span className="mr-1.5 font-semibold text-muted">{label}</span> : null}
        {action.description}
      </p>
      {action.command && action.withheldReason === null ? <FixCommandBlock command={action.command} riskLevel={action.riskLevel === "high" ? "high" : stepRisk === "high" ? "high" : action.riskLevel} /> : null}
      {change ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-md border border-hairline bg-surface-sunken px-3 py-2 text-body-sm">
          <dt className="text-muted">{t("fix.config.service")}</dt>
          <dd>{change.serviceName}{change.serviceInCatalogue ? null : <Badge tone="warning" className="ml-2">{t("fix.config.notInCatalogue")}</Badge>}</dd>
          <dt className="text-muted">{t("fix.config.setting")}</dt>
          <dd><ValueText parameter={change.settingName} /></dd>
          <dt className="text-muted">{t("fix.config.before")}</dt>
          <dd><ValueText parameter={change.beforeValue} /></dd>
          <dt className="text-muted">{t("fix.config.after")}</dt>
          <dd><ValueText parameter={change.afterValue} /></dd>
        </dl>
      ) : null}
      {change?.command && action.withheldReason === null ? <FixCommandBlock command={change.command} riskLevel={stepRisk} /> : null}
      {action.evidenceCode && action.withheldReason === null ? <p className="text-caption text-muted">{t("fix.rerunQuery", { code: action.evidenceCode })}</p> : null}
      {action.withheldReason ? (
        <p role="note" className="rounded-md border border-hairline bg-surface-sunken px-3 py-2 text-caption text-muted">{t(`fix.withheld.${action.withheldReason}`, { defaultValue: t("fix.withheld.unsafe_shell_syntax") })}</p>
      ) : null}
      {action.expectedResult ? <p className="text-caption text-muted"><span className="font-semibold">{t("fix.expected")}</span> {action.expectedResult}</p> : null}
    </div>
  );
}

/**
 * A checked fix step: its purpose and risk, what to do (a command with fill-in fields for the values Keigan did not have, or an edit, or words), how to see it worked and how to undo it.
 * Warnings are written by code. Keigan suggests; a person runs the command in their own tools.
 */
export function FixStepCard({ step, number, perspectiveLabel }: { step: FixStepV2; number: number; perspectiveLabel?: string }) {
  const { t } = useTranslation("investigations");
  return (
    <li className="flex flex-col gap-2.5 rounded-md border border-hairline px-3 py-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h6 className="text-body-sm font-semibold text-default"><span className="mr-1.5 text-muted">{number}.</span>{step.title}</h6>
        <Badge tone="neutral">{t(`fix.purpose.${step.purpose}`)}</Badge>
        <Badge tone={riskTones[step.riskLevel]}>{t(`fix.risk.${step.riskLevel}`)}</Badge>
        {perspectiveLabel ? <Badge tone="brand" variant="outline">{perspectiveLabel}</Badge> : null}
      </div>
      <FixActionView action={step.action} label={null} stepRisk={step.riskLevel} />
      {step.warnings.length > 0 ? (
        <ul className="flex flex-col gap-0.5">
          {step.warnings.map((warning) => (
            <li key={warning} className="flex items-center gap-1.5 text-caption font-semibold text-warning"><TriangleAlert aria-hidden="true" size={13} />{t(`fix.warning.${warning}`, { defaultValue: warning })}</li>
          ))}
        </ul>
      ) : null}
      {step.assumptions.length > 0 ? (
        <div>
          <p className="text-caption font-semibold text-muted">{t("fix.assumptions")}</p>
          <ul className="list-disc space-y-0.5 pl-5 text-caption text-muted">{step.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
        </div>
      ) : null}
      {step.check ? <FixActionView action={step.check} label={t("fix.check")} stepRisk="low" /> : null}
      {step.revert ? <FixActionView action={step.revert} label={t("fix.undo")} stepRisk="low" /> : null}
    </li>
  );
}
