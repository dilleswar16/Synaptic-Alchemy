import { apiGet, apiPatch, apiPost } from "./httpClient";
import type { ApplicationRole, Identifier, IsoDateTimeString } from "./types/common";

/** Authentication endpoints (doc 05 §3). */

export type ThemePreference = "light" | "dark" | "system";

/** A dummy user offered on the local-mode sign-in page (`backend/keigan/resources/local_users.yaml`). */
export interface LocalUser {
  userPrincipalName: string;
  displayName: string;
  emailAddress?: string;
  roleDescription: string;
  groupNames: string[];
  preferredLocale?: string;
}

export interface ApplicationRoleAssignment {
  applicationId: Identifier;
  applicationCode: string;
  applicationName: string;
  role: ApplicationRole;
  /** `requested`, `draft`, `onboarding`, `live`, `paused`. */
  lifecycleStatus?: string;
}

export interface CurrentUser {
  userPrincipalName: string;
  displayName: string;
  email: string | null;
  isKeiganAdmin: boolean;
  applicationRoles: ApplicationRoleAssignment[];
  preferredLocale: string | null;
  preferredTheme: ThemePreference | null;
}

export interface LocalSignInResponse {
  accessToken: string;
  expiresAt: IsoDateTimeString;
  user: CurrentUser;
}

export interface PreferencesUpdate {
  preferredLocale?: string;
  preferredTheme?: ThemePreference;
}

export const authQueryKeys = {
  currentUser: ["auth", "me"] as const,
  localUsers: ["auth", "local-users"] as const,
};

type RawLocalUser = Partial<LocalUser> & { groups?: string[]; name?: string; email?: string };
type RawCurrentUser = Partial<CurrentUser> & { emailAddress?: string | null };

/** Tolerates `groups`/`groupNames` and `email`/`emailAddress` spellings so the sign-in page never breaks on a rename. */
function normaliseLocalUser(rawUser: RawLocalUser): LocalUser {
  return {
    userPrincipalName: rawUser.userPrincipalName ?? "",
    displayName: rawUser.displayName ?? rawUser.name ?? rawUser.userPrincipalName ?? "",
    emailAddress: rawUser.emailAddress ?? rawUser.email,
    roleDescription: rawUser.roleDescription ?? "",
    groupNames: rawUser.groupNames ?? rawUser.groups ?? [],
    preferredLocale: rawUser.preferredLocale,
  };
}

function normaliseCurrentUser(rawUser: RawCurrentUser): CurrentUser {
  return {
    userPrincipalName: rawUser.userPrincipalName ?? "",
    displayName: rawUser.displayName ?? rawUser.userPrincipalName ?? "",
    email: rawUser.email ?? rawUser.emailAddress ?? null,
    isKeiganAdmin: rawUser.isKeiganAdmin === true,
    applicationRoles: rawUser.applicationRoles ?? [],
    preferredLocale: rawUser.preferredLocale ?? null,
    preferredTheme: rawUser.preferredTheme ?? null,
  };
}

export async function getLocalUsers(): Promise<LocalUser[]> {
  const rawUsers = await apiGet<RawLocalUser[] | { items: RawLocalUser[] }>("/auth/local-users", { isPublic: true });
  const userList = Array.isArray(rawUsers) ? rawUsers : (rawUsers.items ?? []);
  return userList.map(normaliseLocalUser);
}

export async function localSignIn(userPrincipalName: string): Promise<LocalSignInResponse> {
  const response = await apiPost<LocalSignInResponse & { user: RawCurrentUser }>(
    "/auth/local-sign-in",
    { userPrincipalName },
    { isPublic: true, ignoreUnauthorized: true },
  );
  return { ...response, user: normaliseCurrentUser(response.user ?? {}) };
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return normaliseCurrentUser(await apiGet<RawCurrentUser>("/auth/me"));
}

export async function updatePreferences(preferencesUpdate: PreferencesUpdate): Promise<CurrentUser> {
  return normaliseCurrentUser(await apiPatch<RawCurrentUser>("/auth/me/preferences", preferencesUpdate));
}
