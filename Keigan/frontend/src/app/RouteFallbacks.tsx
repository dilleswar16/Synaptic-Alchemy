import { isRouteErrorResponse, useRouteError } from "react-router";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { Button } from "@/components/ui/Button";

/** Suspense fallback while a lazy page or its translation namespace loads. */
export function PageLoadingFallback() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

/** Route-level error boundary (render errors and failed lazy imports). */
export function RouteErrorBoundary() {
  const { t } = useTranslation("navigation");
  const { t: translateCommon } = useTranslation("common");
  const routeError = useRouteError();
  const details = isRouteErrorResponse(routeError) ? `${routeError.status} ${routeError.statusText}` : routeError instanceof Error ? routeError.message : String(routeError);
  return (
    <div className="grid min-h-[50dvh] place-items-center p-6">
      <div className="flex max-w-xl flex-col items-center gap-4">
        <ErrorState title={t("routeError.title")} description={t("routeError.description")} />
        <code className="max-w-full overflow-x-auto rounded-sm bg-surface-sunken px-3 py-2 font-mono text-caption text-muted">{details}</code>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          {translateCommon("actions.reloadPage")}
        </Button>
      </div>
    </div>
  );
}
