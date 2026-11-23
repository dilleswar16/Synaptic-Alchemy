import { HeartPulse, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCreateActionItem } from "@/api/actionItemsApi";
import { useRunbookHealth, type RunbookFinding } from "@/api/knowledgeApi";
import { useAccessControl } from "@/auth/accessControl";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatusChip } from "@/components/ui/StatusChip";
import { ActionItemDialog } from "@/features/action-items/components/ActionItemDialog";

function findingText(finding: RunbookFinding, t: (key: string, options?: Record<string, unknown>) => string): string {
  return t(`health.finding.${finding.kind}`, { days: finding.parameters.days, incorrect: finding.parameters.incorrect, rated: finding.parameters.rated });
}

/** Which runbooks need attention and why, with the figures. Reads only; nothing here edits a runbook. */
export function RunbookHealthCard({ applicationId }: { applicationId: string }) {
  const { t } = useTranslation("knowledge");
  const { data } = useRunbookHealth(applicationId);
  const { canEdit } = useAccessControl();
  const create = useCreateActionItem();
  const [raising, setRaising] = useState<{ runbookId: string; title: string; details: string } | null>(null);
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
                <div className="flex items-center justify-between gap-3">
                  <p className="font-semibold text-default">{runbook.runbookTitle}</p>
                  {canEdit(applicationId) ? (
                    <Button size="sm" variant="secondary" leadingIcon={Plus} onClick={() => setRaising({ runbookId: runbook.runbookId, title: t("health.itemTitle", { runbook: runbook.runbookTitle }), details: runbook.findings.map((finding) => `- ${findingText(finding, t)}`).join("\n") })}>{t("health.createItem")}</Button>
                  ) : null}
                </div>
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
      <ActionItemDialog
        open={raising !== null}
        onOpenChange={(open) => { if (!open) setRaising(null); }}
        mode="create"
        applicationId={applicationId}
        preset={{ actionType: "prevent", itemTitle: raising?.title, itemDetailsMarkdown: raising?.details }}
        onSubmit={async (fields) => { if (raising) await create.mutateAsync({ applicationId, body: { ...fields, runbookId: raising.runbookId } }); }}
      />
    </Card>
  );
}
