import { useMemo } from "react";
import { Gauge, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { InvestigationDetail } from "@/api/investigationsApi";
import { TopologyGraph, type TopologyImpactLevel } from "@/components/topology/TopologyGraph";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { useRelationshipLabel } from "@/components/topology/useRelationshipLabel";
import { communicationLanguageLabel, topologyNodeType } from "./investigationPresentation";

const sloTone: Record<string, StatusTone> = { healthy: "success", at_risk: "warning", breached: "danger", no_data: "neutral" };

/** Mini topology with directly and indirectly impacted services, the impact narrative, impacted SLOs and stakeholders. */
export function BlastRadiusSection({ detail }: { detail: InvestigationDetail }) {
  const { t } = useTranslation("investigations");
  const { t: translateNotifications } = useTranslation("notifications");
  const relationshipLabel = useRelationshipLabel();
  const blastRadius = detail.blastRadius;
  const graph = useMemo(() => {
    if (!blastRadius) return null;
    const highlighted: Record<string, TopologyImpactLevel> = {};
    for (const node of blastRadius.nodes) {
      if (node.impactLevel === "direct" || node.impactLevel === "indirect") highlighted[node.serviceId] = node.impactLevel;
    }
    return {
      nodes: blastRadius.nodes.map((node) => ({ key: node.serviceId, name: node.serviceName, type: topologyNodeType(node.serviceType), subtitle: t(`blast.impact.${node.impactLevel}`) })),
      edges: blastRadius.edges.map((edge) => ({ source: edge.fromServiceId, target: edge.toServiceId, label: relationshipLabel(edge.kind) })),
      highlighted,
    };
  }, [blastRadius, t]);

  if (!blastRadius || !graph) return <EmptyState title={t("blast.emptyTitle")} description={t("blast.emptyDescription")} isBordered />;
  const directNames = blastRadius.nodes.filter((node) => node.impactLevel === "direct").map((node) => node.serviceName);
  const atRiskSlos = blastRadius.impactedSlos.filter((slo) => slo.status !== "healthy");
  const healthySloCount = blastRadius.impactedSlos.length - atRiskSlos.length;
  const indirectNames = blastRadius.nodes.filter((node) => node.impactLevel === "indirect").map((node) => node.serviceName);
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader title={t("blast.graphTitle")} description={t("blast.graphDescription")} actions={<AiGeneratedChip size="sm" modelName={detail.modelNames.join(", ") || null} />} />
        <CardBody className="flex flex-col gap-4">
          <TopologyGraph nodes={graph.nodes} edges={graph.edges} highlightedNodeKeys={graph.highlighted} height={440} showMiniMap={false} legendPlacement="below" />
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-body-sm">
            <p><Badge tone="danger">{t("blast.impact.direct")}</Badge> <span className="ml-1 text-muted">{directNames.join(", ") || t("blast.none")}</span></p>
            <p><Badge tone="alert">{t("blast.impact.indirect")}</Badge> <span className="ml-1 text-muted">{indirectNames.join(", ") || t("blast.none")}</span></p>
          </div>
        </CardBody>
      </Card>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title={t("blast.narrativeTitle")} />
          <CardBody className="flex flex-col gap-3">
            {blastRadius.userImpactSummary ? <p className="text-body font-medium text-default">{blastRadius.userImpactSummary}</p> : null}
            <MarkdownView content={blastRadius.narrativeMarkdown ?? ""} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader icon={Gauge} iconTone="warning" title={t("blast.slosTitle")} />
          <CardBody>
            {atRiskSlos.length === 0 ? (
              <p className="text-body-sm text-muted">{t("blast.noSlos")}</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {atRiskSlos.map((slo, sloIndex) => (
                  <li key={String(slo.sloId ?? sloIndex)} className="flex items-center justify-between gap-3">
                    <span className="text-body-sm text-default">{String(slo.sliName ?? t("blast.sloFallback"))}</span>
                    <StatusChip tone={sloTone[String(slo.status)] ?? "neutral"} size="sm">{t(`blast.sloStatus.${String(slo.status)}`, { defaultValue: String(slo.status ?? "") })}</StatusChip>
                  </li>
                ))}
              </ul>
            )}
            {healthySloCount > 0 ? <p className="mt-3 border-t border-hairline pt-3 text-caption text-muted">{t("blast.healthySlos", { count: healthySloCount })}</p> : null}
          </CardBody>
        </Card>
        <Card>
          <CardHeader icon={Users} iconTone="info" title={t("blast.stakeholdersTitle")} />
          <CardBody>
            {blastRadius.stakeholders.length === 0 ? (
              <p className="text-body-sm text-muted">{t("blast.noStakeholders")}</p>
            ) : (
              <ul className="flex flex-col gap-2.5">
                {blastRadius.stakeholders.map((stakeholder) => (
                  <li key={stakeholder.displayName} className="flex items-center justify-between gap-3 text-body-sm">
                    <span className="text-default">{stakeholder.displayName}</span>
                    <span className="text-caption text-muted">{translateNotifications(`roles.${stakeholder.role}`, { defaultValue: stakeholder.role })} · {communicationLanguageLabel(stakeholder.preferredLanguageCode)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
