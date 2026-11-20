import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { Toast as RadixToast } from "radix-ui";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { defaultToneIcons, toneTextClasses, type StatusTone } from "./toneStyles";

export interface ToastOptions {
  tone?: Extract<StatusTone, "info" | "success" | "warning" | "danger" | "ai" | "neutral">;
  title: ReactNode;
  description?: ReactNode;
  action?: { label: string; onClick: () => void };
  /** Default 5000 ms; pauses while hovered or focused. */
  durationMilliseconds?: number;
}

interface ToastRecord extends ToastOptions {
  toastId: string;
  isOpen: boolean;
}

interface ToastContextValue {
  showToast: (options: ToastOptions) => string;
  dismissToast: (toastId: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastSequence = 0;

/** Mount once near the root (AppProviders does). Renders the bottom-right toast viewport. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation("common");
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const dismissToast = useCallback((toastId: string) => {
    setToasts((currentToasts) => currentToasts.map((toast) => (toast.toastId === toastId ? { ...toast, isOpen: false } : toast)));
    window.setTimeout(() => setToasts((currentToasts) => currentToasts.filter((toast) => toast.toastId !== toastId)), 300);
  }, []);

  const showToast = useCallback((options: ToastOptions) => {
    toastSequence += 1;
    const toastId = `toast-${toastSequence}`;
    setToasts((currentToasts) => [...currentToasts.slice(-4), { ...options, toastId, isOpen: true }]);
    return toastId;
  }, []);

  const contextValue = useMemo(() => ({ showToast, dismissToast }), [showToast, dismissToast]);

  return (
    <ToastContext.Provider value={contextValue}>
      <RadixToast.Provider swipeDirection="right" duration={5000} label={t("toast.regionLabel")}>
        {children}
        {toasts.map((toast) => {
          const tone = toast.tone ?? "info";
          const ToneIcon = defaultToneIcons[tone];
          return (
            <RadixToast.Root
              key={toast.toastId}
              open={toast.isOpen}
              duration={toast.durationMilliseconds}
              type={tone === "danger" ? "foreground" : "background"}
              onOpenChange={(isOpen: boolean) => (isOpen ? undefined : dismissToast(toast.toastId))}
              className={cn(
                "pointer-events-auto relative flex w-full items-start gap-3 rounded-md border border-hairline bg-surface p-4 pr-10 shadow-lg",
                "data-[state=open]:animate-toast-in data-[state=closed]:animate-toast-out",
                "data-[swipe=move]:translate-x-[var(--radix-toast-swipe-move-x)] data-[swipe=cancel]:translate-x-0 data-[swipe=end]:animate-toast-out",
              )}
            >
              <ToneIcon aria-hidden="true" size={20} strokeWidth={2} className={cn("mt-px shrink-0", toneTextClasses[tone])} />
              <div className="min-w-0 flex-1">
                <RadixToast.Title className="text-body font-semibold text-default">{toast.title}</RadixToast.Title>
                {toast.description ? (
                  <RadixToast.Description className="mt-0.5 text-body-sm text-muted">{toast.description}</RadixToast.Description>
                ) : null}
                {toast.action ? (
                  <RadixToast.Action
                    altText={toast.action.label}
                    onClick={toast.action.onClick}
                    className="mt-2 text-body-sm font-semibold text-action hover:text-action-hover hover:underline"
                  >
                    {toast.action.label}
                  </RadixToast.Action>
                ) : null}
              </div>
              <RadixToast.Close
                aria-label={t("toast.dismiss")}
                className="absolute top-3 right-3 grid size-7 place-items-center rounded-sm text-muted hover:bg-surface-hover hover:text-default"
              >
                <X aria-hidden="true" size={16} />
              </RadixToast.Close>
            </RadixToast.Root>
          );
        })}
        <RadixToast.Viewport className="fixed right-0 bottom-0 z-[80] m-0 flex w-full max-w-[420px] list-none flex-col gap-2.5 p-4 outline-none sm:p-6" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}

/** `const { showToast } = useToast(); showToast({ tone: "success", title: t("…") })`. */
export function useToast(): ToastContextValue {
  const toastContext = useContext(ToastContext);
  if (!toastContext) {
    throw new Error("useToast must be used inside ToastProvider.");
  }
  return toastContext;
}
