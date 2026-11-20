import { Suspense, useMemo } from "react";
import { RouterProvider } from "react-router";
import { isDeveloperEnvironment, useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { Spinner } from "@/components/ui/Spinner";
import { AppProviders } from "./providers";
import { createAppRouter } from "./routes";

export function App() {
  const runtimeConfiguration = useRuntimeConfiguration();
  const router = useMemo(() => createAppRouter({ isDeveloperEnvironment: isDeveloperEnvironment(runtimeConfiguration) }), [runtimeConfiguration]);
  return (
    <AppProviders>
      <Suspense
        fallback={
          <div className="grid min-h-dvh place-items-center bg-canvas">
            <Spinner size="lg" />
          </div>
        }
      >
        <RouterProvider router={router} />
      </Suspense>
    </AppProviders>
  );
}
