import { Navigate, Outlet, useLocation } from "react-router";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { useAccessControl } from "./accessControl";
import { useAuth } from "./authContext";

/** Full-screen centred content for loading / error states before the shell is available. */
function FullScreenMessage({ children }: { children: React.ReactNode }) {
  return <div className="grid min-h-dvh place-items-center bg-canvas p-6">{children}</div>;
}

/**
 * Route guard: signed-out users go to `/sign-in` (remembering where they were), profile failures show a retry,
 * and signed-in users who belong to no application see the "request access" state (`noAccessElement`).
 */
export function RequireAuthentication({ noAccessElement }: { noAccessElement: React.ReactNode }) {
  const { t } = useTranslation("auth");
  const { status, refreshUser } = useAuth();
  const { user, isKeiganAdmin } = useAccessControl();
  const location = useLocation();

  if (status === "initializing" || status === "loadingProfile") {
    return (
      <FullScreenMessage>
        <Spinner size="lg" label={status === "initializing" ? t("loading.startingUp") : t("loading.loadingProfile")} />
      </FullScreenMessage>
    );
  }
  if (status === "signedOut") {
    return <Navigate to="/sign-in" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  if (status === "profileError") {
    return (
      <FullScreenMessage>
        <ErrorState title={t("profileError.title")} description={t("profileError.description")} onRetry={() => void refreshUser()} />
      </FullScreenMessage>
    );
  }
  if (user && !isKeiganAdmin && user.applicationRoles.length === 0) {
    return <>{noAccessElement}</>;
  }
  return <Outlet />;
}

/** Wrap Keigan-admin-only routes (administration pages). Backend enforces the same rule. */
export function RequireKeiganAdmin() {
  const { t } = useTranslation("navigation");
  const { isKeiganAdmin } = useAccessControl();
  if (!isKeiganAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title={t("adminOnly.title")}
        description={t("adminOnly.description")}
        action={
          <Button asChild variant="secondary">
            <a href="/">{t("notFound.goHome")}</a>
          </Button>
        }
      />
    );
  }
  return <Outlet />;
}
