import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString, PagedResult } from "@/api/types/common";

export interface SettingsGroup {
  groupKey: string;
  groupTitle: string;
  settings: Record<string, unknown>;
}

export interface IntegrationStatus {
  integrationKey: string;
  mode: string;
  isSimulated: boolean;
  isConfigured: boolean;
  summary: string;
}

export interface ModelCapabilities {
  modelTier: "fast" | "deep" | "vision";
  modelName: string;
  toolCalling: "native" | "prompted_json" | "none";
  parallelToolCalls: boolean;
  streamsText: boolean;
  streamsToolRequests: boolean;
  supportsToolChoiceNone: boolean;
  supportsTemperature: boolean;
  reportsStreamUsage: boolean;
  maxContextTokens: number;
}

export interface ConformanceReportSummary {
  generatedAt: IsoDateTimeString;
  passed: boolean;
  providerName: string;
  modelName: string;
  toolCallingMode: string;
  scenarioCount: number;
  passedCount: number;
}

export interface AdministrationSettings {
  environment: string;
  productVersion: string;
  groups: SettingsGroup[];
  integrations: IntegrationStatus[];
  keiganIdentity: { managedIdentityObjectId: string; managedIdentityClientId: string; managedIdentityDisplayName: string; multiTenantAppClientId: string | null };
  simulationControlsAvailable: boolean;
  modelCapabilities: ModelCapabilities[];
  lastConformanceReport: ConformanceReportSummary | null;
}

export interface ConnectionTestOutcome {
  integration: string;
  succeeded: boolean;
  message: string;
  details: Record<string, unknown>;
  testedAt: IsoDateTimeString;
}

export interface UsageBucket {
  bucketKey: string;
  bucketLabel: string;
  callCount: number;
  inputTokenCount: number;
  outputTokenCount: number;
  estimatedCost: number;
}

export interface Usage {
  periodStart: IsoDateTimeString;
  periodEnd: IsoDateTimeString;
  groupBy: string;
  buckets: UsageBucket[];
  totalCallCount: number;
  totalInputTokenCount: number;
  totalOutputTokenCount: number;
  totalEstimatedCost: number;
  averageTokensPerInvestigation: number | null;
  failedCallCount: number;
}

export interface AuditEvent {
  auditEventId: Identifier;
  actorUserPrincipalName: string;
  actionName: string;
  targetEntityType: string | null;
  targetEntityId: string | null;
  applicationId: string | null;
  actionDetails: Record<string, unknown> | null;
  occurredAt: IsoDateTimeString;
}

export interface AuditFilters {
  actor?: string;
  action?: string;
  page: number;
  pageSize: number;
}

export interface BackgroundJobSummary {
  jobId: Identifier;
  jobType: string;
  jobStatus: string;
  attemptCount: number;
  maximumAttemptCount: number;
  lastErrorMessage: string | null;
  createdAt: IsoDateTimeString;
  finishedAt: IsoDateTimeString | null;
}

export interface JobStats {
  countsByStatus: Record<string, number>;
  countsByType: Record<string, number>;
  deadLetters: BackgroundJobSummary[];
  recentJobs: BackgroundJobSummary[];
}

export interface SimulationScenario {
  scenarioKey: string;
  title: string;
  category: string;
  serviceTypes: string;
}

export interface OutboxDeliverySummary {
  notificationDeliveryId: Identifier;
  applicationName: string | null;
  notificationType: string;
  deliveryChannel: string;
  recipientAddress: string;
  subjectLine: string | null;
  deliveryStatus: string;
  attemptCount: number;
  lastErrorMessage: string | null;
  createdAt: IsoDateTimeString;
  sentAt: IsoDateTimeString | null;
}

export interface OutboxDeliveryDetail extends OutboxDeliverySummary {
  bodyHtml: string | null;
  bodyText: string | null;
}

export const administrationQueryKeys = {
  settings: ["administration", "settings"] as const,
  usage: (groupBy: string, days: number) => ["administration", "usage", groupBy, days] as const,
  audit: (filters: AuditFilters) => ["administration", "audit", filters] as const,
  jobs: ["administration", "jobs"] as const,
  scenarios: ["administration", "scenarios"] as const,
  outbox: (page: number) => ["administration", "outbox", page] as const,
  outboxDelivery: (deliveryId: string) => ["administration", "outbox", "delivery", deliveryId] as const,
};

export function useAdministrationSettings() {
  return useQuery({ queryKey: administrationQueryKeys.settings, queryFn: () => apiGet<AdministrationSettings>("/administration/settings") });
}

export function useConnectionTest() {
  return useMutation({ mutationFn: (integration: string) => apiPost<ConnectionTestOutcome, undefined>(`/administration/connection-tests/${integration}`, undefined) });
}

export function useUsage(groupBy: "day" | "application" | "feature", days: number) {
  return useQuery({
    queryKey: administrationQueryKeys.usage(groupBy, days),
    queryFn: () => apiGet<Usage>("/administration/usage", { query: { groupBy, from: new Date(Date.now() - days * 86_400_000).toISOString() } }),
  });
}

export function useAuditEvents(filters: AuditFilters) {
  return useQuery({
    queryKey: administrationQueryKeys.audit(filters),
    queryFn: () => apiGet<PagedResult<AuditEvent>>("/administration/audit-events", { query: { actor: filters.actor || undefined, action: filters.action || undefined, page: filters.page, pageSize: filters.pageSize } }),
    placeholderData: keepPreviousData,
  });
}

export function useJobStats() {
  return useQuery({ queryKey: administrationQueryKeys.jobs, queryFn: () => apiGet<JobStats>("/administration/jobs"), refetchInterval: 15_000 });
}

export function useRetryJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiPost<BackgroundJobSummary, undefined>(`/administration/jobs/${jobId}/retry`, undefined),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: administrationQueryKeys.jobs }),
  });
}

export function useSimulationScenarios(isEnabled: boolean) {
  return useQuery({ queryKey: administrationQueryKeys.scenarios, queryFn: () => apiGet<SimulationScenario[]>("/administration/simulation/scenarios"), enabled: isEnabled });
}

export function useTriggerScenario() {
  return useMutation({
    mutationFn: ({ scenarioKey, applicationId }: { scenarioKey: string; applicationId: string }) =>
      apiPost<{ servicenowIncidentNumber?: string; title: string }, { applicationId: string }>(`/administration/simulation/scenarios/${scenarioKey}`, { applicationId }),
  });
}

export function useOutbox(page: number) {
  return useQuery({
    queryKey: administrationQueryKeys.outbox(page),
    queryFn: () => apiGet<PagedResult<OutboxDeliverySummary>>("/outbox", { query: { page, pageSize: 25 } }),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useOutboxDelivery(deliveryId: string | null) {
  return useQuery({ queryKey: administrationQueryKeys.outboxDelivery(deliveryId ?? ""), queryFn: () => apiGet<OutboxDeliveryDetail>(`/outbox/${deliveryId}`), enabled: Boolean(deliveryId) });
}
