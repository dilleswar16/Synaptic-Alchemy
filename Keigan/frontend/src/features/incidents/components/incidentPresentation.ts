import type { IncidentStatus, IncidentSummary } from "@/api/incidentsApi";
import type { StatusTone } from "@/components/ui/toneStyles";

export const incidentStatusOrder: IncidentStatus[] = ["new", "investigating", "identified", "resolved", "closed"];

export const incidentStatusTone: Record<IncidentStatus, StatusTone> = {
  new: "danger",
  investigating: "info",
  identified: "ai",
  resolved: "success",
  closed: "neutral",
};

export const incidentSources = ["servicenow", "alert", "manual"] as const;
export const incidentPriorities = ["P1", "P2", "P3", "P4"] as const;

export const isOpenIncident = (status: IncidentStatus) => status === "new" || status === "investigating" || status === "identified";

/** Open incidents first, then newest detection first; resolved and closed incidents follow in the same order. */
export const orderOpenFirst = (incidents: IncidentSummary[]) =>
  [...incidents].sort((first, second) => Number(isOpenIncident(second.incidentStatus)) - Number(isOpenIncident(first.incidentStatus)) || Date.parse(second.detectedByKeiganAt) - Date.parse(first.detectedByKeiganAt));
