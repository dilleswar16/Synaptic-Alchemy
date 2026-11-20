import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { PublicClientApplication } from "@azure/msal-browser";
import { getCurrentUser, localSignIn, type CurrentUser } from "@/api/authApi";
import { queryClient } from "@/api/queryClient";
import { useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { changeApplicationLanguage, isSupportedLocale } from "@/i18n";
import { setThemePreference } from "@/hooks/useTheme";
import { registerAuthBridge } from "./authBridge";
import { AuthContext, type AuthContextValue, type AuthStatus } from "./authContext";
import { acquireEntraAccessToken, createEntraClient, getEntraAccount } from "./entraClient";
import { clearLocalSession, readLocalSession, subscribeToLocalSession, writeLocalSession } from "./localSession";

/** Applies the language and theme saved on the profile without writing them back. */
function applyProfilePreferences(user: CurrentUser): void {
  if (isSupportedLocale(user.preferredLocale)) {
    void changeApplicationLanguage(user.preferredLocale, { persistToProfile: false });
  }
  if (user.preferredTheme) {
    setThemePreference(user.preferredTheme, { persistToProfile: false });
  }
}

/**
 * Owns the sign-in state for both auth modes (local token / Microsoft Entra via MSAL) and registers the live
 * token provider with `authBridge`, which the HTTP client uses. Mount inside `RuntimeConfigurationContext`.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const runtimeConfiguration = useRuntimeConfiguration();
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const entraClientRef = useRef<PublicClientApplication | null>(null);
  const isAuthenticatedRef = useRef(false);

  isAuthenticatedRef.current = status === "authenticated" || status === "loadingProfile";

  const resetToSignedOut = useCallback(() => {
    setUser(null);
    setStatus("signedOut");
    queryClient.clear();
  }, []);

  const loadProfile = useCallback(async () => {
    setStatus("loadingProfile");
    try {
      const currentUser = await getCurrentUser();
      setUser(currentUser);
      setStatus("authenticated");
      applyProfilePreferences(currentUser);
    } catch (error) {
      // A 401 already ended the session through the bridge; anything else is a profile problem.
      setStatus((previousStatus) => (previousStatus === "signedOut" ? previousStatus : "profileError"));
      console.error("[Keigan] Could not load the user profile.", error);
    }
  }, []);

  // Bootstrap: Entra client, bridge registration, existing session.
  useEffect(() => {
    let isCancelled = false;
    const isEntraMode = runtimeConfiguration.authMode === "entra" && runtimeConfiguration.entra !== null;

    const unregisterBridge = registerAuthBridge({
      isAuthenticated: () => isAuthenticatedRef.current,
      getAccessToken: async () => {
        if (isEntraMode && entraClientRef.current && runtimeConfiguration.entra) {
          return acquireEntraAccessToken(entraClientRef.current, runtimeConfiguration.entra.apiScope);
        }
        return readLocalSession()?.accessToken ?? null;
      },
      handleUnauthorized: () => {
        if (isEntraMode) {
          resetToSignedOut();
          return;
        }
        clearLocalSession("rejected");
      },
    });

    async function initialise(): Promise<void> {
      if (isEntraMode && runtimeConfiguration.entra) {
        const entraClient = await createEntraClient(runtimeConfiguration.entra);
        await entraClient.handleRedirectPromise().catch((error: unknown) => console.error("[Keigan] Microsoft sign-in failed.", error));
        if (isCancelled) return;
        entraClientRef.current = entraClient;
        if (getEntraAccount(entraClient)) {
          await loadProfile();
          return;
        }
        setStatus("signedOut");
        return;
      }
      if (readLocalSession()) {
        await loadProfile();
        return;
      }
      setStatus("signedOut");
    }

    initialise().catch((error: unknown) => {
      console.error("[Keigan] Sign-in initialisation failed.", error);
      if (!isCancelled) setStatus("signedOut");
    });

    const unsubscribeFromSession = subscribeToLocalSession(() => {
      if (!isEntraMode && !readLocalSession()) {
        resetToSignedOut();
      }
    });

    return () => {
      isCancelled = true;
      unregisterBridge();
      unsubscribeFromSession();
    };
  }, [runtimeConfiguration, loadProfile, resetToSignedOut]);

  const signInLocal = useCallback(
    async (userPrincipalName: string) => {
      const signInResponse = await localSignIn(userPrincipalName);
      writeLocalSession({ accessToken: signInResponse.accessToken, expiresAt: signInResponse.expiresAt });
      queryClient.clear();
      setUser(signInResponse.user);
      setStatus("authenticated");
      applyProfilePreferences(signInResponse.user);
    },
    [],
  );

  const signInWithMicrosoft = useCallback(async () => {
    const entraClient = entraClientRef.current;
    if (!entraClient || !runtimeConfiguration.entra) {
      throw new Error("Microsoft sign-in is not configured.");
    }
    await entraClient.loginRedirect({ scopes: [runtimeConfiguration.entra.apiScope] });
  }, [runtimeConfiguration.entra]);

  const signOut = useCallback(async () => {
    if (runtimeConfiguration.authMode === "entra" && entraClientRef.current) {
      resetToSignedOut();
      await entraClientRef.current.logoutRedirect({ account: getEntraAccount(entraClientRef.current) ?? undefined });
      return;
    }
    clearLocalSession("signedOut");
  }, [runtimeConfiguration.authMode, resetToSignedOut]);

  const contextValue = useMemo<AuthContextValue>(
    () => ({ status, user, signInLocal, signInWithMicrosoft, signOut, refreshUser: loadProfile }),
    [status, user, signInLocal, signInWithMicrosoft, signOut, loadProfile],
  );

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>;
}
