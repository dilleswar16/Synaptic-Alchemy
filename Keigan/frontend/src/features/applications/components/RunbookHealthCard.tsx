import { HeartPulse } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useRunbookHealth, type RunbookFinding } from "@/api/knowledgeApi";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatusChip } from "@/components/ui/StatusChip";

function findingText(finding: RunbookFinding, t: (key: string, options?: Record<string, unknown>) => string): string {
  return t(`health.finding.${finding.kind}`, { days: finding.parameters.days, incorrect: finding.parameters.incorrect, rated: finding.parameters.rated });
}

/** Which runbooks need attention and why, with the figures. Reads only; nothing here edits a runbook. */
export function RunbookHealthCard({ applicationId }: { applicationId: string }) {
  const { t } = useTranslation("knowledge");
  const { data } = useRunbookHealth(applicationId);
  if (!data || data.runbookCount === 0) return null;
  const flagged = data.runbooks.filter((runbook) => runbook.findings.length > 0);
  return (
    <Card radius="lg">
      <CardHeader
        title={t("health.title")}
        description={flagged.length === 0 ? t("health.allFine", { count: data.runbookCount }) : t("health.summary", { count: flagged.length, total: data.runbookCount })}
        actions={<HeartPulse size={18} aria-hidden className="text-muted" />}
      />
      {flagged.length > 0 ? (
        <CardBody>
          <ul className="flex flex-col divide-y divide-hairline">
            {flagged.map((runbook) => (
              <li key={runbook.runbookId} className="flex flex-col gap-1.5 py-3">
                <p className="font-semibold text-default">{runbook.runbookTitle}</p>
                <div className="flex flex-wrap gap-2">
                  {runbook.findings.map((finding) => <StatusChip key={finding.kind} tone={finding.kind === "often_wrong" ? "warning" : "neutral"} size="sm">{t(`health.kind.${finding.kind}`)}</StatusChip>)}
                </div>
                <ul className="text-body-sm text-muted">
                  {runbook.findings.map((finding) => <li key={finding.kind}>{findingText(finding, t)}</li>)}
                </ul>
              </li>
            ))}
          </ul>
        </CardBody>
      ) : null}
    </Card>
  );
}
