import {
  Bell,
  Circle,
  CircleCheck,
  CircleExclamationPoint,
  Info,
  Sparkles,
  TriangleExclamationPoint,
  Eye,
  type LucideIcon,
} from "lucide-react";

/** Semantic tones shared by chips, badges, banners, icon tiles and timeline dots (doc 04 §1.2). */
export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "alert" | "ai" | "brand";

export const statusTones: StatusTone[] = ["neutral", "info", "success", "warning", "danger", "alert", "ai", "brand"];

/** Soft background with the tone's text colour (chips, icon tiles). */
export const toneSoftClasses: Record<StatusTone, string> = {
  neutral: "bg-neutral-soft text-neutral",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  alert: "bg-alert-soft text-alert",
  ai: "bg-ai-soft text-ai",
  brand: "bg-brand-soft text-brand",
};

/** Solid fill (dots, bars, solid badges). */
export const toneFillClasses: Record<StatusTone, string> = {
  neutral: "bg-neutral-fill",
  info: "bg-info-fill",
  success: "bg-success-fill",
  warning: "bg-warning-fill",
  danger: "bg-danger-fill",
  alert: "bg-alert-fill",
  ai: "bg-ai-fill",
  brand: "bg-brand-fill",
};

/** Text and icon colour only. */
export const toneTextClasses: Record<StatusTone, string> = {
  neutral: "text-neutral",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  alert: "text-alert",
  ai: "text-ai",
  brand: "text-brand",
};

/** Hairline border tinted with the tone (banners, outlined chips). */
export const toneBorderClasses: Record<StatusTone, string> = {
  neutral: "border-strong",
  info: "border-info/30",
  success: "border-success/30",
  warning: "border-warning/30",
  danger: "border-danger/30",
  alert: "border-alert/30",
  ai: "border-ai/30",
  brand: "border-brand/30",
};

/** Text colour that reads on the solid fill (yellow and green fills need dark text). */
export const toneOnFillTextClasses: Record<StatusTone, string> = {
  neutral: "text-white",
  info: "text-white",
  success: "text-metlife-darkest-gray",
  warning: "text-metlife-darkest-gray",
  danger: "text-white",
  alert: "text-white",
  ai: "text-white",
  brand: "text-white",
};

/** Default icon per tone, so status is never shown by colour alone. */
export const defaultToneIcons: Record<StatusTone, LucideIcon> = {
  neutral: Circle,
  info: Info,
  success: CircleCheck,
  warning: TriangleExclamationPoint,
  danger: CircleExclamationPoint,
  alert: Bell,
  ai: Sparkles,
  brand: Eye,
};
