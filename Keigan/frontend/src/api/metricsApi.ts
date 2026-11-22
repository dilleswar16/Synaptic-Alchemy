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
