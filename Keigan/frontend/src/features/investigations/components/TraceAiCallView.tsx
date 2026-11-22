import { useTranslation } from "react-i18next";
import type { TraceAiCall } from "@/api/investigationsApi";
import { Button } from "@/components/ui/Button";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatNumber } from "@/utils/formatters";

const shortHash = (hash: string | null) => (hash ? hash.slice(0, 12) : "—");

/** One AI call of the trace: the prompt and its hashes, the attempts, what went in (by reference and hash, never the text) and what Keigan's own checks changed. */
export function TraceAiCallView({ call, canSeeRawOutput, onShowRawOutput }: { call: TraceAiCall; canSeeRawOutput: boolean; onShowRawOutput: () => void }) {
  const { t } = useTranslation("investigations");
  const adjustmentText = (code: string, parameters: Record<string, unknown>) =>
    t(`trace.adjustment.${code}`, { ...parameters, codes: Array.isArray(parameters.codes) ? (parameters.codes as string[]).join(", ") : undefined });
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid gap-x-6 gap-y-2 text-body-sm sm:grid-cols-2">
        <div><dt className="text-caption text-muted">{t("trace.aiCall.prompt")}</dt><dd className="font-mono">{call.promptKey} · {t("trace.aiCall.version")} {call.promptVersion}</dd></div>
        <div><dt className="text-caption text-muted">{t("trace.aiCall.model")}</dt><dd className="font-mono">{call.providerName} · {call.modelName} · {call.modelTier}</dd></div>
        <div><dt className="text-caption text-muted">{t("trace.aiCall.templateHash")}</dt><dd className="font-mono" title={call.promptTemplateSha256 ?? undefined}>{shortHash(call.promptTemplateSha256)}</dd></div>
        <div><dt className="text-caption text-muted">{t("trace.aiCall.systemHash")}</dt><dd className="font-mono" title={call.systemPromptSha256 ?? undefined}>{shortHash(call.systemPromptSha256)}</dd></div>
      </dl>
      {call.failureCode ? <p className="text-body-sm text-danger">{t("trace.aiCall.failedWith", { reason: t(`trace.failure.${call.failureCode}`) })}</p> : null}
      {call.attempts.length > 0 ? (
        <div>
          <h5 className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted">{t("trace.aiCall.attempts")}</h5>
          <ul className="list-disc space-y-0.5 pl-5 text-body-sm">
            {call.attempts.map((attempt, index) => (
              <li key={index}>{t("trace.aiCall.attemptRow", { status: attempt.outcomeStatus, milliseconds: formatNumber(attempt.latencyMilliseconds), input: formatNumber(attempt.inputTokenCount), output: formatNumber(attempt.outputTokenCount) })}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {call.inputSections.length > 0 ? (
        <div>
          <h5 className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted">{t("trace.aiCall.inputs")}</h5>
          <ul className="flex flex-col gap-2">
            {call.inputSections.map((section) => (
              <li key={section.title} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-hairline px-3 py-2 text-body-sm">
                <span className="font-semibold text-default">{section.title}</span>
                <StatusChip tone={section.isUntrusted ? "warning" : "neutral"} size="sm" variant="outline">{section.isUntrusted ? t("trace.aiCall.untrusted") : t("trace.aiCall.trusted")}</StatusChip>
                <span className="text-muted">{t("trace.aiCall.characters", { sent: formatNumber(section.sentCharacterCount), total: formatNumber(section.characterCount) })}{section.isTruncated ? ` · ${t("trace.aiCall.cut")}` : ""}</span>
                <span className="font-mono text-caption text-muted" title={section.sha256}>{shortHash(section.sha256)}</span>
                {section.citationCodes.length > 0 ? <span className="font-mono text-caption">{section.citationCodes.join(" ")}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div>
        <h5 className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted">{t("trace.aiCall.adjustments")}</h5>
        {call.adjustments.length === 0 ? (
          <p className="text-body-sm text-muted">{t("trace.aiCall.nothingChanged")}</p>
        ) : (
          <ul className="list-disc space-y-0.5 pl-5 text-body-sm">{call.adjustments.map((adjustment, index) => <li key={index}>{adjustmentText(adjustment.code, adjustment.parameters)}</li>)}</ul>
        )}
      </div>
      {call.hasRawOutput ? (
        canSeeRawOutput ? <div><Button variant="secondary" size="sm" onClick={onShowRawOutput}>{t("trace.aiCall.rawAnswer")}</Button></div>
        : <p className="text-caption text-muted">{t("trace.aiCall.rawAdminsOnly")}</p>
      ) : null}
    </div>
  );
}
