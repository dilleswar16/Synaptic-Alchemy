import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * Keigan's type scale replaces Tailwind's default font sizes (`text-body`, `text-h1`, …). tailwind-merge must know
 * these are font sizes, otherwise `cn("text-body", "text-muted")` would treat both as colours and drop one.
 */
const mergeKeiganClasses = extendTailwindMerge({
  extend: {
    theme: {
      text: ["display", "h1", "h2", "h3", "h4", "body-lg", "body", "body-sm", "caption", "micro", "kpi", "kpi-sm", "code"],
    },
  },
});

/** Joins class names conditionally and resolves Tailwind conflicts (last one wins). */
export function cn(...classValues: ClassValue[]): string {
  return mergeKeiganClasses(clsx(classValues));
}
