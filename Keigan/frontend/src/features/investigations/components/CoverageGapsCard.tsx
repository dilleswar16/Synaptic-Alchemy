import { EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CoverageGap } from "@/api/investigationsApi";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";

function stringParameter(gap: CoverageGap, name: string): string | undefined {
  const value = gap.parameters[name];
  return typeof value === "string" || typeof value === "number" ? String(value) : undefined;
}

/** What Keigan could not check: sources it could not read, services with no telemetry and limits that cut a check. A check that was not made is never shown as healthy. */
export function CoverageGapsCard({ gaps }: { gaps: CoverageGap[] }) {
  const { t } = useTranslation("investigations");
  const serviceNames = gaps.find((gap) => Array.isArray(gap.parameters.serviceNames))?.parameters.serviceNames;
  return (
    <Card>
      <CardHeader icon={EyeOff} iconTone="warning" title={t("coverage.title")} description={t("coverage.description")} />
      <CardBody className="flex flex-col gap-3">
        {gaps.length === 0 ? (
          <p className="text-body text-default">{t("coverage.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-2 text-body">
            {gaps.map((gap) => (
              <li key={gap.coverageGapId} className="flex flex-col gap-0.5">
                <span>
                  {t(`coverage.kind.${gap.gapKind}`, {
                    service: gap.serviceName ?? "",
                    source: gap.sourceKind ?? "",
                    count: stringParameter(gap, "count"),
                    limit: stringParameter(gap, "limit"),
                    perspective: stringParameter(gap, "perspective") ? t(`perspective.${stringParameter(gap, "perspective")}`) : "",
                    services: Array.isArray(gap.parameters.serviceNames) ? (gap.parameters.serviceNames as string[]).join(", ") : serviceNames,
                  })}
                  {gap.reasonCode ? `: ${t(`coverage.reason.${gap.reasonCode}`)}` : ""}.
                </span>
                {gap.legacyEvidenceCode ? <span className="text-caption text-muted">{t("coverage.legacyEvidence", { code: gap.legacyEvidenceCode })}</span> : null}
              </li>
            ))}
          </ul>
        )}
        <p className="border-t border-hairline pt-3 text-caption text-muted">{t("coverage.footnote")}</p>
      </CardBody>
    </Card>
  );
}
