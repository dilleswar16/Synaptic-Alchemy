import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { AcceptedJob, Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (doc 05 §9) ─────────────────────────────────────────────── */
export type SloStatus = "healthy" | "at_risk" | "breached" | "no_data";

export interface SloSummary {
  sloId: Identifier;
  sliId: Identifier;
  applicationId: Identifier;
  applicationName: string | null;
  serviceId: string | null;
  serviceName: string | null;
  sliName: string;
  sliKind: string | null;
  isHeadline: boolean;
  isApproximate: boolean;
  targetPercentage: number;
  rollingWindowDays: number;
  compliancePercentage: number | null;
  errorBudgetRemainingPercentage: number | null;
  errorBudgetRemainingMinutes: number | null;
  errorBudgetTotalMinutes: number | null;
  burnRateOneHour: number | null;
  burnRateSixHours: number | null;
  status: SloStatus;
  sparkline: number[];
}

export interface SeriesPoint {
  timestamp: IsoDateTimeString;
  sliPercentage: number | null;
  goodEventCount: number;
  totalEventCount: number;
  budgetRemainingPercentage: number | null;
}
export interface SloSeries {
  sloId: Identifier;
  sliName: string;
  targetPercentage: number;
  rollingWindowDays: number;
  resolutionMinutes: number;
  points: SeriesPoint[];
  compliancePercentage: number | null;
}

export interface HeatmapRow {
  applicationId: Identifier;
  applicationName: string;
  sloId: Identifier;
  rowLabel: string;
  serviceName: string | null;
  targetPercentage: number;
  overallCompliancePercentage: number | null;
  status: SloStatus;
  cells: Array<{ date: string; compliancePercentage: number | null }>;
}
export interface EcosystemHeatmap { days: number; dates: string[]; rows: HeatmapRow[] }

export interface SliProposal {
  proposalKey: string;
  catalogEntryKey: string;
  serviceId: Identifier;
  serviceName: string;
  sliName: string;
  sliKind: string;
  explanation: string;
  sourceChip: string;
  goodTotalDefinition: string | null;
  isEnabledByDefault: boolean;
  isAvailable: boolean;
  disabledReason: string | null;
  measuredPercentage: number | null;
  eventCount: number;
  sparkline: number[];
  proposedTargetPercentage: number | null;
  proposedLatencyThresholdMilliseconds: number | null;
  rollingWindowDays: number;
  errorBudgetMinutes: number | null;
  errorBudgetText: string | null;
  isApproximate: boolean;
  isHeadline: boolean;
  warning: string | null;
  alreadyAccepted: boolean;
}
export interface ServiceProposalGroup {
  serviceId: Identifier;
  serviceName: string;
  serviceType: string;
  proposals: SliProposal[];
  supportingSignals: Array<{ signalKey: string; signalName: string; description: string | null }>;
}
export interface SloProposals {
  applicationId: Identifier;
  measurementStatus: "not_started" | "measuring" | "ready" | "failed";
  progressStage: string | null;
  errorMessage: string | null;
  suggestedSloCount: number;
  serviceCount: number;
  headlineProposal: SliProposal | null;
  groups: ServiceProposalGroup[];
  explanation: string;
}
export interface AcceptedProposalBody {
  catalogEntryKey: string;
  serviceId: string;
  targetPercentage: number;
  rollingWindowDays: 7 | 28 | 30;
  latencyThresholdMilliseconds?: number | null;
}
export interface Sli {
  sliId: Identifier;
  serviceName: string | null;
  sliName: string;
  sliKind: string;
  isEnabled: boolean;
  catalogEntryKey: string;
  slo: { sloId: string; targetPercentage: number; rollingWindowDays: number } | null;
}
export interface CustomSliBody {
  serviceId?: string | null;
  sliName: string;
  sliKind: "availability" | "latency";
  dataSourceKind: "log_query";
  queryDefinition: { kql: string };
  latencyThresholdMilliseconds?: number | null;
  targetPercentage?: number | null;
  rollingWindowDays: 7 | 28 | 30;
}

/* ── Hooks ─────────────────────────────────────────────────────────── */
export const sloQueryKeys = {
  all: ["slo"] as const,
  dashboard: (applicationIds: string[]) => ["slo", "dashboard", applicationIds] as const,
  series: (sloId: string, resolution: number) => ["slo", "series", sloId, resolution] as const,
  heatmap: (days: number) => ["slo", "heatmap", days] as const,
  proposals: (applicationId: string) => ["slo", "proposals", applicationId] as const,
  slis: (applicationId: string) => ["slo", "slis", applicationId] as const,
};

export const useSloDashboard = (applicationIds: string[]) =>
  useQuery({ queryKey: sloQueryKeys.dashboard(applicationIds), refetchInterval: 60_000, queryFn: () => apiGet<SloSummary[]>("/slo-dashboard", { query: { applicationIds } }) });
export const useSloSeries = (sloId: string | null, resolutionMinutes: number) =>
  useQuery({ queryKey: sloQueryKeys.series(sloId ?? "", resolutionMinutes), enabled: Boolean(sloId), queryFn: () => apiGet<SloSeries>(`/slos/${sloId}/series`, { query: { resolution: resolutionMinutes } }) });
export const useEcosystemHeatmap = (days: number) => useQuery({ queryKey: sloQueryKeys.heatmap(days), queryFn: () => apiGet<EcosystemHeatmap>("/slo-ecosystem-heatmap", { query: { days } }) });

export const useSloProposals = (applicationId: string) =>
  useQuery({
    queryKey: sloQueryKeys.proposals(applicationId),
    queryFn: () => apiGet<SloProposals>(`/applications/${applicationId}/slo-proposals`),
    refetchInterval: (query) => (query.state.data?.measurementStatus === "measuring" ? 2_000 : false),
  });

function useSloMutation<Variables, Result>(mutationFunction: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: mutationFunction, onSuccess: () => queryClient.invalidateQueries({ queryKey: sloQueryKeys.all }) });
}
export const useMeasureSloProposals = (applicationId: string) => useSloMutation(() => apiPost<AcceptedJob>(`/applications/${applicationId}/slo-proposals/measure`));
export const useAcceptSloProposals = (applicationId: string) =>
  useSloMutation((acceptedProposals: AcceptedProposalBody[]) => apiPost<{ acceptedCount: number }>(`/applications/${applicationId}/slo-proposals/accept`, { acceptedProposals }));
export const useSlis = (applicationId: string) => useQuery({ queryKey: sloQueryKeys.slis(applicationId), queryFn: () => apiGet<Sli[]>(`/applications/${applicationId}/slis`) });
export const useCreateCustomSli = (applicationId: string) => useSloMutation((body: CustomSliBody) => apiPost<Sli>(`/applications/${applicationId}/slis`, body));
export const useUpdateSlo = () => useSloMutation((variables: { sloId: string; targetPercentage?: number; rollingWindowDays?: number }) => apiPatch(`/slos/${variables.sloId}`, variables));
export const useDeleteSli = () => useSloMutation((sliId: string) => apiDelete(`/slis/${sliId}`));
