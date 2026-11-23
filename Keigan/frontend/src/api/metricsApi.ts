import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString } from "@/api/types/common";

/** Reliability metrics (GET /api/metrics/overview). A figure that could not be computed is null, never 0; every figure carries its sample size. */

export interface MetricStat {
  sampleCount: number;
  median: number | null;
  p90: number | null;
  mean: number | null;
  /** Items that could not give a value (no start, no end, or an end before the start). Durations only. */
  excludedCount: number;
}

export interface PriorityCount {
  priority: string;
  openedCount: number;
  resolvedCount: number;
}

export interface InvestigationStatusCount {
  status: string;
  count: number;
}

export interface Ratings {
  ratedCount: number;
  correctCount: number;
  partiallyCorrectCount: number;
  incorrectCount: number;
  minimumSample: number;
  /** Percent marked correct among rated investigations; null while fewer than `minimumSample` were rated. */
  shareCorrect: number | null;
}

/** How the memory of past incidents (spec 34) is used and judged in the period. */
/** What the people who resolved incidents in the period said about how far Keigan's analysis helped. */
export interface KeiganHelpMetrics {
  resolvedCount: number;
  answeredCount: number;
  answers: { answer: string; count: number }[];
  minimumSample: number;
  /** Percent of answers that said "found the cause"; null while fewer than `minimumSample` answers were given. */
  shareFoundCause: number | null;
  timeToResolveWithHelp: MetricStat;
  timeToResolveWithoutHelp: MetricStat;
}

export interface MemoryMetrics {
  completedInvestigationCount: number;
  /** Completed investigations whose AI was shown at least one confirmed past incident. */
  investigationsGivenAHintCount: number;
  relevanceAnswerCount: number;
  relevantCount: number;
  notRelevantCount: number;
  minimumSample: number;
  /** Percent of answers that said "relevant"; null while fewer than `minimumSample` answers were given. */
  shareRelevant: number | null;
  /** Past incidents an admin hid in the period. */
  hiddenEntryCount: number;
}

export interface CostSummary {
  isConfigured: boolean;
  totalEstimatedCost: number | null;
  perInvestigation: MetricStat;
  unpricedModels: string[];
  unpricedInvestigationCount: number;
}

export interface AiUsage {
  investigationCount: number;
  callCount: number;
  failedCallCount: number;
  inputTokens: MetricStat;
  outputTokens: MetricStat;
  latencyMilliseconds: MetricStat;
  cost: CostSummary;
}

export interface MetricsSummary {
  incidentsOpenedCount: number;
  incidentsResolvedCount: number;
  byPriority: PriorityCount[];
  timeToDetect: MetricStat;
  timeToFirstUpdate: MetricStat;
  timeToResolve: MetricStat;
  timeToConclusion: MetricStat;
  investigationCount: number;
  investigationsByStatus: InvestigationStatusCount[];
  ratings: Ratings;
  memory: MemoryMetrics;
  keiganHelp: KeiganHelpMetrics;
  aiUsage: AiUsage;
}

export interface ApplicationMetrics extends MetricsSummary {
  applicationId: Identifier;
  applicationName: string;
  applicationCode: string;
}

export interface WeeklyPoint {
  weekStart: IsoDateTimeString;
  incidentsOpenedCount: number;
  incidentsResolvedCount: number;
  timeToResolve: MetricStat;
  timeToConclusion: MetricStat;
  tokensPerInvestigation: MetricStat;
}

export interface NotAvailableMetric {
  metric: string;
  reason: string;
}

export interface MetricsOverview {
  periodStart: IsoDateTimeString;
  periodEnd: IsoDateTimeString;
  applicationId: Identifier | null;
  minimumRatingSample: number;
  maximumWindowDays: number;
  summary: MetricsSummary;
  applications: ApplicationMetrics[];
  weeklyTrend: WeeklyPoint[];
  notAvailable: NotAvailableMetric[];
  definitionKeys: string[];
  generatedAt: IsoDateTimeString;
}

export function useMetricsOverview(options: { applicationId: string | null; days: number }) {
  return useQuery({
    queryKey: ["metrics", "overview", options.applicationId, options.days],
    queryFn: () => apiGet<MetricsOverview>("/metrics/overview", { query: { applicationId: options.applicationId ?? undefined, days: options.days } }),
    staleTime: 60_000,
  });
}
