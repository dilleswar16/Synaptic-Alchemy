import { useMemo, useState } from "react";
import { Check, MessageSquareWarning, Network, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBuildTopology, useReviewTopology, useTopology, type ReviewVerdict, type TopologyDetail, type TopologyEdge, type TopologyNode } from "@/api/knowledgeApi";
import { AiGeneratedChip } from "@/components/ui/AiGeneratedChip";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { MarkdownView } from "@/components/ui/MarkdownView";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";
import { TopologyGraph, type TopologyGraphNode } from "@/components/topology/TopologyGraph";
import { useRelationshipLabel } from "@/components/topology/useRelationshipLabel";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

/** Maps a topology node to the graph kit's icon types using what the builder knows about it. */
function graphType(node: TopologyNode): string {
  const technology = (node.technology ?? "").toLowerCase();
  if (node.nodeType === "data_store") return "database";
  if (node.nodeType === "client") return "users";
  if (["external", "hardware", "mainframe", "saas", "queue"].includes(node.nodeType)) return node.nodeType;
  if (technology.includes("aks")) return "aks";
  if (technology.includes("function")) return "functions";
  if (technology.includes("app service")) return "app_service";
  if (technology.includes("logic")) return "logic_apps";
  if (technology.includes("api management")) return "api_management";
  if (technology.includes("data factory")) return "data_factory";
  if (technology.includes("sql")) return "database";
  return "service";
}

const verdictTones = { looks_right: "success", needs_correction: "warning", comment: "info" } as const;

interface ReviewPanelProps {
  title: string;
  subtitle?: string;
  verdict: ReviewVerdict | null;
  comment: string | null;
  canEdit: boolean;
  isSaving: boolean;
  onReview: (verdict: ReviewVerdict, comment?: string) => void;
}

/** Stakeholders review, not approve: "Looks right" or "Needs correction" with a comment that feeds the next build. */
function ReviewPanel({ title, subtitle, verdict, comment, canEdit, isSaving, onReview }: ReviewPanelProps) {
  const { t } = useTranslation("knowledge");
  const [draft, setDraft] = useState("");
  const [isCorrecting, setIsCorrecting] = useState(false);
  return (
    <Card dense className="flex flex-col gap-3 p-[var(--card-padding)]">
      <div>
        <h4 className="text-body font-semibold">{title}</h4>
        {subtitle ? <p className="text-caption text-muted">{subtitle}</p> : null}
      </div>
      {verdict ? (
        <div className="flex flex-col gap-1">
          <StatusChip size="sm" tone={verdictTones[verdict]} className="self-start">{t(`topology.verdicts.${verdict}`)}</StatusChip>
          {comment ? <p className="text-body-sm text-muted">{comment}</p> : null}
        </div>
      ) : null}
      {canEdit ? (
        isCorrecting ? (
          <div className="flex flex-col gap-2">
            <Textarea aria-label={t("topology.correctionLabel")} placeholder={t("topology.correctionPlaceholder")} rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" isLoading={isSaving} disabled={!draft.trim()} onClick={() => { onReview("needs_correction", draft.trim()); setDraft(""); setIsCorrecting(false); }}>{t("topology.sendCorrection")}</Button>
              <Button size="sm" variant="ghost" onClick={() => setIsCorrecting(false)}>{t("topology.cancel")}</Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" leadingIcon={Check} isLoading={isSaving} onClick={() => onReview("looks_right")}>{t("topology.looksRight")}</Button>
            <Button size="sm" variant="secondary" leadingIcon={MessageSquareWarning} onClick={() => setIsCorrecting(true)}>{t("topology.needsCorrection")}</Button>
          </div>
        )
      ) : null}
    </Card>
  );
}

function TopologyView({ applicationId, topology, canEdit }: { applicationId: string; topology: TopologyDetail; canEdit: boolean }) {
  const { t } = useTranslation("knowledge");
  const relationshipLabel = useRelationshipLabel();
  const review = useReviewTopology(applicationId);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [edgeToCorrect, setEdgeToCorrect] = useState<TopologyEdge | null>(null);
  const [edgeCorrection, setEdgeCorrection] = useState("");
  const nodeByKey = useMemo(() => new Map(topology.nodes.map((node) => [node.nodeKey, node])), [topology.nodes]);
  const graphNodes = useMemo<TopologyGraphNode[]>(() => topology.nodes.map((node) => ({ key: node.nodeKey, name: node.label, type: graphType(node), subtitle: node.technology ?? undefined })), [topology.nodes]);
  const selectedNode = selectedKey ? nodeByKey.get(selectedKey) : undefined;
  const sendReview = (targetElementKey: string | undefined, verdict: ReviewVerdict, comment?: string) =>
    review.mutate({ topologyId: topology.topologyId, targetElementKey, reviewVerdict: verdict, reviewCommentText: comment });
  const labelOf = (key: string) => nodeByKey.get(key)?.label ?? key;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card radius="lg" className="overflow-hidden p-0">
          <TopologyGraph nodes={graphNodes} edges={topology.edges.map((edge) => ({ source: edge.sourceNodeKey, target: edge.targetNodeKey, label: relationshipLabel(edge.relationship) }))} height={460} showMiniMap onNodeSelect={setSelectedKey} highlightedNodeKeys={selectedKey ? { [selectedKey]: "direct" } : undefined} />
        </Card>
        <div className="flex flex-col gap-4">
          {selectedNode ? (
            <ReviewPanel
              key={selectedNode.nodeKey}
              title={selectedNode.label}
              subtitle={[t(`topology.nodeTypes.${selectedNode.nodeType}`, { defaultValue: selectedNode.nodeType }), selectedNode.technology].filter(Boolean).join(" · ")}
              verdict={selectedNode.reviewVerdict}
              comment={selectedNode.reviewCommentText}
              canEdit={canEdit}
              isSaving={review.isPending}
              onReview={(verdict, comment) => sendReview(selectedNode.nodeKey, verdict, comment)}
            />
          ) : (
            <Card dense className="p-[var(--card-padding)]"><p className="text-body-sm text-muted">{t("topology.selectNodeHint")}</p></Card>
          )}
          <ReviewPanel title={t("topology.wholeGraph")} verdict={null} comment={null} canEdit={canEdit} isSaving={review.isPending} onReview={(verdict, comment) => sendReview(undefined, verdict, comment)} />
        </div>
      </div>

      {topology.understandingSummaryMarkdown ? (
        <Card>
          <CardHeader title={t("topology.understanding")} actions={<AiGeneratedChip modelName={topology.generatedByModelName} generatedAt={topology.createdAt} size="sm" />} />
          <CardBody><MarkdownView content={topology.understandingSummaryMarkdown} /></CardBody>
        </Card>
      ) : null}
      {topology.uncertainties.length ? (
        <Banner tone="neutral" title={t("topology.uncertainties")}>
          <ul className="list-disc pl-5">{topology.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul>
        </Banner>
      ) : null}

      <Card>
        <CardHeader title={t("topology.relationships", { count: topology.edges.length })} />
        <CardBody>
          <ul className="flex flex-col divide-y divide-hairline">
            {topology.edges.map((edge: TopologyEdge) => (
              <li key={edge.edgeKey} className="flex flex-wrap items-center justify-between gap-2 py-2 text-body-sm">
                <span>
                  <span className="font-medium">{labelOf(edge.sourceNodeKey)}</span> <span className="text-muted">{relationshipLabel(edge.relationship)}</span> <span className="font-medium">{labelOf(edge.targetNodeKey)}</span>
                </span>
                <span className="flex items-center gap-2">
                  {edge.reviewVerdict ? <StatusChip size="sm" tone={verdictTones[edge.reviewVerdict]}>{t(`topology.verdicts.${edge.reviewVerdict}`)}</StatusChip> : null}
                  {canEdit ? (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => sendReview(edge.edgeKey, "looks_right")}>{t("topology.looksRight")}</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEdgeToCorrect(edge)}>{t("topology.needsCorrection")}</Button>
                    </>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
      <Dialog
        open={edgeToCorrect !== null}
        onOpenChange={(open) => { if (!open) { setEdgeToCorrect(null); setEdgeCorrection(""); } }}
        title={t("topology.correctRelationship", { source: labelOf(edgeToCorrect?.sourceNodeKey ?? ""), target: labelOf(edgeToCorrect?.targetNodeKey ?? "") })}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEdgeToCorrect(null)}>{t("topology.cancel")}</Button>
            <Button
              disabled={!edgeCorrection.trim()}
              onClick={() => { if (edgeToCorrect) sendReview(edgeToCorrect.edgeKey, "needs_correction", edgeCorrection.trim()); setEdgeToCorrect(null); setEdgeCorrection(""); }}
            >
              {t("topology.sendCorrection")}
            </Button>
          </>
        }
      >
        <Textarea aria-label={t("topology.correctionLabel")} placeholder={t("topology.correctionPlaceholder")} rows={3} value={edgeCorrection} onChange={(event) => setEdgeCorrection(event.target.value)} />
      </Dialog>
    </div>
  );
}

export function TopologyStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("knowledge");
  const topologyQuery = useTopology(applicationId);
  const buildTopology = useBuildTopology(applicationId);
  const topology = topologyQuery.data;
  const isBuilding = !!topology?.buildInProgress || buildTopology.isPending;
  const reviewTone = topology?.current?.reviewStatus === "reviewed" ? "success" : topology?.current?.reviewStatus === "needs_correction" ? "warning" : "neutral";

  return (
    <StepFrame
      stepKey="topology"
      actions={
        canEdit ? (
          <Button leadingIcon={Sparkles} isLoading={isBuilding} onClick={() => buildTopology.mutate(undefined, { onSuccess: onStatusChange })}>
            {topology?.current ? t("topology.rebuild") : t("topology.build")}
          </Button>
        ) : undefined
      }
    >
      {topologyQuery.isError ? (
        <ErrorState error={topologyQuery.error} onRetry={() => void topologyQuery.refetch()} />
      ) : topologyQuery.isLoading ? (
        <Skeleton className="h-96 rounded-lg" />
      ) : (
        <>
          {isBuilding ? (
            <Banner tone="ai" icon={false} title={t("topology.buildingTitle")}>
              <span className="flex items-center gap-2"><Spinner size="sm" />{t("topology.buildingBody")}</span>
            </Banner>
          ) : null}
          {topology?.current ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <StatusChip tone={reviewTone} dot>{t(`topology.reviewStatus.${topology.current.reviewStatus}`)}</StatusChip>
                <span className="text-body-sm text-muted">{t("topology.version", { number: topology.current.topologyVersionNumber, count: topology.versions.length })}</span>
              </div>
              <TopologyView applicationId={applicationId} topology={topology.current} canEdit={canEdit} />
            </>
          ) : !isBuilding ? (
            <EmptyState isBordered icon={Network} title={t("topology.emptyTitle")} description={t("topology.emptyDescription")} />
          ) : null}
        </>
      )}
    </StepFrame>
  );
}
