import { createContext, useContext } from "react";
import type { CurrentUser } from "@/api/authApi";

/**
 * - `initializing`: configuration / MSAL / stored session being checked
 * - `signedOut`: no session; show the sign-in page
 * - `loadingProfile`: signed in, `/auth/me` in flight
 * - `authenticated`: `user` is available
 * - `profileError`: signed in but the profile could not be loaded (not a 401)
 */
export type AuthStatus = "initializing" | "signedOut" | "loadingProfile" | "authenticated" | "profileError";

export interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  /** Local mode: exchange a dummy user's principal name for a local token. Rejects with `ApiError`. */
  signInLocal: (userPrincipalName: string) => Promise<void>;
  /** Entra mode: starts the Microsoft redirect sign-in. */
  signInWithMicrosoft: () => Promise<void>;
  signOut: () => Promise<void>;
  /** Reloads `/auth/me` (e.g. after the user got new groups). */
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const authContextValue = useContext(AuthContext);
  if (!authContextValue) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return authContextValue;
}

/** The signed-in user; throws outside `RequireAuthentication`-guarded routes. */
export function useCurrentUser(): CurrentUser {
  const { user } = useAuth();
  if (!user) {
    throw new Error("useCurrentUser needs a signed-in user; render inside RequireAuthentication.");
  }
  return user;
}
