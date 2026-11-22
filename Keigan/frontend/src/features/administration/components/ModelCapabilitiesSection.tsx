import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ConformanceReportSummary, ModelCapabilities } from "@/api/administrationApi";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDateTime, formatNumber } from "@/utils/formatters";

function ModelCard({ model }: { model: ModelCapabilities }) {
  const { t } = useTranslation("administration");
  const yesNo = (value: boolean) => t(value ? "settings.models.yes" : "settings.models.no");
  return (
    <Card dense className="flex flex-col gap-3 p-[var(--card-padding)]">
      <div className="min-w-0">
        <h3 className="text-body font-semibold text-default">{t(`settings.models.tiers.${model.modelTier}`)}</h3>
        <p className="truncate font-mono text-caption text-muted">{model.modelName}</p>
      </div>
      <KeyValueList dense items={[
        { key: "toolCalling", label: t("settings.models.toolCalling"), value: t(`settings.models.toolCallingValues.${model.toolCalling}`) },
        { key: "parallel", label: t("settings.models.parallelToolCalls"), value: yesNo(model.parallelToolCalls) },
        { key: "streamsText", label: t("settings.models.streamsText"), value: yesNo(model.streamsText) },
        { key: "streamsToolRequests", label: t("settings.models.streamsToolRequests"), value: yesNo(model.streamsToolRequests) },
        { key: "toolChoiceNone", label: t("settings.models.toolChoiceNone"), value: yesNo(model.supportsToolChoiceNone) },
        { key: "temperature", label: t("settings.models.temperature"), value: yesNo(model.supportsTemperature) },
        { key: "streamUsage", label: t("settings.models.streamUsage"), value: yesNo(model.reportsStreamUsage) },
        { key: "context", label: t("settings.models.context"), value: t("settings.models.tokens", { value: formatNumber(model.maxContextTokens) }) },
      ]} />
    </Card>
  );
}

function ConformanceReport({ report }: { report: ConformanceReportSummary | null }) {
  const { t } = useTranslation("administration");
  if (!report) return <p className="text-body-sm text-muted">{t("settings.conformance.none")}</p>;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={report.passed ? "success" : "warning"} size="sm">{t(report.passed ? "settings.conformance.passed" : "settings.conformance.failed")}</StatusChip>
        <span className="text-body-sm text-default">{t("settings.conformance.summary", { passed: report.passedCount, total: report.scenarioCount })}</span>
      </div>
      <p className="text-caption text-muted">
        {t("settings.conformance.model", { provider: report.providerName, model: report.modelName, mode: report.toolCallingMode })} · {t("settings.conformance.ran", { date: formatDateTime(report.generatedAt) })}
      </p>
    </div>
  );
}

/** What Keigan resolved for each configured AI model, and the last conformance run against a real model (read only). */
export function ModelCapabilitiesSection({ models, report }: { models: ModelCapabilities[]; report: ConformanceReportSummary | null }) {
  const { t } = useTranslation("administration");
  return (
    <Card>
      <CardHeader icon={Brain} iconTone="ai" title={t("settings.modelsTitle")} description={t("settings.modelsDescription")} />
      <CardBody className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{models.map((model) => <ModelCard key={model.modelTier} model={model} />)}</div>
        <section aria-labelledby="conformance-heading" className="flex flex-col gap-2">
          <h3 id="conformance-heading" className="text-body font-semibold text-default">{t("settings.conformance.title")}</h3>
          <ConformanceReport report={report} />
        </section>
      </CardBody>
    </Card>
  );
}
