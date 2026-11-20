/**
 * Fallback for the hosts a link inside AI-written or user-supplied Markdown may point to (security review V8), used only when the
 * backend does not publish `allowedLinkHosts` in `/api/public/client-configuration`. An entry is an exact host, or `*.suffix`
 * for sub-domains. It mirrors the backend default of `AI_OUTPUT_ALLOWED_LINK_HOSTS`; the backend value is the one that counts.
 */
export const defaultAllowedLinkHosts: readonly string[] = ["portal.azure.com", "learn.microsoft.com"];
