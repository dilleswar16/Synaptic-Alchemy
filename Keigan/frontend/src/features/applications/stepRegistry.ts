import type { StepKey } from "@/api/applicationsApi";

export type StageKey = "connect" | "teach" | "operate" | "launch";
export type StepRequirement = "required" | "recommended" | "optional" | "informational";

export interface StepDefinition {
  key: StepKey;
  stage: StageKey;
  requirement: StepRequirement;
  /** Tables and graphs use the full width of the panel; forms stay at 760 px. */
  isWide: boolean;
}

/** The eleven workspace steps (spec 6.2). The same modules render in wizard mode while onboarding and in page mode after go-live. */
export const stepDefinitions: StepDefinition[] = [
  { key: "components", stage: "connect", requirement: "required", isWide: false },
  { key: "services", stage: "connect", requirement: "required", isWide: true },
  { key: "log_tools", stage: "connect", requirement: "optional", isWide: false },
  { key: "knowledge", stage: "teach", requirement: "recommended", isWide: false },
  { key: "topology", stage: "teach", requirement: "recommended", isWide: true },
  { key: "runbooks", stage: "teach", requirement: "optional", isWide: false },
  { key: "incidents", stage: "operate", requirement: "required", isWide: false },
  { key: "slo", stage: "operate", requirement: "required", isWide: true },
  { key: "notifications", stage: "operate", requirement: "required", isWide: true },
  { key: "access", stage: "launch", requirement: "informational", isWide: false },
  { key: "review", stage: "launch", requirement: "required", isWide: false },
];

export const stageOrder: StageKey[] = ["connect", "teach", "operate", "launch"];

export function isStepKey(value: string): value is StepKey {
  return stepDefinitions.some((definition) => definition.key === value);
}

/** Props shared by every step component (doc 07 §2). Call `onStatusChange` after saves so the workspace refetches readiness. */
export interface StepProps {
  applicationId: string;
  mode: "wizard" | "page";
  canEdit: boolean;
  onStatusChange?: () => void;
}
