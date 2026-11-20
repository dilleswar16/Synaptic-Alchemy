import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Check, LogIn, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { authQueryKeys, getLocalUsers } from "@/api/authApi";
import { isApiError } from "@/api/httpClient";
import { useAuth } from "@/auth/authContext";
import { getLastSessionEndReason } from "@/auth/localSession";
import { useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { LanguageSwitcher } from "@/components/layout/LanguageSwitcher";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/utils/cn";

const brandHighlightKeys = ["highlightRootCause", "highlightNoise", "highlightSlo", "highlightCommunications"] as const;

/** Sign-in (doc 04 §6.1): brand panel on the left; local test users or "Sign in with Microsoft" on the right. */
export default function SignInPage() {
  const { t } = useTranslation("auth");
  const { t: translateCommon } = useTranslation("common");
  const navigate = useNavigate();
  const location = useLocation();
  const { status, signInLocal, signInWithMicrosoft } = useAuth();
  const { authMode } = useRuntimeConfiguration();
  const [selectedUserPrincipalName, setSelectedUserPrincipalName] = useState<string>("");
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [signInErrorMessage, setSignInErrorMessage] = useState<string | null>(null);
  const [sessionEndReason] = useState(getLastSessionEndReason);

  const redirectTarget = (location.state as { from?: string } | null)?.from ?? "/";
  const isLocalMode = authMode === "local";

  const localUsersQuery = useQuery({ queryKey: authQueryKeys.localUsers, queryFn: getLocalUsers, enabled: isLocalMode, retry: false });

  useEffect(() => {
    document.title = `${t("signIn.pageTitle")} · Keigan`;
  }, [t]);

  useEffect(() => {
    if (!selectedUserPrincipalName && localUsersQuery.data?.[0]) {
      setSelectedUserPrincipalName(localUsersQuery.data[0].userPrincipalName);
    }
  }, [localUsersQuery.data, selectedUserPrincipalName]);

  if (status === "authenticated") {
    return <Navigate to={redirectTarget} replace />;
  }

  async function handleSignIn(): Promise<void> {
    setSignInErrorMessage(null);
    setIsSigningIn(true);
    try {
      if (isLocalMode) {
        await signInLocal(selectedUserPrincipalName);
        navigate(redirectTarget, { replace: true });
      } else {
        await signInWithMicrosoft();
      }
    } catch (error) {
      setSignInErrorMessage(isApiError(error) ? error.detail ?? error.title : error instanceof Error ? error.message : t("signIn.signInFailed"));
      setIsSigningIn(false);
    }
  }

  const sessionBanner =
    sessionEndReason === "expired" ? t("signIn.sessionExpired") : sessionEndReason === "rejected" ? t("signIn.sessionRejected") : null;
  const loadUsersError = localUsersQuery.error;

  return (
    <div className="grid min-h-dvh lg:grid-cols-[44%_1fr]">
      <aside className="relative hidden overflow-hidden bg-gradient-brand p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div aria-hidden="true" className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-white/15 blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 -left-16 size-[28rem] rounded-full bg-metlife-green/25 blur-3xl" />
        <KeiganLogo tone="inverse" size={44} showKanji className="relative" />
        <div className="relative max-w-md">
          <h2 className="font-display text-display text-white">{translateCommon("tagline")}</h2>
          <ul className="mt-8 flex flex-col gap-3">
            {brandHighlightKeys.map((highlightKey) => (
              <li key={highlightKey} className="flex items-start gap-3 text-body-lg text-white/90">
                <Check aria-hidden="true" size={20} className="mt-0.5 shrink-0" />
                {t(`brand.${highlightKey}`)}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-body-sm text-white/80">{t("signIn.footer")}</p>
      </aside>

      <main className="relative flex items-center justify-center bg-canvas p-6 sm:p-10">
        <div className="absolute top-4 right-4 flex items-center gap-1">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
        <div className="flex w-full max-w-lg flex-col gap-6">
          <KeiganLogo showKanji className="lg:hidden" />
          <div>
            <h1 className="font-display text-h1 text-default">{t("signIn.title")}</h1>
            <p className="mt-2 text-body text-muted">{t("signIn.subtitle")}</p>
          </div>

          {sessionBanner ? <Banner tone="info">{sessionBanner}</Banner> : null}
          {isLocalMode ? (
            <Banner tone="warning" title={t("signIn.localModeBanner")}>
              {t("signIn.localModeDescription")}
            </Banner>
          ) : null}
          {signInErrorMessage ? (
            <Banner tone="danger" title={t("signIn.signInFailed")}>
              {signInErrorMessage}
            </Banner>
          ) : null}

          {isLocalMode ? (
            <section aria-labelledby="test-user-heading" className="rounded-lg border border-hairline bg-surface p-5 shadow-sm">
              <h2 id="test-user-heading" className="font-display text-h3 text-default">
                {t("signIn.chooseTestUser")}
              </h2>
              <p className="mt-1 mb-4 text-body-sm text-muted">{t("signIn.chooseTestUserDescription")}</p>
              {localUsersQuery.isLoading ? (
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : loadUsersError ? (
                <Banner tone="danger" title={t("signIn.loadUsersFailed")}>
                  {isApiError(loadUsersError) && loadUsersError.isNetworkError ? t("signIn.apiUnavailable") : loadUsersError.message}
                </Banner>
              ) : (localUsersQuery.data ?? []).length === 0 ? (
                <p className="text-body-sm text-muted">{t("signIn.noTestUsers")}</p>
              ) : (
                <div role="radiogroup" aria-labelledby="test-user-heading" className="flex flex-col gap-2">
                  {(localUsersQuery.data ?? []).map((localUser) => {
                    const isSelected = localUser.userPrincipalName === selectedUserPrincipalName;
                    return (
                      <button
                        key={localUser.userPrincipalName}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        onClick={() => setSelectedUserPrincipalName(localUser.userPrincipalName)}
                        className={cn(
                          "flex items-center gap-3 rounded-md border p-3 text-left transition-colors",
                          isSelected ? "border-action bg-surface-selected" : "border-hairline hover:bg-surface-hover",
                        )}
                      >
                        <Avatar name={localUser.displayName} size="lg" />
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="text-body font-semibold text-default">{localUser.displayName}</span>
                            {localUser.roleDescription ? <Badge tone="brand">{localUser.roleDescription}</Badge> : null}
                          </span>
                          <span className="block truncate font-mono text-caption text-muted">
                            {localUser.groupNames.length > 0 ? localUser.groupNames.join(", ") : t("signIn.noGroups")}
                          </span>
                        </span>
                        {isSelected ? <Check aria-hidden="true" size={18} className="shrink-0 text-action" /> : null}
                      </button>
                    );
                  })}
                </div>
              )}
              <Button
                className="mt-5"
                fullWidth
                size="lg"
                leadingIcon={LogIn}
                isLoading={isSigningIn}
                disabled={!selectedUserPrincipalName}
                onClick={() => void handleSignIn()}
              >
                {isSigningIn ? t("signIn.signingIn") : t("signIn.signInButton")}
              </Button>
            </section>
          ) : (
            <section className="rounded-lg border border-hairline bg-surface p-5 shadow-sm">
              <p className="mb-4 flex items-start gap-2 text-body text-muted">
                <ShieldCheck aria-hidden="true" size={20} className="mt-0.5 shrink-0 text-action" />
                {t("signIn.microsoftDescription")}
              </p>
              <Button fullWidth size="lg" leadingIcon={LogIn} isLoading={isSigningIn} onClick={() => void handleSignIn()}>
                {isSigningIn ? t("signIn.redirecting") : t("signIn.signInWithMicrosoft")}
              </Button>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
