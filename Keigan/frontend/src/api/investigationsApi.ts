import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString, PagedResult, Priority } from "@/api/types/common";
import { incidentQueryKeys, type ApplicationReference, type IncidentSummary } from "./incidentsApi";

/* ── Types (doc 05 §6) ─────────────────────────────────────────────── */
export type InvestigationStatus = "queued" | "running" | "completed" | "completed_evidence_only" | "failed" | "cancelled";
export type AnalysisPerspective = "application" | "dependencies" | "infrastructure";
export type SignalStrength = "high" | "medium" | "low";
export type FeedbackVerdict = "correct" | "partially_correct" | "incorrect";
export type CommunicationType = "initial_update" | "executive_summary" | "preliminary_report" | "progress_update" | "resolution_update";
export type CommunicationStatus = "draft" | "approved" | "sent";

export interface InvestigationSummary {
  investigationId: Identifier;
  application: ApplicationReference;
  incidentId: Identifier | null;
  incidentNumber: string | null;
  incidentTitle: string | null;
  investigationTrigger: string;
  investigationStatus: InvestigationStatus;
  currentStageName: string;
  progressPercent: number;
  keiganPriority: Priority | null;
  overallConfidenceScore: number | null;
  executiveSummary: string | null;
  investigatedServiceNames: string[];
  createdAt: IsoDateTimeString;
  startedAt: IsoDateTimeString | null;
  completedAt: IsoDateTimeString | null;
  requestedByUserPrincipalName: string | null;
}

export interface StageMessage {
  at: IsoDateTimeString;
  stage: string;
  message: string;
}

export interface InvestigationProgress {
  investigationId: Identifier;
  status: InvestigationStatus;
  currentStageName: string;
  progressPercent: number;
  stageMessages: StageMessage[];
  failureReason: string | null;
}

export interface LogPattern {
  template: string;
  level: string;
  count: number;
  baselineCount: number;
  firstSeenAt: IsoDateTimeString | null;
  lastSeenAt: IsoDateTimeString | null;
  isNewPattern: boolean;
  changeRatio: number | null;
  sampleLinesMasked: string[];
  topDimensionValues: Record<string, Record<string, number>>;
  changeKind?: string;
  caller?: string | null;
}

export interface MetricSeriesSummary {
  metricName: string;
  unit: string;
  baselineMedian: number;
  windowPeak: number;
  windowPeakAt: IsoDateTimeString;
  robustZScore: number;
  signalStrength: SignalStrength;
  points: Array<{ t: IsoDateTimeString; v: number | null }>;
}

export interface Evidence {
  evidenceId: Identifier;
  evidenceCode: string;
  serviceId: Identifier | null;
  serviceName: string | null;
  evidenceSourceKind: string;
  evidenceCategory: string;
  evidenceTitle: string;
  evidenceSummary: string | null;
  queryLanguage: string;
  queryText: string | null;
  queryTimeRangeStart: IsoDateTimeString | null;
  queryTimeRangeEnd: IsoDateTimeString | null;
  matchedRecordCount: number;
  baselineRecordCount: number | null;
  condensedPatterns: LogPattern[];
  metricSeries: MetricSeriesSummary[];
  signalStrength: SignalStrength;
  maskedValueCount: number;
  possiblePromptInjection: boolean;
  deepLinkUrl: string | null;
  collectedAt: IsoDateTimeString;
}

export interface FixStep {
  description: string;
  commandText: string | null;
  commandLanguage: string | null;
  commandRiskLevel: "low" | "medium" | "high" | null;
}

export interface CodeChange {
  repositoryName: string | null;
  filePath: string;
  changeDescription: string;
  beforeSnippet: string | null;
  afterSnippet: string | null;
}

export interface ProposedFix {
  summary: string;
  steps: FixStep[];
  codeChanges: CodeChange[];
  verificationSteps: string[];
  rollbackSteps: string[];
}

export interface RunbookReference {
  runbookId: Identifier;
  runbookTitle: string;
}

export interface Hypothesis {
  hypothesisId: Identifier;
  analysisPerspective: AnalysisPerspective;
  hypothesisTitle: string;
  hypothesisStatementMarkdown: string | null;
  reasoningMarkdown: string | null;
  confidenceScore: number;
  supportingEvidenceCodes: string[];
  contradictingEvidenceCodes: string[];
  proposedFix: ProposedFix | null;
  fixRiskLevel: "low" | "medium" | "high";
  matchedRunbook: RunbookReference | null;
  isLeadingHypothesis: boolean;
  displayOrder: number;
}

export interface BlastRadiusNode {
  serviceId: Identifier;
  serviceName: string;
  serviceType: string;
  criticalityTier: string;
  impactLevel: "direct" | "indirect" | "investigated";
}

export interface BlastRadius {
  nodes: BlastRadiusNode[];
  edges: Array<{ fromServiceId: Identifier; toServiceId: Identifier; kind: string }>;
  impactedSlos: Array<Record<string, unknown>>;
  stakeholders: Array<{ displayName: string; role: string; preferredLanguageCode: string }>;
  narrativeMarkdown: string | null;
  userImpactSummary: string | null;
}

export interface AlertGroupPayload {
  alertGroupId: Identifier;
  groupTitle: string;
  groupSummary: string | null;
  groupStatus: string;
  priorityScore: number;
  groupingReason: string | null;
  memberAlertCount: number;
  startedAt: IsoDateTimeString;
  alerts: Array<{ alertId: Identifier; ruleName: string; severityLevel: number; alertStatus: string; firstSeenAt: IsoDateTimeString; alertSummary: string; finalDisposition: string | null }>;
  decisions: Array<{ alertId: Identifier; pipelineStage: string; decisionOutcome: string; decisionReason: string; decidedAt: IsoDateTimeString }>;
}

export interface InvestigationDetail extends InvestigationSummary {
  incident: IncidentSummary | null;
  investigationWindowStart: IsoDateTimeString | null;
  investigationWindowEnd: IsoDateTimeString | null;
  baselineWindowStart: IsoDateTimeString | null;
  baselineWindowEnd: IsoDateTimeString | null;
  services: Array<{ serviceId: Identifier; serviceName: string; serviceType: string }>;
  triage: Record<string, unknown> | null;
  whatWentWrongMarkdown: string | null;
  whyItHappenedMarkdown: string | null;
  howToFixMarkdown: string | null;
  openQuestions: string[];
  leadingHypothesisId: Identifier | null;
  hypotheses: Hypothesis[];
  evidence: Evidence[];
  blastRadius: BlastRadius | null;
  matchedRunbooks: RunbookReference[];
  knowledgeReferences: Array<Record<string, unknown>>;
  alertGroup: AlertGroupPayload | null;
  stageMessages: StageMessage[];
  isEvidenceOnly: boolean;
  failureReason: string | null;
  userFeedbackVerdict: FeedbackVerdict | null;
  userFeedbackComment: string | null;
  totalInputTokenCount: number;
  totalOutputTokenCount: number;
  modelNames: string[];
  detectedAt: IsoDateTimeString | null;
  firstUpdateSentAt: IsoDateTimeString | null;
}

export interface TimelineEvent {
  timelineEventId: Identifier;
  eventOccurredAt: IsoDateTimeString;
  eventType: string;
  eventTitle: string;
  eventDetailsMarkdown: string | null;
  eventSource: string;
  sourceReference: string | null;
  actorDisplayName: string | null;
}

export interface Communication {
  communicationId: Identifier;
  incidentId: Identifier | null;
  investigationId: Identifier | null;
  communicationType: CommunicationType;
  audienceType: string;
  languageCode: string;
  subjectLine: string;
  bodyMarkdown: string;
  communicationStatus: CommunicationStatus;
  approvedByUserPrincipalName: string | null;
  approvedAt: IsoDateTimeString | null;
  sentAt: IsoDateTimeString | null;
  createdAt: IsoDateTimeString;
  updatedAt: IsoDateTimeString;
}

export interface CommunicationSendResult {
  communication: Communication;
  deliveriesQueued: number;
  message: string;
}

export interface StartInvestigationRequest {
  applicationId: Identifier;
  serviceIds: Identifier[];
  description: string;
  windowStart?: IsoDateTimeString;
  windowEnd?: IsoDateTimeString;
}

/* ── Hooks ─────────────────────────────────────────────────────────── */
export const isInvestigationRunning = (status: string | undefined) => status === "queued" || status === "running";

export const investigationQueryKeys = {
  all: ["investigations"] as const,
  list: (incidentId: string) => ["investigations", "list", incidentId] as const,
  detail: (investigationId: string) => ["investigations", "detail", investigationId] as const,
  progress: (investigationId: string) => ["investigations", "progress", investigationId] as const,
  timeline: (investigationId: string) => ["investigations", "timeline", investigationId] as const,
  communications: (investigationId: string) => ["investigations", "communications", investigationId] as const,
};

export function useInvestigation(investigationId: string | undefined) {
  return useQuery({
    queryKey: investigationQueryKeys.detail(investigationId ?? ""),
    queryFn: ({ signal }) => apiGet<InvestigationDetail>(`/investigations/${investigationId}`, { signal }),
    enabled: Boolean(investigationId),
    refetchInterval: (query) => (isInvestigationRunning(query.state.data?.investigationStatus) ? 4_000 : false),
  });
}

/** Polled every 2 s while the investigation runs (doc 05 §6). */
export function useInvestigationProgress(investigationId: string | undefined, isRunning: boolean) {
  return useQuery({
    queryKey: investigationQueryKeys.progress(investigationId ?? ""),
    queryFn: ({ signal }) => apiGet<InvestigationProgress>(`/investigations/${investigationId}/progress`, { signal }),
    enabled: Boolean(investigationId) && isRunning,
    refetchInterval: 2_000,
  });
}

export function useInvestigationsForIncident(incidentId: string | undefined) {
  return useQuery({
    queryKey: investigationQueryKeys.list(incidentId ?? ""),
    queryFn: ({ signal }) => apiGet<PagedResult<InvestigationSummary>>("/investigations", { query: { incidentId, pageSize: 20 }, signal }),
    enabled: Boolean(incidentId),
    placeholderData: keepPreviousData,
  });
}

export function useInvestigationTimeline(investigationId: string | undefined, isRunning: boolean) {
  return useQuery({
    queryKey: investigationQueryKeys.timeline(investigationId ?? ""),
    queryFn: ({ signal }) => apiGet<TimelineEvent[]>(`/investigations/${investigationId}/timeline`, { signal }),
    enabled: Boolean(investigationId),
    refetchInterval: isRunning ? 4_000 : 30_000,
  });
}

export function useStartInvestigation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: StartInvestigationRequest) => apiPost<AcceptedJob, StartInvestigationRequest>("/investigations", request),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.all }),
  });
}

export function useRerunInvestigation(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<AcceptedJob>(`/investigations/${investigationId}/rerun`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.all });
    },
  });
}

export function useInvestigationFeedback(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: { verdict: FeedbackVerdict; comment?: string }) => apiPost<InvestigationSummary, typeof request>(`/investigations/${investigationId}/feedback`, request),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.detail(investigationId) }),
  });
}

export function useCommunications(investigationId: string | undefined) {
  return useQuery({
    queryKey: investigationQueryKeys.communications(investigationId ?? ""),
    queryFn: ({ signal }) => apiGet<Communication[]>(`/investigations/${investigationId}/communications`, { signal }),
    enabled: Boolean(investigationId),
    refetchInterval: 15_000,
  });
}

export function useGenerateCommunications(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: { communicationType: CommunicationType; languageCodes: string[] }) => apiPost<AcceptedJob, typeof request>(`/investigations/${investigationId}/communications/generate`, request),
    onSuccess: () => window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.communications(investigationId) }), 2500),
  });
}

export function useUpdateCommunication(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ communicationId, ...request }: { communicationId: Identifier; subjectLine?: string; bodyMarkdown?: string }) =>
      apiPatch<Communication, typeof request>(`/communications/${communicationId}`, request),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.communications(investigationId) }),
  });
}

export function useApproveCommunication(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (communicationId: Identifier) => apiPost<Communication>(`/communications/${communicationId}/approve`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.communications(investigationId) }),
  });
}

export function useSendCommunication(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (communicationId: Identifier) => apiPost<CommunicationSendResult>(`/communications/${communicationId}/send`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: investigationQueryKeys.communications(investigationId) }),
  });
}
