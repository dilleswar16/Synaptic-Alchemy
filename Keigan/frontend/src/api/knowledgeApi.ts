import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost, apiUpload, type UploadOptions } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (doc 05 §5) ──────────────────────────────────────────────────────── */
export type DocumentCategory = "code_context" | "architecture" | "operations_guide" | "runbook_source" | "incident_history" | "other";
export type DigestStatus = "pending" | "running" | "ready" | "failed";

export interface CapturePrompt {
  promptMarkdown: string;
  lineCount: number;
  version: string;
  suggestedFileName: string;
}
export interface KnowledgeDocument {
  knowledgeDocumentId: Identifier;
  applicationId: Identifier;
  serviceId: Identifier | null;
  serviceName: string | null;
  documentTitle: string;
  documentCategory: DocumentCategory;
  originalFileName: string;
  contentType: string;
  fileSizeBytes: number;
  headings: string[];
  aiDigestStatus: DigestStatus;
  aiDigestErrorMessage: string | null;
  possiblePromptInjection: boolean;
  estimatedTokenCount: number;
  uploadedByUserPrincipalName: string | null;
  uploadedAt: IsoDateTimeString;
  staleAfterAt: IsoDateTimeString | null;
  isStale: boolean;
}
export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  aiDigestMarkdown: string | null;
  extractedTextExcerpt: string | null;
  chunkCount: number;
}

export type ReviewVerdict = "looks_right" | "needs_correction" | "comment";
export interface TopologyNode {
  nodeKey: string;
  label: string;
  nodeType: string;
  serviceId: Identifier | null;
  technology: string | null;
  description: string | null;
  criticality: string | null;
  reviewVerdict: ReviewVerdict | null;
  reviewCommentText: string | null;
}
export interface TopologyEdge {
  edgeKey: string;
  sourceNodeKey: string;
  targetNodeKey: string;
  relationship: string;
  protocol: string | null;
  description: string | null;
  reviewVerdict: ReviewVerdict | null;
  reviewCommentText: string | null;
}
export interface TopologyVersion {
  topologyId: Identifier;
  topologyVersionNumber: number;
  generationStatus: "building" | "ready" | "failed";
  reviewStatus: "awaiting_review" | "reviewed" | "needs_correction";
  isCurrentVersion: boolean;
  generatedByModelName: string | null;
  createdAt: IsoDateTimeString;
}
export interface TopologyDetail extends TopologyVersion {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  understandingSummaryMarkdown: string | null;
  uncertainties: string[];
}
export interface TopologyResponse {
  current: TopologyDetail | null;
  versions: TopologyVersion[];
  buildInProgress: boolean;
}

export interface Runbook {
  runbookId: Identifier;
  applicationId: Identifier;
  runbookTitle: string;
  triggerSymptomsText: string | null;
  runbookStepsMarkdown: string | null;
  sourceUrl: string | null;
  appliesToServiceIds: Identifier[];
  appliesToServiceNames: string[];
  knowledgeDocumentId: Identifier | null;
  timesReferencedCount: number;
  lastReferencedAt: IsoDateTimeString | null;
  updatedAt: IsoDateTimeString;
}
export interface RunbookBody {
  runbookTitle: string;
  triggerSymptomsText?: string | null;
  runbookStepsMarkdown?: string | null;
  sourceUrl?: string | null;
  appliesToServiceIds: Identifier[];
}

export const knowledgeQueryKeys = {
  documents: (applicationId: string) => ["knowledge", applicationId, "documents"] as const,
  document: (applicationId: string, documentId: string) => ["knowledge", applicationId, "documents", documentId] as const,
  capturePrompt: (applicationId: string, serviceId: string | null) => ["knowledge", applicationId, "capture-prompt", serviceId] as const,
  topology: (applicationId: string) => ["knowledge", applicationId, "topology"] as const,
  runbooks: (applicationId: string) => ["knowledge", applicationId, "runbooks"] as const,
};

const applicationPath = (applicationId: string) => `/applications/${applicationId}`;

/** Documents whose digest is still running are refreshed every few seconds. */
export const useKnowledgeDocuments = (applicationId: string) =>
  useQuery({
    queryKey: knowledgeQueryKeys.documents(applicationId),
    queryFn: () => apiGet<KnowledgeDocument[]>(`${applicationPath(applicationId)}/knowledge/documents`),
    refetchInterval: (query) => (query.state.data?.some((document) => document.aiDigestStatus === "pending" || document.aiDigestStatus === "running") ? 3000 : false),
  });
export const useKnowledgeDocument = (applicationId: string, documentId: string | null) =>
  useQuery({
    queryKey: knowledgeQueryKeys.document(applicationId, documentId ?? ""),
    queryFn: () => apiGet<KnowledgeDocumentDetail>(`${applicationPath(applicationId)}/knowledge/documents/${documentId}`),
    enabled: documentId !== null,
  });
export const useCapturePrompt = (applicationId: string, serviceId: string | null) =>
  useQuery({
    queryKey: knowledgeQueryKeys.capturePrompt(applicationId, serviceId),
    queryFn: () => apiGet<CapturePrompt>(`${applicationPath(applicationId)}/knowledge/capture-prompt`, { query: { serviceId } }),
  });
export const useTopology = (applicationId: string) =>
  useQuery({
    queryKey: knowledgeQueryKeys.topology(applicationId),
    queryFn: () => apiGet<TopologyResponse>(`${applicationPath(applicationId)}/topology`),
    refetchInterval: (query) => (query.state.data?.buildInProgress ? 2500 : false),
  });
export const useRunbooks = (applicationId: string) =>
  useQuery({ queryKey: knowledgeQueryKeys.runbooks(applicationId), queryFn: () => apiGet<Runbook[]>(`${applicationPath(applicationId)}/runbooks`) });

/** Everything on a step changes readiness, so mutations refresh the whole application subtree and the knowledge subtree. */
function useKnowledgeMutation<Result, Variables>(applicationId: string, mutate: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: mutate,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["knowledge", applicationId] }),
        queryClient.invalidateQueries({ queryKey: ["applications", applicationId, "readiness"] }),
      ]);
    },
  });
}

export interface UploadDocumentVariables {
  file: File;
  documentCategory: DocumentCategory;
  serviceId: string | null;
  documentTitle?: string;
  onUploadProgress?: UploadOptions["onUploadProgress"];
}
export const useUploadDocument = (applicationId: string) =>
  useKnowledgeMutation(applicationId, (variables: UploadDocumentVariables) => {
    const formData = new FormData();
    formData.append("file", variables.file);
    formData.append("documentCategory", variables.documentCategory);
    if (variables.serviceId) formData.append("serviceId", variables.serviceId);
    if (variables.documentTitle) formData.append("documentTitle", variables.documentTitle);
    return apiUpload<{ document: KnowledgeDocument; jobId: string }>(`${applicationPath(applicationId)}/knowledge/documents`, formData, {
      onUploadProgress: variables.onUploadProgress,
    });
  });
export const useDeleteDocument = (applicationId: string) =>
  useKnowledgeMutation(applicationId, (documentId: string) => apiDelete<void>(`${applicationPath(applicationId)}/knowledge/documents/${documentId}`));
export const useBuildTopology = (applicationId: string) =>
  useKnowledgeMutation(applicationId, () => apiPost<AcceptedJob>(`${applicationPath(applicationId)}/topology/build`));
export const useReviewTopology = (applicationId: string) =>
  useKnowledgeMutation(applicationId, (variables: { topologyId: string; targetElementKey?: string; reviewVerdict: ReviewVerdict; reviewCommentText?: string }) =>
    apiPost(`${applicationPath(applicationId)}/topology/${variables.topologyId}/reviews`, {
      targetElementKey: variables.targetElementKey,
      reviewVerdict: variables.reviewVerdict,
      reviewCommentText: variables.reviewCommentText,
    }));
export const useSaveRunbook = (applicationId: string) =>
  useKnowledgeMutation(applicationId, (variables: { runbookId?: string; body: RunbookBody }) =>
    variables.runbookId
      ? apiPatch<Runbook>(`${applicationPath(applicationId)}/runbooks/${variables.runbookId}`, variables.body)
      : apiPost<Runbook>(`${applicationPath(applicationId)}/runbooks`, variables.body));
export const useDeleteRunbook = (applicationId: string) =>
  useKnowledgeMutation(applicationId, (runbookId: string) => apiDelete<void>(`${applicationPath(applicationId)}/runbooks/${runbookId}`));

/* ── Runbook health (spec 32) ──────────────────────────────────────── */
export type RunbookFindingKind = "no_trigger_symptoms" | "no_steps" | "never_used" | "not_updated" | "often_wrong";
export const runbookFindingKinds: RunbookFindingKind[] = ["no_trigger_symptoms", "no_steps", "never_used", "not_updated", "often_wrong"];

export interface RunbookFinding {
  kind: RunbookFindingKind;
  /** The figures behind the finding: `days`, or `incorrect` and `rated`. */
  parameters: { days?: number; incorrect?: number; rated?: number };
}
export interface RunbookHealthRow {
  runbookId: string;
  runbookTitle: string;
  timesReferencedCount: number;
  lastReferencedAt: string | null;
  createdAt: string;
  updatedAt: string;
  matchedInvestigationCount: number;
  ratedInvestigationCount: number;
  incorrectRatedCount: number;
  findings: RunbookFinding[];
}
export interface RunbookHealth {
  runbookCount: number;
  withFindingsCount: number;
  runbooks: RunbookHealthRow[];
}
export const useRunbookHealth = (applicationId: string) =>
  useQuery({ queryKey: ["knowledge", applicationId, "runbook-health"] as const, queryFn: ({ signal }) => apiGet<RunbookHealth>(`${applicationPath(applicationId)}/runbook-health`, { signal }) });
