import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { RequireAuthentication, RequireKeiganAdmin } from "@/auth/RequireAuthentication";
import { AppShell } from "@/components/layout/AppShell";
import { NoAccessState } from "./NoAccessState";
import { RouteErrorBoundary } from "./RouteFallbacks";

/** Lazy route: `lazyPage(() => import("@/features/alerts/pages/AlertsPage"))` (page has a default export). */
function lazyPage(loadModule: () => Promise<{ default: React.ComponentType }>): Pick<RouteObject, "lazy"> {
  return { lazy: async () => ({ Component: (await loadModule()).default }) };
}

/**
 * Route table. To add a page: create `features/<area>/pages/<Name>Page.tsx` with a default export and add one
 * `{ path, ...lazyPage(...) }` entry below (inside `RequireKeiganAdmin` for admin-only pages).
 */
export function createAppRouter(options: { isDeveloperEnvironment: boolean }) {
  const authenticatedChildren: RouteObject[] = [
    { index: true, ...lazyPage(() => import("@/features/home/pages/HomePage")) },
    { path: "incidents", ...lazyPage(() => import("@/features/incidents/pages/IncidentRoomPage")) },
    { path: "investigations/:investigationId", ...lazyPage(() => import("@/features/investigations/pages/InvestigationPage")) },
    { path: "alerts", ...lazyPage(() => import("@/features/alerts/pages/AlertsPage")) },
    { path: "slo", ...lazyPage(() => import("@/features/slo/pages/SloMonitoringPage")) },
    { path: "intelligence", ...lazyPage(() => import("@/features/intelligence/pages/IntelligencePage")) },
    { path: "metrics", ...lazyPage(() => import("@/features/metrics/pages/ReliabilityMetricsPage")) },
    { path: "chat", ...lazyPage(() => import("@/features/chat/pages/KeiganChatPage")) },
    { path: "chat/:conversationId", ...lazyPage(() => import("@/features/chat/pages/KeiganChatPage")) },
    { path: "applications", ...lazyPage(() => import("@/features/applications/pages/ApplicationsPage")) },
    { path: "applications/:applicationId/*", ...lazyPage(() => import("@/features/applications/pages/ApplicationWorkspacePage")) },
    {
      element: <RequireKeiganAdmin />,
      children: [
        { path: "administration", element: <Navigate to="/administration/settings" replace /> },
        { path: "administration/settings", ...lazyPage(() => import("@/features/administration/pages/PlatformSettingsPage")) },
        { path: "administration/usage", ...lazyPage(() => import("@/features/administration/pages/UsageAndAuditPage")) },
        { path: "administration/outbox", ...lazyPage(() => import("@/features/administration/pages/OutboxPage")) },
      ],
    },
    ...(options.isDeveloperEnvironment ? [{ path: "design-system", ...lazyPage(() => import("./DesignSystemShowcasePage")) }] : []),
    { path: "*", ...lazyPage(() => import("./NotFoundPage")) },
  ];

  return createBrowserRouter([
    {
      errorElement: <RouteErrorBoundary />,
      children: [
        { path: "/sign-in", ...lazyPage(() => import("./SignInPage")) },
        {
          element: <RequireAuthentication noAccessElement={<NoAccessState />} />,
          children: [{ element: <AppShell />, children: authenticatedChildren }],
        },
      ],
    },
  ]);
}
