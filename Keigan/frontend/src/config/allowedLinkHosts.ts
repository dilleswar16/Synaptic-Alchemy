/**
 * Hosts a link inside AI-written or user-supplied Markdown may point to (security review V8). Any other link is shown as
 * plain text. Matches the host itself and its sub-domains. This mirrors the backend list `DEFAULT_ALLOWED_LINK_HOSTS`;
 * once the backend publishes `allowedLinkHosts` in `/api/public/client-configuration` that value replaces this one.
 */
export const defaultAllowedLinkHosts: readonly string[] = [
  "portal.azure.com",
  "service-now.com",
  "dev.azure.com",
  "github.com",
  "metlife.com",
  "learn.microsoft.com",
];
