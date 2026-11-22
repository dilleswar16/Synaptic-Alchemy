import type { AnalysisPerspective, EvidenceCheckOutcome, HypothesisStateName, InvestigationOutcomeCode, InvestigationStatus, SignalStrength } from "@/api/investigationsApi";
import type { StatusTone } from "@/components/ui/toneStyles";

export const investigationStatusTone: Record<InvestigationStatus, StatusTone> = {
  queued: "neutral",
  running: "info",
  completed: "success",
  completed_evidence_only: "warning",
  failed: "danger",
  cancelled: "neutral",
};

export const signalStrengthTone: Record<SignalStrength, StatusTone> = { high: "danger", medium: "warning", low: "neutral" };

export const perspectiveOrder: AnalysisPerspective[] = ["application", "dependencies", "infrastructure"];

export const investigationStages = ["triage", "context", "evidence", "hypotheses", "synthesis", "communications"] as const;

/** Maps a Keigan service type to the TopologyGraph node type (icon). */
export function topologyNodeType(serviceType: string): string {
  const mapping: Record<string, string> = {
    aks: "aks",
    function_app: "functions",
    app_service: "app_service",
    logic_app: "logic_apps",
    api_management: "api_management",
    data_factory: "data_factory",
    sql_database: "database",
    saas_service: "saas",
    mainframe_subsystem: "mainframe",
    batch_job_stream: "mainframe",
    server: "hardware",
    network_appliance: "hardware",
  };
  return mapping[serviceType] ?? "service";
}

/** Evidence, runbook and knowledge citations such as [E3] that appear in AI-written markdown. */
/** Tone of the outcome chip: a result, never an alarm ("cause not visible" is information, not danger). */
export const outcomeTone: Record<Exclude<InvestigationOutcomeCode, "not_recorded">, StatusTone> = { cause_identified: "success", inconclusive: "warning", cause_not_visible: "info" };
export const hypothesisStateTone: Record<HypothesisStateName, StatusTone> = { supported: "success", ruled_out: "neutral", inconclusive: "warning" };
export const checkOutcomeTone: Record<EvidenceCheckOutcome, StatusTone> = { signal: "info", no_signal: "neutral", not_checked: "warning" };

export function extractCitationCodes(markdown: string | null | undefined): string[] {
  const codes = new Set<string>();
  for (const match of (markdown ?? "").matchAll(/\[(E\d{1,3})\]/g)) {
    const code = match[1];
    if (code) codes.add(code);
  }
  return [...codes].sort((first, second) => Number(first.slice(1)) - Number(second.slice(1)));
}

export function evidenceElementId(evidenceCode: string): string {
  return `evidence-${evidenceCode}`;
}

export function runbookElementId(runbookId: string): string {
  return `runbook-${runbookId}`;
}

export function communicationLanguageLabel(languageCode: string): string {
  const labels: Record<string, string> = { en: "English", ja: "日本語", "zh-CN": "简体中文", es: "Español", "es-MX": "Español (MX)", nl: "Nederlands", fr: "Français" };
  return labels[languageCode] ?? languageCode;
}

export const timelineEventTone = (eventType: string): StatusTone => {
  if (eventType === "change") return "warning";
  if (eventType === "incident_resolved" || eventType === "communication_sent") return "success";
  if (eventType === "incident_opened" || eventType === "alert") return "danger";
  if (eventType === "chat_fact") return "info";
  if (eventType.startsWith("rca") || eventType.startsWith("evidence") || eventType.startsWith("investigation") || eventType.startsWith("postmortem") || eventType.startsWith("communications")) return "ai";
  return "neutral";
};

/** Keigan's own pipeline steps (investigation, evidence, analysis, communications drafts): they all land within seconds of each other. */
export const isPipelineEvent = (eventType: string, eventSource: string): boolean =>
  eventSource === "keigan" && /^(investigation|evidence|rca|communications|postmortem)/.test(eventType);
