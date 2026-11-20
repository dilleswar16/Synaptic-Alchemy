import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Info, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { defaultToneIcons, toneBorderClasses, toneSoftClasses, toneTextClasses, type StatusTone } from "./toneStyles";

export interface BannerProps {
  tone?: StatusTone;
  title?: ReactNode;
  children?: ReactNode;
  /** Custom icon, or `false` for none. Defaults to the tone icon. */
  icon?: LucideIcon | false;
  /** Action(s) on the right (link-style Button). */
  action?: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

/** Inline message spanning its container: info notices, warnings, the local-mode banner. */
export function Banner({ tone = "info", title, children, icon, action, onDismiss, className }: BannerProps) {
  const { t } = useTranslation("common");
  // A neutral notice shows the info icon: the plain circle of a neutral chip reads as an unchecked radio button next to text.
  const Icon = icon === false ? null : (icon ?? (tone === "neutral" ? Info : defaultToneIcons[tone]));
  // Only an error interrupts a screen reader; warnings and notices are announced politely.
  const isUrgent = tone === "danger";
  return (
    <div
      role={isUrgent ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-md border px-4 py-3",
        toneSoftClasses[tone],
        toneBorderClasses[tone],
        className,
      )}
    >
      {Icon ? <Icon aria-hidden="true" size={18} strokeWidth={2} className={cn("mt-0.5 shrink-0", toneTextClasses[tone])} /> : null}
      <div className="min-w-0 flex-1 text-body-sm text-default">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={cn(title && "mt-0.5", "text-default/85")}>{children}</div> : null}
      </div>
      {action ? <div className="shrink-0 self-center">{action}</div> : null}
      {onDismiss ? (
        <button
          type="button"
          aria-label={t("actions.dismiss")}
          onClick={onDismiss}
          className="-mt-0.5 -mr-1 grid size-7 shrink-0 place-items-center rounded-sm text-muted hover:bg-black/5 hover:text-default"
        >
          <X aria-hidden="true" size={16} />
        </button>
      ) : null}
    </div>
  );
}
