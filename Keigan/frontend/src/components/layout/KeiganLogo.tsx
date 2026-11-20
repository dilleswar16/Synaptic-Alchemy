import { useId } from "react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/utils/cn";

export interface KeiganLogoProps {
  /** `mark` is the eye only; `full` adds the wordmark. */
  variant?: "full" | "mark";
  /** Mark height in px (the wordmark scales with it). Default 32. */
  size?: number;
  /** Show the kanji 慧眼 after the wordmark (sidebar header, sign-in). */
  showKanji?: boolean;
  /** `inverse` forces the white outline for use on the brand gradient or other dark fills. */
  tone?: "auto" | "inverse";
  className?: string;
}

/**
 * Keigan mark: an almond eye from two arcs with a brand-gradient stroke, a Dark Blue iris with a highlight and a
 * green arc suggesting a radar sweep (doc 04 §1.1). On dark backgrounds the outline turns white → green.
 */
export function KeiganLogo({ variant = "full", size = 32, showKanji = false, tone = "auto", className }: KeiganLogoProps) {
  const gradientId = `keigan-eye-${useId()}`;
  const { resolvedTheme } = useTheme();
  const isOnDark = tone === "inverse" || resolvedTheme === "dark";
  const outlineStops = isOnDark ? ["#FFFFFF", "#A4CE4E"] : ["#0061A0", "#0090DA", "#A4CE4E"];
  const irisColor = isOnDark && tone === "inverse" ? "#0061A0" : "#0061A0";

  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" role={variant === "mark" ? "img" : undefined} aria-label={variant === "mark" ? "Keigan" : undefined} aria-hidden={variant === "mark" ? undefined : true} className="shrink-0">
        <defs>
          <linearGradient id={gradientId} x1="2" y1="16" x2="30" y2="16" gradientUnits="userSpaceOnUse">
            {outlineStops.map((stopColor, stopIndex) => (
              <stop key={stopColor + stopIndex} offset={stopIndex / (outlineStops.length - 1)} stopColor={stopColor} />
            ))}
          </linearGradient>
        </defs>
        <path d="M2 16 Q16 3.5 30 16" stroke={`url(#${gradientId})`} strokeWidth="2.25" strokeLinecap="round" />
        <path d="M2 16 Q16 28.5 30 16" stroke={`url(#${gradientId})`} strokeWidth="2.25" strokeLinecap="round" />
        <circle cx="16" cy="16" r="6" fill={isOnDark ? "#FFFFFF" : irisColor} />
        <circle cx="16" cy="16" r="4.6" fill={irisColor} />
        <circle cx="14.2" cy="14.2" r="1.5" fill="#FFFFFF" fillOpacity="0.9" />
        <path d="M23.2 18.9 A8 8 0 0 1 17.6 23.9" stroke="#A4CE4E" strokeWidth="2" strokeLinecap="round" />
      </svg>
      {variant === "full" ? (
        <span className="inline-flex items-baseline gap-2 leading-none">
          <span
            className={cn("font-display font-bold tracking-[-0.01em]", isOnDark ? "text-white" : "text-default")}
            style={{ fontSize: Math.round(size * 0.72) }}
          >
            Keigan
          </span>
          {showKanji ? (
            <span lang="ja" className={cn("font-medium", isOnDark ? "text-white/70" : "text-muted")} style={{ fontFamily: '"Noto Sans JP", sans-serif', fontSize: Math.round(size * 0.43) }}>
              慧眼
            </span>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
