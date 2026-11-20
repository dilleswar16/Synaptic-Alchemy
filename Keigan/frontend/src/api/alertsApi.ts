import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString, PagedResult } from "@/api/types/common";

/* ── Types (doc 05 §8) ─────────────────────────────────────────────── */
export type AlertTool = "azure_monitor" | "elastic" | "generic";
export type PolicyMode = "observe" | "active";

export interface AlertSource {
  alertSourceId: Identifier;
  applicationId: Identifier;
  sourceTool: AlertTool;
  sourceName: string;
  sourceStatus: "waiting_for_first_alert" | "receiving" | "authentication_failures" | "paused";
  webhookUrl: string;
  fieldMapping: Record<string, string> | null;
  severityMapping: Record<string, number> | null;
  serviceMapping: ServiceMapping | null;
  lastReceivedAt: IsoDateTimeString | null;
  receivedAlertCount: number;
  authenticationFailureCount: number;
  previousSecretValidUntil: IsoDateTimeString | null;
  sevenDayAlertCount: number;
  sevenDayGroupCount: number;
  sevenDayInvestigatedCount: number;
}

export interface ServiceMapping {
  field_path?: string;
  value_map?: Record<string, string>;
  auto_match?: boolean;
}

export interface SetupCodeBlock { title: string; language: string; content: string }
export interface SetupTab { tabKey: string; tabTitle: string; steps: string[]; codeBlocks: SetupCodeBlock[] }
export interface SetupInstructions {
  sourceTool: AlertTool;
  webhookUrl: string;
  webhookSecretIsPlaceholder: boolean;
  headerName: string;
  tabs: SetupTab[];
  canonicalExample: Record<string, unknown>;
}
export interface AlertSourceCreated { alertSource: AlertSource; webhookUrl: string; webhookSecret: string; setupInstructions: SetupInstructions }
export interface SecretRotation { alertSource: AlertSource; webhookUrl: string; webhookSecret: string; previousSecretValidUntil: IsoDateTimeString }

export interface CreateAlertSourceBody {
  sourceTool: AlertTool;
  sourceName: string;
  fieldMapping?: Record<string, string> | null;
  severityMapping?: Record<string, number> | null;
  serviceMapping?: ServiceMapping | null;
}
export type UpdateAlertSourceBody = Partial<Omit<CreateAlertSourceBody, "sourceTool">> & { isPaused?: boolean };

export interface MappingPreviewBody {
  sourceTool: AlertTool;
  samplePayload?: Record<string, unknown> | null;
  fieldMapping?: Record<string, string> | null;
  severityMapping?: Record<string, number> | null;
  serviceMapping?: ServiceMapping | null;
}
export interface MappingPreview {
  isParsed: boolean;
  errorMessage: string | null;
  parsedAlert: Record<string, unknown> | null;
  matchedServiceId: string | null;
  matchedServiceName: string | null;
  suggestedFieldMapping: Record<string, string>;
  availablePaths: string[];
  distinctServiceValues: string[];
}

export interface RecentAlertEvent {
  alertEventId: Identifier;
  receivedAt: IsoDateTimeString;
  processingStatus: string;
  processingErrorMessage: string | null;
  payloadSizeBytes: number;
  rawPayload: Record<string, unknown> | null;
  parsedAlert: Record<string, unknown> | null;
  matchedServiceName: string | null;
  parseError: string | null;
}

export interface AzureAlertRule {
  ruleName: string;
  ruleKind: string;
  severity: number | null;
  targetResource: string | null;
  isEnabled: boolean;
  sendsToKeigan: boolean;
  actionGroupNames: string[];
}
/** A resource group whose alert rules Keigan could not read. The rules are missing from the list. */
export interface UnreadableResourceGroup { resourceGroupName: string; subscriptionId: string; reasonCode: "forbidden" | "not_found" | "throttled" | "failed" }
export interface AzureAlertRules { isSimulated: boolean; totalRuleCount: number; sendingToKeiganCount: number; rules: AzureAlertRule[]; unreadableResourceGroups: UnreadableResourceGroup[] }

export interface NoisePolicySettings {
  minSeverity: number;
  investigateEnvironments: string[];
  settleDelayMinutes: number;
  noDelaySeverities: number[];
  reopenWindowMinutes: number;
  groupWindowMinutes: number;
  flapCount: number;
  flapWindowMinutes: number;
  maxInvestigationsPerHour: number;
  investigateScoreThreshold: number;
}
export interface FunnelStep { stepKey: string; stepLabel: string; count: number; detail: string | null }
export interface Funnel {
  periodStart: IsoDateTimeString;
  periodEnd: IsoDateTimeString;
  steps: FunnelStep[];
  reasonCounts: Record<string, number>;
  summarySentence: string;
  isIllustration: boolean;
}
export interface NoisePolicy {
  applicationId: Identifier;
  policyMode: PolicyMode;
  policySettings: NoisePolicySettings;
  policySentences: string[];
  observeModeStartedAt: IsoDateTimeString | null;
  observeModeDaysRemaining: number | null;
  observedEffect: Funnel | null;
  dependencyHint: string | null;
}
export interface NoisePolicyUpdateBody { policyMode?: PolicyMode; policySettings?: NoisePolicySettings; resetToDefaults?: boolean }

export interface MaintenanceWindow {
  maintenanceWindowId: Identifier;
  applicationId: Identifier;
  windowName: string;
  appliesToServiceIds: string[];
  appliesToServiceNames: string[];
  appliesToEnvironments: string[];
  startsAt: IsoDateTimeString;
  endsAt: IsoDateTimeString;
  repeatsWeekly: boolean;
  isActiveNow: boolean;
  createdByUserPrincipalName: string | null;
}
export interface MaintenanceWindowBody {
  windowName: string;
  appliesToServiceIds?: string[];
  appliesToEnvironments?: string[];
  startsAt: string;
  endsAt: string;
  repeatsWeekly: boolean;
}
export interface MuteRuleMatcher {
  ruleNameContains?: string | null;
  serviceId?: string | null;
  alertSourceId?: string | null;
  severity?: number | null;
  labelKey?: string | null;
  labelValue?: string | null;
}
export interface MuteRule {
  muteRuleId: Identifier;
  applicationId: Identifier;
  ruleName: string;
  matcher: Record<string, unknown>;
  muteReason: string;
  expiresAt: IsoDateTimeString;
  isExpired: boolean;
  createdByUserPrincipalName: string | null;
}
export interface MuteRuleBody { ruleName: string; matcher: MuteRuleMatcher; muteReason: string; expiresAt: string }

export interface AlertGroupSummary {
  alertGroupId: Identifier;
  applicationId: Identifier;
  applicationName: string | null;
  groupTitle: string;
  groupSummary: string | null;
  groupStatus: "open" | "queued" | "resolved";
  priorityScore: number;
  groupingReason: string | null;
  memberAlertCount: number;
  totalOccurrenceCount: number;
  services: Array<{ serviceId: string; serviceName: string }>;
  highestSeverityLevel: number;
  startedAt: IsoDateTimeString;
  lastActivityAt: IsoDateTimeString;
  resolvedAt: IsoDateTimeString | null;
  investigationId: Identifier | null;
  incidentId: Identifier | null;
  servicenowIncidentSuggested: boolean;
  userFeedbackVerdict: "useful" | "noise" | null;
  decisionReason: string | null;
  decisionOutcome: string | null;
}
export interface AlertMember {
  alertId: Identifier;
  ruleName: string;
  alertStatus: string;
  severityLevel: number;
  serviceName: string | null;
  alertSummary: string;
  occurrenceCount: number;
  isFlapping: boolean;
  firstSeenAt: IsoDateTimeString;
  lastSeenAt: IsoDateTimeString;
  resolvedAt: IsoDateTimeString | null;
  finalDisposition: string | null;
}
export interface AlertDecision {
  alertDecisionId: Identifier;
  alertId: Identifier;
  ruleName: string | null;
  pipelineStage: string;
  decisionOutcome: string;
  decisionReason: string;
  wouldHaveOutcomeInActiveMode: string | null;
  decidedAt: IsoDateTimeString;
}
export interface AlertGroupDetail extends AlertGroupSummary {
  members: AlertMember[];
  decisions: AlertDecision[];
  userFeedbackReason: string | null;
  policyMode: PolicyMode;
}
export interface AlertGroupFilters { applicationIds: string[]; periodStart: string; statuses?: string[]; page: number; pageSize: number }

/* ── Query keys and hooks ──────────────────────────────────────────── */
export const alertQueryKeys = {
  all: ["alerts"] as const,
  groups: (filters: AlertGroupFilters) => ["alerts", "groups", filters] as const,
  group: (alertGroupId: string) => ["alerts", "group", alertGroupId] as const,
  funnel: (applicationIds: string[], periodStart: string) => ["alerts", "funnel", applicationIds, periodStart] as const,
  sources: (applicationId: string) => ["alerts", "sources", applicationId] as const,
  events: (applicationId: string, alertSourceId: string) => ["alerts", "events", applicationId, alertSourceId] as const,
  rules: (applicationId: string) => ["alerts", "azure-rules", applicationId] as const,
  policy: (applicationId: string) => ["alerts", "policy", applicationId] as const,
  windows: (applicationId: string) => ["alerts", "windows", applicationId] as const,
  muteRules: (applicationId: string) => ["alerts", "mute-rules", applicationId] as const,
};
const applicationBase = (applicationId: string) => `/applications/${applicationId}`;

export const useAlertGroups = (filters: AlertGroupFilters) =>
  useQuery({
    queryKey: alertQueryKeys.groups(filters),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
    queryFn: () =>
      apiGet<PagedResult<AlertGroupSummary>>("/alert-groups", {
        query: { applicationIds: filters.applicationIds, from: filters.periodStart, statuses: filters.statuses, page: filters.page, pageSize: filters.pageSize },
      }),
  });
export const useAlertGroup = (alertGroupId: string | null) =>
  useQuery({ queryKey: alertQueryKeys.group(alertGroupId ?? ""), enabled: Boolean(alertGroupId), queryFn: () => apiGet<AlertGroupDetail>(`/alert-groups/${alertGroupId}`) });
export const useAlertFunnel = (applicationIds: string[], periodStart: string) =>
  useQuery({ queryKey: alertQueryKeys.funnel(applicationIds, periodStart), queryFn: () => apiGet<Funnel>("/alerts/funnel", { query: { applicationIds, from: periodStart } }) });

function useInvalidatingMutation<Variables, Result>(mutationFunction: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: mutationFunction, onSuccess: () => queryClient.invalidateQueries({ queryKey: alertQueryKeys.all }) });
}

export const useGiveGroupFeedback = () =>
  useInvalidatingMutation((variables: { alertGroupId: string; verdict: "useful" | "noise"; reason?: string }) =>
    apiPost<AlertGroupSummary>(`/alert-groups/${variables.alertGroupId}/feedback`, { verdict: variables.verdict, reason: variables.reason }));
export const useCreateIncidentFromGroup = () =>
  useInvalidatingMutation((alertGroupId: string) => apiPost<{ incidentId: string }>(`/alert-groups/${alertGroupId}/create-servicenow-incident`));

export const useAlertSources = (applicationId: string) => useQuery({ queryKey: alertQueryKeys.sources(applicationId), queryFn: () => apiGet<AlertSource[]>(`${applicationBase(applicationId)}/alert-sources`) });
export const useCreateAlertSource = (applicationId: string) =>
  useInvalidatingMutation((body: CreateAlertSourceBody) => apiPost<AlertSourceCreated>(`${applicationBase(applicationId)}/alert-sources`, body));
export const useUpdateAlertSource = (applicationId: string) =>
  useInvalidatingMutation((variables: { alertSourceId: string; body: UpdateAlertSourceBody }) =>
    apiPatch<AlertSource>(`${applicationBase(applicationId)}/alert-sources/${variables.alertSourceId}`, variables.body));
export const useDeleteAlertSource = (applicationId: string) =>
  useInvalidatingMutation((alertSourceId: string) => apiDelete(`${applicationBase(applicationId)}/alert-sources/${alertSourceId}`));
export const useRotateAlertSourceSecret = (applicationId: string) =>
  useInvalidatingMutation((alertSourceId: string) => apiPost<SecretRotation>(`${applicationBase(applicationId)}/alert-sources/${alertSourceId}/rotate-secret`));
export const useSendTestAlert = (applicationId: string) =>
  useInvalidatingMutation((alertSourceId: string) => apiPost<{ alertEventId: string }>(`${applicationBase(applicationId)}/alert-sources/${alertSourceId}/test`));
export const usePreviewAlertMapping = (applicationId: string) =>
  useMutation({ mutationFn: (body: MappingPreviewBody) => apiPost<MappingPreview>(`${applicationBase(applicationId)}/alert-sources/mapping-preview`, body) });
export const useRecentAlertEvents = (applicationId: string, alertSourceId: string | null, isListening: boolean) =>
  useQuery({
    queryKey: alertQueryKeys.events(applicationId, alertSourceId ?? ""),
    enabled: Boolean(alertSourceId),
    refetchInterval: isListening ? 3_000 : false,
    queryFn: () => apiGet<RecentAlertEvent[]>(`${applicationBase(applicationId)}/alert-sources/${alertSourceId}/recent-events`),
  });
export const useAzureAlertRules = (applicationId: string) => useQuery({ queryKey: alertQueryKeys.rules(applicationId), queryFn: () => apiGet<AzureAlertRules>(`${applicationBase(applicationId)}/azure-alert-rules`) });

export const useNoisePolicy = (applicationId: string) =>
  useQuery({ queryKey: alertQueryKeys.policy(applicationId), queryFn: () => apiGet<NoisePolicy>(`${applicationBase(applicationId)}/noise-policy`), enabled: Boolean(applicationId) });
export const useUpdateNoisePolicy = (applicationId: string) =>
  useInvalidatingMutation((body: NoisePolicyUpdateBody) => apiPut<NoisePolicy>(`${applicationBase(applicationId)}/noise-policy`, body));
export const usePreviewNoisePolicy = (applicationId: string) =>
  useMutation({ mutationFn: (policySettings: NoisePolicySettings | null) => apiPost<Funnel>(`${applicationBase(applicationId)}/noise-policy/preview`, { policySettings, days: 7 }) });

export const useMaintenanceWindows = (applicationId: string) => useQuery({ queryKey: alertQueryKeys.windows(applicationId), queryFn: () => apiGet<MaintenanceWindow[]>(`${applicationBase(applicationId)}/maintenance-windows`) });
export const useCreateMaintenanceWindow = (applicationId: string) =>
  useInvalidatingMutation((body: MaintenanceWindowBody) => apiPost<MaintenanceWindow>(`${applicationBase(applicationId)}/maintenance-windows`, body));
export const useDeleteMaintenanceWindow = (applicationId: string) =>
  useInvalidatingMutation((windowId: string) => apiDelete(`${applicationBase(applicationId)}/maintenance-windows/${windowId}`));
export const useMuteRules = (applicationId: string) => useQuery({ queryKey: alertQueryKeys.muteRules(applicationId), queryFn: () => apiGet<MuteRule[]>(`${applicationBase(applicationId)}/mute-rules`) });
export const useCreateMuteRule = (applicationId: string) =>
  useInvalidatingMutation((body: MuteRuleBody) => apiPost<MuteRule>(`${applicationBase(applicationId)}/mute-rules`, body));
export const useDeleteMuteRule = (applicationId: string) =>
  useInvalidatingMutation((muteRuleId: string) => apiDelete(`${applicationBase(applicationId)}/mute-rules/${muteRuleId}`));
