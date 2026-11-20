import type { IncidentStatus } from "@/api/incidentsApi";
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
