import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString, PagedResult, Priority } from "@/api/types/common";
import type { AlertGroupingReason } from "@/api/alertsApi";
import { incidentQueryKeys, type ApplicationReference, type IncidentSummary } from "./incidentsApi";

/* ── Types (doc 05 §6) ─────────────────────────────────────────────── */
export type InvestigationStatus = "queued" | "running" | "completed" | "completed_evidence_only" | "failed" | "cancelled";
export type AnalysisPerspective = "application" | "dependencies" | "infrastructure";
export type SignalStrength = "high" | "medium" | "low";
export type FeedbackVerdict = "correct" | "partially_correct" | "incorrect";
export type CommunicationType = "initial_update" | "executive_summary" | "preliminary_report" | "progress_update" | "resolution_update";
export type CommunicationStatus = "draft" | "approved" | "sent";

/** How far an investigation got. `not_recorded` is an investigation that ran before Keigan recorded outcomes. */
export type InvestigationOutcomeCode = "cause_identified" | "inconclusive" | "cause_not_visible" | "not_recorded";
export type HypothesisStateName = "supported" | "ruled_out" | "inconclusive";
export type EvidenceCheckOutcome = "signal" | "no_signal" | "not_checked";
export type BaselineComparison = "compared" | "no_baseline_for_source";

export interface InvestigationOutcomeInfo {
  code: InvestigationOutcomeCode;
  proposedCode: string | null;
  guardCode: string | null;
  reasonMarkdown: string | null;
}

/** One thing the investigation meant to check and could not (codes and catalogue names only). */
export interface CoverageGap {
  coverageGapId: Identifier;
  gapKind: string;
  reasonCode: string | null;
  serviceId: Identifier | null;
  serviceName: string | null;
  sourceKind: string | null;
  parameters: Record<string, unknown>;
  legacyEvidenceCode: string | null;
}

export interface InvestigationSummary {
  investigationId: Identifier;
  application: ApplicationReference;
  incidentId: Identifier | null;
  incidentNumber: string | null;
  incidentTitle: string | null;
  investigationTrigger: string;
  investigationStatus: InvestigationStatus;
  /** Null while the investigation runs, failed or ended evidence only. */
  investigationOutcome: InvestigationOutcomeCode | null;
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
  checkOutcome: EvidenceCheckOutcome | null;
  baselineComparison: BaselineComparison | null;
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
  /** Why Keigan did not show the command (the description stays); null when it is shown. */
  commandWithheldReason: string | null;
  /** Code-written warnings about the command, for example `prints_secrets`. */
  commandWarnings: string[];
}

export interface CodeChange {
  repositoryName: string | null;
  filePath: string;
  changeDescription: string;
  beforeSnippet: string | null;
  afterSnippet: string | null;
}

/* ── Checked fix steps (spec 33, schema version 2) ─────────────────────────────────────────── */
export type FixRisk = "low" | "medium" | "high";
export type FixValueStatus = "verified" | "assumed" | "missing" | "masked" | "refused";
export type FixStepPurpose = "diagnose" | "mitigate" | "durable_fix";
export type FixActionKind = "command" | "configuration_change" | "manual_action" | "rerun_evidence_query";
export type FixSegmentKind = "literal" | "value" | "assumed_value" | "missing_value";

/** One value of a command or setting. `value` is never a refused or masked value: the server clears those. The patterns are the server's, so typed input is checked with the same rules. */
export interface FixParameter {
  name: string;
  valueKind: string;
  value: string | null;
  valueSource: string;
  sourceCode: string | null;
  status: FixValueStatus;
  statusReason: string | null;
  valuePattern: string | null;
  barePattern: string | null;
  maximumLength: number | null;
  labelKey: string | null;
}

export interface FixSegment {
  kind: FixSegmentKind;
  text: string;
  parameterName: string | null;
}

export interface FixRendering {
  dialect: "bash" | "powershell";
  /** The command to copy; null while a value is missing. */
  text: string | null;
  riskLevel: FixRisk;
  segments: FixSegment[];
}

export interface FixCommand {
  tool: string;
  dialect: string;
  template: string;
  parameters: FixParameter[];
  withheldReason: string | null;
  renderings: FixRendering[];
  riskLevel: FixRisk;
  warnings: string[];
}

export interface FixConfigurationChange {
  targetKind: string;
  serviceName: string;
  serviceInCatalogue: boolean;
  settingName: FixParameter;
  beforeValue: FixParameter | null;
  afterValue: FixParameter;
  filePath: string | null;
  withheldReason: string | null;
  riskLevel: FixRisk;
  warnings: string[];
}

export interface FixAction {
  actionKind: FixActionKind;
  description: string;
  expectedResult: string;
  riskLevel: FixRisk;
  command: FixCommand | null;
  configurationChange: FixConfigurationChange | null;
  evidenceCode: string | null;
  withheldReason: string | null;
}

export interface FixStepV2 {
  stepId: string;
  title: string;
  purpose: FixStepPurpose;
  riskLevel: FixRisk;
  riskReasons: string[];
  warnings: string[];
  assumptions: string[];
  hasAssumedValues: boolean;
  missingValueCount: number;
  action: FixAction;
  check: FixAction | null;
  revert: FixAction | null;
  /** Set on the steps of the fix plan: which analyst wrote the step. */
  perspective: string | null;
}

export interface FixPlan {
  overviewMarkdown: string;
  steps: FixStepV2[];
}

/** Version 1 rows (written before spec 33 phase 2) keep their free-text `steps`; version 2 rows carry `fixSteps`. */
export interface ProposedFix {
  schemaVersion: 1 | 2;
  summary: string;
  steps: FixStep[];
  fixSteps: FixStepV2[];
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
  /** Null on a hypothesis stored before states were recorded. */
  state: HypothesisStateName | null;
  proposedState: HypothesisStateName | null;
  stateGuardCode: string | null;
  stateReasonMarkdown: string | null;
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
  groupingReason: AlertGroupingReason;
  memberAlertCount: number;
  startedAt: IsoDateTimeString;
  alerts: Array<{ alertId: Identifier; ruleName: string; severityLevel: number; alertStatus: string; firstSeenAt: IsoDateTimeString; alertSummary: string; finalDisposition: string | null }>;
  decisions: Array<{ alertId: Identifier; pipelineStage: string; decisionOutcome: string; decisionReason: string; decidedAt: IsoDateTimeString }>;
}

export interface InvestigationDetail extends InvestigationSummary {
  outcome: InvestigationOutcomeInfo | null;
  leadingPerspectiveReasonMarkdown: string | null;
  coverageGaps: CoverageGap[];
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
  /** The recommended steps, resolved from the analysts' checked steps; null for an investigation written before the plan existed. */
  fixPlan: FixPlan | null;
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

export interface TraceAttempt { outcomeStatus: string; latencyMilliseconds: number; inputTokenCount: number; outputTokenCount: number }
export interface TraceInputSection {
  title: string;
  sourceLabel: string;
  isUntrusted: boolean;
  isFlagged: boolean;
  characterCount: number;
  sentCharacterCount: number;
  isTruncated: boolean;
  sha256: string;
  citationCodes: string[];
}
export interface TraceAdjustment { code: string; parameters: Record<string, unknown> }
export interface TraceAiCall {
  featureName: string | null;
  promptKey: string | null;
  promptVersion: string | null;
  promptTemplateSha256: string | null;
  systemPromptSha256: string | null;
  providerName: string | null;
  modelName: string | null;
  modelTier: string | null;
  inputTokenCount: number;
  outputTokenCount: number;
  tokenCountsEstimated: boolean;
  attempts: TraceAttempt[];
  inputSections: TraceInputSection[];
  adjustments: TraceAdjustment[];
  hasRawOutput: boolean;
  rawOutputCharacterCount: number | null;
  rawOutputIsTruncated: boolean | null;
  failureCode: string | null;
  hypothesisId: string | null;
}
export interface TraceStep {
  traceStepId: Identifier;
  sequenceNumber: number;
  stageName: string;
  stepKind: "inputs" | "ai_call" | "evidence" | "decision" | "outcome";
  stepStatus: "succeeded" | "failed" | "skipped";
  decisionKind: string | null;
  startedAt: IsoDateTimeString;
  completedAt: IsoDateTimeString | null;
  durationMilliseconds: number | null;
  aiCall: TraceAiCall | null;
  details: Record<string, unknown> | null;
}
export interface TraceCallWithoutStep { featureName: string; modelName: string; createdAt: IsoDateTimeString; inputTokenCount: number; outputTokenCount: number; outcomeStatus: string }
export interface InvestigationTrace {
  investigationId: Identifier;
  isRecorded: boolean;
  isComplete: boolean;
  pipelineVersion: string | null;
  status: string;
  outcome: InvestigationOutcomeInfo | null;
  totals: { inputTokenCount: number; outputTokenCount: number; tokenCountsEstimated: boolean; aiCallCount: number; attemptCount: number; failedAttemptCount: number; durationMilliseconds: number | null };
  models: Array<{ providerName: string | null; modelName: string | null; modelTier: string | null; callCount: number }>;
  prompts: Array<{ promptKey: string; promptVersion: string | null; promptTemplateSha256: string | null }>;
  steps: TraceStep[];
  callsWithoutStep: TraceCallWithoutStep[];
}
export interface RawOutput { rawOutput: Record<string, unknown>; characterCount: number; isTruncated: boolean; sha256: string }

export const investigationQueryKeys = {
  all: ["investigations"] as const,
  trace: (investigationId: string) => ["investigations", "trace", investigationId] as const,
  rawOutput: (investigationId: string, traceStepId: string) => ["investigations", "trace", investigationId, "raw", traceStepId] as const,
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
/** The decision trace; refreshed while the investigation runs so steps appear as they finish. */
export function useInvestigationTrace(investigationId: string | undefined, isRunning: boolean) {
  return useQuery({
    queryKey: investigationQueryKeys.trace(investigationId ?? ""),
    queryFn: ({ signal }) => apiGet<InvestigationTrace>(`/investigations/${investigationId}/trace`, { signal }),
    enabled: Boolean(investigationId),
    refetchInterval: isRunning ? 4_000 : false,
  });
}

/** The raw AI answer of one step (application admins only); fetched only when the dialog opens. */
export function useRawOutput(investigationId: string, traceStepId: string | null) {
  return useQuery({
    queryKey: investigationQueryKeys.rawOutput(investigationId, traceStepId ?? ""),
    queryFn: ({ signal }) => apiGet<RawOutput>(`/investigations/${investigationId}/trace/steps/${traceStepId}/raw-output`, { signal }),
    enabled: traceStepId !== null,
    retry: false,
  });
}

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
