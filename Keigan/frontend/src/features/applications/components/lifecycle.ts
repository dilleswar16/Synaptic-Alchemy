import type { LifecycleStatus, ComponentType } from "@/api/applicationsApi";
import type { StatusTone } from "@/components/ui/toneStyles";
import { Cloud, Cpu, Server, Network } from "lucide-react";

export const lifecycleTone: Record<LifecycleStatus, StatusTone> = {
  requested: "alert",
  draft: "neutral",
  onboarding: "info",
  live: "success",
  paused: "warning",
};

export const componentTypeIcon = {
  azure_resource_group: Cloud,
  hardware: Network,
  mainframe: Server,
  saas_platform: Cpu,
} satisfies Record<ComponentType, unknown>;
