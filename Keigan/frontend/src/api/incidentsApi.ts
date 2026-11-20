import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, ApiError } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString, PagedResult, Priority } from "@/api/types/common";

/* ── Types (doc 05 §6) ─────────────────────────────────────────────── */
export type IncidentStatus = "new" | "investigating" | "identified" | "resolved" | "closed";
export type IncidentSource = "servicenow" | "alert" | "manual";

export interface ApplicationReference {
  applicationId: Identifier;
  applicationCode: string;
  applicationName: string;
}

export interface IncidentSummary {
  incidentId: Identifier;
  application: ApplicationReference;
  incidentSource: IncidentSource;
  externalIncidentNumber: string | null;
  incidentTitle: string;
  servicenowPriority: Priority | null;
  keiganPriority: Priority | null;
  incidentCategory: string | null;
  incidentStatus: IncidentStatus;
  externalState: string | null;
  affectedServiceNames: string[];
  assignmentGroupName: string | null;
  openedAt: IsoDateTimeString;
  detectedByKeiganAt: IsoDateTimeString;
  resolvedAt: IsoDateTimeString | null;
  durationMinutes: number;
  keiganConfidence: number | null;
  latestInvestigationId: Identifier | null;
  latestInvestigationStatus: string | null;
  servicenowUrl: string | null;
}

export interface InvestigationBrief {
  investigationId: Identifier;
  investigationStatus: string;
  currentStageName: string;
  progressPercent: number;
  overallConfidenceScore: number | null;
  executiveSummary: string | null;
  investigationTrigger: string;
  startedAt: IsoDateTimeString | null;
  completedAt: IsoDateTimeString | null;
}

export interface IncidentDetail extends IncidentSummary {
  incidentDescription: string | null;
  priorityRationale: string | null;
  servicenowImpact: string | null;
  servicenowUrgency: string | null;
  firstUpdateSentAt: IsoDateTimeString | null;
  closedAt: IsoDateTimeString | null;
  latestInvestigation: InvestigationBrief | null;
  postmortemId: Identifier | null;
  postmortemStatus: string | null;
}

export interface IncidentFilters {
  applicationIds?: string[];
  priorities?: string[];
  statuses?: string[];
  sources?: string[];
  search?: string;
  onlyMine?: boolean;
  from?: string;
  to?: string;
  page?: number;
  pageSize?: number;
}

export interface Postmortem {
  postmortemId: Identifier;
  incidentId: Identifier;
  investigationId: Identifier | null;
  reportTitle: string;
  reportMarkdown: string | null;
  reportSections: Record<string, unknown> | null;
  languageCode: string;
  reportStatus: "generating" | "draft" | "final" | "failed";
  generationTrigger: string;
  finalizedByUserPrincipalName: string | null;
  finalizedAt: IsoDateTimeString | null;
  sentAt: IsoDateTimeString | null;
  createdAt: IsoDateTimeString;
  updatedAt: IsoDateTimeString;
}

export interface PostmortemSendResult {
  postmortem: Postmortem;
  deliveriesQueued: number;
  message: string;
}

/* ── Query keys and hooks ──────────────────────────────────────────── */
export const incidentQueryKeys = {
  all: ["incidents"] as const,
  list: (filters: IncidentFilters) => ["incidents", "list", filters] as const,
  detail: (incidentId: string) => ["incidents", "detail", incidentId] as const,
  postmortem: (incidentId: string) => ["incidents", "postmortem", incidentId] as const,
};

export function useIncidents(filters: IncidentFilters, options: { refetchIntervalMilliseconds?: number } = {}) {
  return useQuery({
    queryKey: incidentQueryKeys.list(filters),
    queryFn: ({ signal }) => apiGet<PagedResult<IncidentSummary>>("/incidents", { query: { ...filters }, signal }),
    placeholderData: keepPreviousData,
    refetchInterval: options.refetchIntervalMilliseconds ?? 15_000,
  });
}

export function useIncident(incidentId: string | undefined) {
  return useQuery({
    queryKey: incidentQueryKeys.detail(incidentId ?? ""),
    queryFn: ({ signal }) => apiGet<IncidentDetail>(`/incidents/${incidentId}`, { signal }),
    enabled: Boolean(incidentId),
    refetchInterval: 20_000,
  });
}

export function useResolveIncident(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: { resolutionNote?: string; generatePostmortem: boolean }) => apiPost<IncidentDetail, typeof request>(`/incidents/${incidentId}/resolve`, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["investigations"] });
    },
  });
}

/** The postmortem of an incident, or `null` when none was written yet. Polls while it is being generated. */
export function usePostmortem(incidentId: string | undefined) {
  return useQuery({
    queryKey: incidentQueryKeys.postmortem(incidentId ?? ""),
    queryFn: async ({ signal }) => {
      try {
        return await apiGet<Postmortem | null>(`/incidents/${incidentId}/postmortem`, { signal });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: Boolean(incidentId),
    refetchInterval: (query) => (query.state.data?.reportStatus === "generating" ? 2_000 : false),
  });
}

export function useGeneratePostmortem(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<AcceptedJob>(`/incidents/${incidentId}/postmortem/generate`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.postmortem(incidentId) }),
  });
}

export function useUpdatePostmortem(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ postmortemId, ...request }: { postmortemId: string; reportTitle?: string; reportMarkdown?: string }) =>
      apiPatch<Postmortem, typeof request>(`/postmortems/${postmortemId}`, request),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.postmortem(incidentId) }),
  });
}

export function useFinalizePostmortem(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (postmortemId: string) => apiPost<Postmortem>(`/postmortems/${postmortemId}/finalize`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.postmortem(incidentId) });
      void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.detail(incidentId) });
    },
  });
}

export function useSendPostmortem(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (postmortemId: string) => apiPost<PostmortemSendResult>(`/postmortems/${postmortemId}/send`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: incidentQueryKeys.postmortem(incidentId) }),
  });
}
