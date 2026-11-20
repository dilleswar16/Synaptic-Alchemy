import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString } from "@/api/types/common";

export interface HomeKpis {
  openIncidentsTotal: number;
  openIncidentsByPriority: Record<string, number>;
  activeAlertGroupCount: number;
  alertsLast24Hours: number;
  noiseReductionPercentage: number | null;
  sloTotalCount: number;
  slosAtRiskCount: number;
  investigationsLast24Hours: number;
  meanMinutesToFirstUpdate: number | null;
}

export type HealthStatus = "healthy" | "watch" | "degraded" | "critical";

export interface ApplicationHealthCard {
  applicationId: Identifier;
  applicationName: string;
  applicationCode: string;
  criticalityTier: string;
  healthPercentage: number;
  healthStatus: HealthStatus;
  worstBudgetRemainingPercentage: number | null;
  worstBudgetSloName: string | null;
  availabilitySparkline: number[];
  openIncidentCount: number;
  latestSignalTitle: string | null;
  latestSignalSeverity: string | null;
  componentTypes: string[];
}

export interface LiveIncidentItem {
  incidentId: Identifier;
  investigationId: Identifier | null;
  applicationId: Identifier;
  applicationName: string;
  incidentTitle: string;
  externalIncidentNumber: string | null;
  priority: "P1" | "P2" | "P3" | "P4" | null;
  incidentStatus: string;
  investigationStatus: string | null;
  currentStageName: string | null;
  progressPercent: number | null;
  openedAt: IsoDateTimeString;
}

export interface IntelligenceFeedItem {
  signalId: Identifier;
  applicationId: Identifier;
  applicationName: string;
  signalTitle: string;
  signalSeverity: string;
  forecastBreachAt: IsoDateTimeString | null;
  detectedAt: IsoDateTimeString;
}

export interface MaintenanceWindowItem {
  maintenanceWindowId: Identifier;
  applicationId: Identifier;
  applicationName: string;
  windowName: string;
  startsAt: IsoDateTimeString;
  endsAt: IsoDateTimeString;
}

export interface RecentPostmortemItem {
  postmortemId: Identifier;
  incidentId: Identifier;
  applicationName: string;
  reportTitle: string;
  reportStatus: string;
  createdAt: IsoDateTimeString;
}

export interface HomeDashboard {
  greetingName: string;
  statusSentence: string;
  kpis: HomeKpis;
  applicationCards: ApplicationHealthCard[];
  liveIncidents: LiveIncidentItem[];
  intelligenceFeed: IntelligenceFeedItem[];
  maintenanceWindows: MaintenanceWindowItem[];
  recentPostmortems: RecentPostmortemItem[];
  generatedAt: IsoDateTimeString;
}

export function useHomeDashboard(applicationIds: string[]) {
  return useQuery({
    queryKey: ["dashboard", "home", applicationIds],
    queryFn: () => apiGet<HomeDashboard>("/dashboard/home", { query: { applicationIds: applicationIds.length ? applicationIds : undefined } }),
    refetchInterval: 30_000,
  });
}
