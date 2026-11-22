import { cn } from "@/utils/cn";

/** A pill-shaped question button: the suggested prompts of an empty conversation and the follow-up questions under an answer. */
export const chatPillClassName = cn(
  "rounded-full border border-strong bg-surface px-3 py-1.5 text-left text-body-sm font-medium text-default transition-colors",
  "hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50",
);
