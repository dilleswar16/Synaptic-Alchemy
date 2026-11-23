import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/httpClient";
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
