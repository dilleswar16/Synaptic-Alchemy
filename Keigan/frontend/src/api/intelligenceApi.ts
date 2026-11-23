import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (doc 05 §9) ─────────────────────────────────────────────── */
export type DetectorName = "seasonal_anomaly" | "error_budget_exhaustion" | "saturation_trend" | "new_error_pattern" | "recurring_incident" | "change_risk";
export type SignalSeverity = "info" | "warning" | "critical";
export type SignalStatus = "open" | "acknowledged" | "dismissed" | "converted_to_incident" | "expired";

export interface PredictiveSignal {
  predictiveSignalId: Identifier;
  applicationId: Identifier;
  applicationName: string | null;
  serviceId: string | null;
  serviceName: string | null;
  detectorName: DetectorName;
  signalSeverity: SignalSeverity;
  signalTitle: string;
  explanationMarkdown: string | null;
  metricName: string | null;
  observedValue: number | null;
  expectedValue: number | null;
  deviationScore: number | null;
  forecastBreachAt: IsoDateTimeString | null;
  confidenceScore: number;
  evidenceSeries: Array<{ t: string; v: number }>;
  signalStatus: SignalStatus;
  detectedAt: IsoDateTimeString;
}
export interface IntelligenceReportSummary {
  intelligenceReportId: Identifier;
  applicationId: Identifier;
  applicationName: string | null;
  reportType: "proactive_alert" | "weekly_digest";
  reportTitle: string;
  reportPeriodStart: IsoDateTimeString;
  reportPeriodEnd: IsoDateTimeString;
  overallHealthScore: number | null;
  sentAt: IsoDateTimeString | null;
  recipientCount: number;
  /** A weekly digest the team went through (spec 31). */
  reviewedAt: IsoDateTimeString | null;
  reviewedBy: string | null;
  reviewNote: string | null;
  createdAt: IsoDateTimeString;
}
export interface IntelligenceReport extends IntelligenceReportSummary {
  reportMarkdown: string | null;
  reportSections: Record<string, unknown>;
  recipientAddresses: string[];
}
export interface HealthScoreTrend {
  applicationId: Identifier;
  currentHealthScore: number | null;
  points: Array<{ day: string; healthScore: number; sloComponent: number; signalComponent: number; incidentComponent: number }>;
}
export interface SignalFilters {
  applicationIds: ReadonlyArray<string>;
  severities?: SignalSeverity[];
  detectors?: DetectorName[];
  statuses?: SignalStatus[];
}

export const intelligenceQueryKeys = {
  signals: (filters: SignalFilters) => ["predictive-signals", filters] as const,
  reports: (applicationId: string | null) => ["intelligence-reports", applicationId] as const,
  report: (reportId: string | null) => ["intelligence-report", reportId] as const,
  trend: (applicationId: string | null, days: number) => ["health-score-trend", applicationId, days] as const,
};

export const useSignals = (filters: SignalFilters) =>
  useQuery({
    queryKey: intelligenceQueryKeys.signals(filters),
    refetchInterval: 60_000,
    queryFn: () =>
      apiGet<PredictiveSignal[]>("/predictive-signals", { query: { applicationIds: filters.applicationIds, severities: filters.severities, detectors: filters.detectors, statuses: filters.statuses } }),
  });
export const useUpdateSignalStatus = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { signalId: string; signalStatus: "open" | "acknowledged" | "dismissed" }) =>
      apiPatch<PredictiveSignal>(`/predictive-signals/${variables.signalId}`, { signalStatus: variables.signalStatus }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["predictive-signals"] }),
  });
};
export const useInvestigateSignal = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) => apiPost<{ investigationId: string; predictiveSignalId: string }>(`/predictive-signals/${signalId}/investigate`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["predictive-signals"] }),
  });
};
export const useIntelligenceReports = (applicationId: string | null) =>
  useQuery({ queryKey: intelligenceQueryKeys.reports(applicationId), queryFn: () => apiGet<IntelligenceReportSummary[]>("/intelligence-reports", { query: { applicationId } }) });
export const useIntelligenceReport = (reportId: string | null) =>
  useQuery({ queryKey: intelligenceQueryKeys.report(reportId), enabled: Boolean(reportId), queryFn: () => apiGet<IntelligenceReport>(`/intelligence-reports/${reportId}`) });
export const useGenerateReport = (applicationId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { reportType: "weekly_digest" | "proactive_alert"; sendToStakeholders: boolean }) =>
      apiPost<AcceptedJob>(`/applications/${applicationId}/intelligence-reports/generate`, variables),
    onSuccess: () => {
      window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: ["intelligence-reports"] }), 4_000);
    },
  });
};
export const useReviewReport = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { reportId: string; noteText: string | null }) => apiPost<IntelligenceReport>(`/intelligence-reports/${variables.reportId}/review`, { noteText: variables.noteText }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["intelligence-reports"] }),
  });
};
export const useHealthScoreTrend = (applicationId: string | null, days = 30) =>
  useQuery({ queryKey: intelligenceQueryKeys.trend(applicationId, days), enabled: Boolean(applicationId), queryFn: () => apiGet<HealthScoreTrend>(`/applications/${applicationId}/health-score-trend`, { query: { days } }) });
