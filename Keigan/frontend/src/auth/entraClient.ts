import {
  EventType,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
  type EventMessage,
} from "@azure/msal-browser";
import type { EntraConfiguration } from "@/config/runtimeConfiguration";

/**
 * Microsoft Entra ID sign-in (AUTH_MODE=entra) with MSAL Browser 5.
 *
 * MSAL 5 receives authentication responses on a "redirect bridge" page (`/auth-redirect.html`, built as a second
 * Vite entry) which hands the response back to the app. Register both of these as SPA redirect URIs in the
 * Entra app registration: `https://<host>/auth-redirect.html` (sign-in) and `https://<host>/sign-in` (sign-out).
 */

export const entraRedirectBridgePath = "/auth-redirect.html";

export async function createEntraClient(entraConfiguration: EntraConfiguration): Promise<PublicClientApplication> {
  const publicClientApplication = new PublicClientApplication({
    auth: {
      clientId: entraConfiguration.spaClientId,
      authority: entraConfiguration.authority || `https://login.microsoftonline.com/${entraConfiguration.tenantId}`,
      redirectUri: `${window.location.origin}${entraRedirectBridgePath}`,
      postLogoutRedirectUri: `${window.location.origin}/sign-in`,
    },
    cache: {
      cacheLocation: "sessionStorage",
    },
  });

  await publicClientApplication.initialize();

  const existingAccounts = publicClientApplication.getAllAccounts();
  if (!publicClientApplication.getActiveAccount() && existingAccounts[0]) {
    publicClientApplication.setActiveAccount(existingAccounts[0]);
  }

  publicClientApplication.addEventCallback((eventMessage: EventMessage) => {
    const isSuccessEvent = eventMessage.eventType === EventType.LOGIN_SUCCESS || eventMessage.eventType === EventType.ACQUIRE_TOKEN_SUCCESS;
    const authenticationResult = eventMessage.payload as AuthenticationResult | null;
    if (isSuccessEvent && authenticationResult?.account) {
      publicClientApplication.setActiveAccount(authenticationResult.account);
    }
  });

  return publicClientApplication;
}

export function getEntraAccount(publicClientApplication: PublicClientApplication): AccountInfo | null {
  return publicClientApplication.getActiveAccount() ?? publicClientApplication.getAllAccounts()[0] ?? null;
}

/** Silent token for the Keigan API scope; falls back to a full-page redirect when interaction is required. */
export async function acquireEntraAccessToken(publicClientApplication: PublicClientApplication, apiScope: string): Promise<string | null> {
  const account = getEntraAccount(publicClientApplication);
  if (!account) {
    return null;
  }
  try {
    const authenticationResult = await publicClientApplication.acquireTokenSilent({ scopes: [apiScope], account });
    return authenticationResult.accessToken;
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      await publicClientApplication.acquireTokenRedirect({ scopes: [apiScope], account, redirectStartPage: window.location.href });
      return null;
    }
    throw error;
  }
}
