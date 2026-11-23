import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, apiPut } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (spec 34, 4.7) ─────────────────────────────────────────── */
export type MemoryKeyKind = "service" | "shared_resource" | "alert_rule" | "error_signature" | "change_operation" | "dependency_target" | "incident_category";
export type MemoryCauseSource = "postmortem" | "investigation" | "none";
export type MemoryFixSource = "resolution_note" | "fix_plan" | "hypothesis_fix" | "none";
export type MemoryStaleReason = "older_than_threshold" | "service_removed";
export type MemoryRelevanceVerdict = "relevant" | "not_relevant";
export type MemoryTrust = "correct" | "partially_correct" | "incorrect" | null;

/** The kinds the screen has a label for; a backend test checks this list is the backend's `IncidentMemoryKeyKind`. */
export const memoryKeyKinds: MemoryKeyKind[] = ["service", "shared_resource", "alert_rule", "error_signature", "change_operation", "dependency_target", "incident_category"];
export const memoryCauseSources: MemoryCauseSource[] = ["postmortem", "investigation", "none"];
export const memoryFixSources: MemoryFixSource[] = ["resolution_note", "fix_plan", "hypothesis_fix", "none"];
export const memoryStaleReasons: MemoryStaleReason[] = ["older_than_threshold", "service_removed"];

export interface MatchReason {
  keyKind: MemoryKeyKind;
  displayText: string;
}

export interface SimilarIncident {
  memoryEntryId: Identifier;
  application: { applicationId: Identifier; applicationName: string };
  isSameApplication: boolean;
  incidentId: Identifier | null;
  incidentNumber: string | null;
  incidentTitle: string;
  investigationId: Identifier;
  occurredAt: IsoDateTimeString;
  ageDays: number;
  /** The admin's verdict on that investigation; null = nobody reviewed it. */
  verdict: MemoryTrust;
  /** Null when that investigation's own analysis was marked incorrect: it is not repeated. */
  causeText: string | null;
  causeSource: MemoryCauseSource;
  fixText: string | null;
  fixSource: MemoryFixSource;
  matchReasons: MatchReason[];
  /** An admin marked that past analysis incorrect: listed apart and labelled. */
  isRejected: boolean;
  isStale: boolean;
  staleReasons: MemoryStaleReason[];
  myRelevanceVerdict: MemoryRelevanceVerdict | null;
  canHide: boolean;
}

export interface SimilarIncidentsResult {
  items: SimilarIncident[];
  /** False while the investigation is still running: matching needs its evidence. */
  isAvailable: boolean;
}

export const incidentMemoryQueryKeys = {
  similar: (investigationId: string) => ["incident-memory", "similar", investigationId] as const,
};

export function useSimilarIncidents(investigationId: string | undefined, isEnabled = true) {
  return useQuery({
    queryKey: incidentMemoryQueryKeys.similar(investigationId ?? ""),
    queryFn: ({ signal }) => apiGet<SimilarIncidentsResult>(`/investigations/${investigationId}/similar-incidents`, { signal }),
    enabled: Boolean(investigationId) && isEnabled,
  });
}

export function useSetRelevance(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memoryEntryId, verdict }: { memoryEntryId: Identifier; verdict: MemoryRelevanceVerdict | null }) =>
      verdict
        ? apiPut<void, { verdict: MemoryRelevanceVerdict }>(`/investigations/${investigationId}/similar-incidents/${memoryEntryId}/relevance`, { verdict })
        : apiDelete<void>(`/investigations/${investigationId}/similar-incidents/${memoryEntryId}/relevance`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: incidentMemoryQueryKeys.similar(investigationId) }),
  });
}

export function useHideMemoryEntry(investigationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memoryEntryId, reason }: { memoryEntryId: Identifier; reason: string }) => apiPost<void, { reason: string }>(`/incident-memory/${memoryEntryId}/hide`, { reason }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: incidentMemoryQueryKeys.similar(investigationId) }),
  });
}
