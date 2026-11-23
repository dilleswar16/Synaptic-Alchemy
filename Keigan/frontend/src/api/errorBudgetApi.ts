import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { actionItemQueryKeys } from "@/api/actionItemsApi";
import { apiGet, apiPost, apiPut } from "@/api/httpClient";
import { incidentQueryKeys } from "@/api/incidentsApi";
import type { Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (spec 30, 4.7) ──────────────────────────────────────────── */
export type BudgetImpactState = "provisional" | "final" | "insufficient_data";
export const budgetImpactStates: BudgetImpactState[] = ["provisional", "final", "insufficient_data"];

/** What one incident cost one SLO's error budget, with the inputs. A share that could not be worked out is null, never 0. */
export interface BudgetImpact {
  sloId: Identifier | null;
  sliName: string;
  targetPercentage: number;
  budgetWindowDays: number;
  impactWindowStart: IsoDateTimeString;
  impactWindowEnd: IsoDateTimeString;
  budgetWindowStart: IsoDateTimeString;
  budgetWindowEnd: IsoDateTimeString;
  badEventCount: number;
  impactTotalEventCount: number;
  windowTotalEventCount: number;
  budgetEventCount: number | null;
  budgetSharePercent: number | null;
  dataCoveragePercent: number;
  isServiceMatched: boolean;
  impactState: BudgetImpactState;
  evaluatedAt: IsoDateTimeString;
}

export interface BudgetPolicySummary {
  isEnabled: boolean;
  singleIncidentThresholdPercent: number;
  minimumDataCoveragePercent: number;
}

export interface IncidentBudgetImpact {
  incidentId: Identifier;
  policy: BudgetPolicySummary;
  impacts: BudgetImpact[];
  /** The policy breach of this incident, when there is one. */
  breach: ErrorBudgetBreach | null;
}

export const errorBudgetQueryKeys = {
  all: ["error-budget"] as const,
  incidentImpact: (incidentId: string) => ["error-budget", "incident", incidentId] as const,
};

/* ── Hooks ─────────────────────────────────────────────────────────── */
export const useIncidentBudgetImpact = (incidentId: string | undefined) =>
  useQuery({
    queryKey: errorBudgetQueryKeys.incidentImpact(incidentId ?? ""),
    enabled: Boolean(incidentId),
    queryFn: ({ signal }) => apiGet<IncidentBudgetImpact>(`/incidents/${incidentId}/budget-impact`, { signal }),
  });

/* ── The policy and its breaches (spec 30) ─────────────────────────── */
export type BreachKind = "single_incident" | "outage_class" | "budget_exhausted";
export type RequirementStatus = "open" | "met" | "waived" | "ended";
export const breachKinds: BreachKind[] = ["single_incident", "outage_class", "budget_exhausted"];
export const requirementStatuses: RequirementStatus[] = ["open", "met", "waived", "ended"];

export interface ErrorBudgetBreach {
  breachId: Identifier;
  applicationId: Identifier;
  applicationName: string;
  breachKind: BreachKind;
  incidentId: Identifier | null;
  incidentReference: string | null;
  sloId: Identifier | null;
  sliName: string | null;
  recurrenceCategory: string | null;
  recurrenceServiceName: string | null;
  measuredSharePercent: number | null;
  thresholdPercent: number | null;
  windowDays: number;
  detectedAt: IsoDateTimeString;
  requirementStatus: RequirementStatus;
  isProvisional: boolean;
  qualifyingActionItemId: Identifier | null;
  waivedBy: string | null;
  waiverReasonText: string | null;
  /** The team's own agreed response (budget_exhausted only). */
  guidanceText: string | null;
  canWaive: boolean;
  canAddActionItem: boolean;
}

export interface ErrorBudgetPolicy {
  applicationId: Identifier;
  isEnabled: boolean;
  singleIncidentThresholdPercent: number;
  outageClassThresholdPercent: number;
  outageClassWindowDays: number;
  usesDefault: { singleIncidentThreshold: boolean; outageClassThreshold: boolean; outageClassWindow: boolean };
  defaults: { singleIncidentThresholdPercent: number; outageClassThresholdPercent: number; outageClassWindowDays: number };
  maximumOutageClassWindowDays: number;
  exhaustedBudgetGuidanceText: string | null;
  guidanceMaximumCharacters: number;
  canEdit: boolean;
  updatedAt: IsoDateTimeString | null;
  updatedBy: string | null;
}

/** A null threshold or window means "use the default". */
export interface ErrorBudgetPolicyBody {
  isEnabled: boolean;
  singleIncidentThresholdPercent: number | null;
  outageClassThresholdPercent: number | null;
  outageClassWindowDays: number | null;
  exhaustedBudgetGuidanceText: string | null;
}

export interface BreachFilters {
  applicationIds: string[];
  statuses?: RequirementStatus[];
  kinds?: BreachKind[];
}

export const useErrorBudgetPolicy = (applicationId: string) =>
  useQuery({ queryKey: ["error-budget", "policy", applicationId] as const, queryFn: ({ signal }) => apiGet<ErrorBudgetPolicy>(`/applications/${applicationId}/error-budget-policy`, { signal }) });

export const useErrorBudgetBreaches = (filters: BreachFilters) =>
  useQuery({
    queryKey: ["error-budget", "breaches", filters] as const,
    queryFn: ({ signal }) => apiGet<ErrorBudgetBreach[]>("/error-budget-breaches", { signal, query: { applicationIds: filters.applicationIds.join(",") || undefined, statuses: filters.statuses?.join(",") || undefined, kinds: filters.kinds?.join(",") || undefined } }),
  });

function useBudgetMutation<Variables, Result>(mutationFunction: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: mutationFunction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: errorBudgetQueryKeys.all });
      await queryClient.invalidateQueries({ queryKey: actionItemQueryKeys.all });
      await queryClient.invalidateQueries({ queryKey: incidentQueryKeys.all });
    },
  });
}

export const useSaveErrorBudgetPolicy = (applicationId: string) =>
  useBudgetMutation((body: ErrorBudgetPolicyBody) => apiPut<ErrorBudgetPolicy, ErrorBudgetPolicyBody>(`/applications/${applicationId}/error-budget-policy`, body));
export const useWaiveBreach = () => useBudgetMutation((variables: { breachId: string; reasonText: string }) => apiPost<ErrorBudgetBreach, { reasonText: string }>(`/error-budget-breaches/${variables.breachId}/waive`, { reasonText: variables.reasonText }));
