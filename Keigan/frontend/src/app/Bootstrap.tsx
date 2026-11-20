import { useCallback, useEffect, useState } from "react";
import { i18nReady } from "@/i18n";
import { loadRuntimeConfiguration, resetRuntimeConfiguration, RuntimeConfigurationContext, type RuntimeConfiguration } from "@/config/runtimeConfiguration";
import { Spinner } from "@/components/ui/Spinner";
import { App } from "./App";

type BootstrapState = { phase: "loading" } | { phase: "error"; message: string } | { phase: "ready"; configuration: RuntimeConfiguration };

/**
 * Loads translations and the runtime client configuration (`/api/public/client-configuration`) before the app
 * renders. Uses plain markup so a failure still shows something readable without any provider.
 */
export function Bootstrap() {
  const [state, setState] = useState<BootstrapState>({ phase: "loading" });

  const start = useCallback(() => {
    setState({ phase: "loading" });
    Promise.all([i18nReady, loadRuntimeConfiguration()])
      .then(([, configuration]) => setState({ phase: "ready", configuration }))
      .catch((error: unknown) => setState({ phase: "error", message: error instanceof Error ? error.message : String(error) }));
  }, []);

  useEffect(start, [start]);

  if (state.phase === "ready") {
    return (
      <RuntimeConfigurationContext.Provider value={state.configuration}>
        <App />
      </RuntimeConfigurationContext.Provider>
    );
  }
  if (state.phase === "error") {
    return (
      <div className="grid min-h-dvh place-items-center bg-canvas p-6 text-center">
        <div className="max-w-md">
          <h1 className="font-display text-h2 text-default">Keigan couldn&apos;t start</h1>
          <p className="mt-2 text-body text-muted">The client configuration couldn&apos;t be loaded from the Keigan API.</p>
          <code className="mt-3 block rounded-sm bg-surface-sunken px-3 py-2 font-mono text-caption text-muted">{state.message}</code>
          <button
            type="button"
            className="mt-4 h-10 rounded-sm bg-action px-4 text-body font-semibold text-on-action hover:bg-action-hover"
            onClick={() => {
              resetRuntimeConfiguration();
              start();
            }}
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="grid min-h-dvh place-items-center bg-canvas">
      <Spinner size="lg" />
    </div>
  );
}
