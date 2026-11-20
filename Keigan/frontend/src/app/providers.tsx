import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Tooltip as RadixTooltip } from "radix-ui";
import { queryClient } from "@/api/queryClient";
import { AuthProvider } from "@/auth/AuthProvider";
import { ToastProvider } from "@/components/ui/Toast";

/** Query cache, tooltip provider, toasts and authentication. The runtime configuration context wraps this (see Bootstrap). */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <RadixTooltip.Provider delayDuration={300} skipDelayDuration={150}>
        <ToastProvider>
          <AuthProvider>{children}</AuthProvider>
        </ToastProvider>
      </RadixTooltip.Provider>
    </QueryClientProvider>
  );
}
