import { CircleSlash } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { MarkdownView } from "@/components/ui/MarkdownView";

/** The explanations the evidence ruled out, each with its reason (nothing when none were ruled out). */
export function RuledOutCard({ detail }: { detail: InvestigationDetail }) {
  const { t } = useTranslation("investigations");
  const ruledOut = detail.hypotheses.filter((hypothesis) => hypothesis.state === "ruled_out");
  if (ruledOut.length === 0) return null;
  return (
    <Card>
      <CardHeader icon={CircleSlash} iconTone="neutral" title={t("ruledOut.title")} description={t("ruledOut.description")} />
      <CardBody>
        <ul className="flex flex-col gap-3">
          {ruledOut.map((hypothesis) => (
            <li key={hypothesis.hypothesisId} className="flex flex-col gap-1">
              <span className="text-body font-semibold text-default">{t(`perspective.${hypothesis.analysisPerspective}`)}: {hypothesis.hypothesisTitle}</span>
              {hypothesis.stateReasonMarkdown ? <MarkdownView content={hypothesis.stateReasonMarkdown} /> : null}
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
