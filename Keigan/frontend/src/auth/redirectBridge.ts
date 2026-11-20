import { broadcastResponseToMainFrame } from "@azure/msal-browser/redirect-bridge";

/**
 * Entry script of `/auth-redirect.html` (MSAL 5 redirect bridge). Entra redirects here after sign-in or silent
 * renewal; the bridge passes the response to the app window (iframe / popup) or navigates back to the page that
 * started the redirect sign-in.
 */
broadcastResponseToMainFrame().catch((error: unknown) => {
  console.error("[Keigan] Could not process the Microsoft sign-in response.", error);
  window.location.replace("/sign-in");
});
