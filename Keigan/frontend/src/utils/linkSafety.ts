/**
 * Returns the normalised URL when `href` is an absolute https link to an allowed host, otherwise `null`.
 * The WHATWG parser is used on purpose: it reads `\` like `/` and splits `user@host` the way browsers do, so a link such as
 * `https://evil.example\@portal.azure.com/` is judged by the host the browser would really open.
 */
export function allowedLinkUrl(href: string | undefined, allowedHosts: readonly string[]): string | null {
  if (!href) {
    return null;
  }
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username !== "" || url.password !== "") {
    return null;
  }
  const hostName = url.hostname.toLowerCase();
  return allowedHosts.some((allowedHost) => hostMatches(hostName, allowedHost)) ? url.href : null;
}

/** Same rule as the backend output filter: an exact host, or `*.suffix` for sub-domains of the suffix (not the suffix itself). */
function hostMatches(hostName: string, allowedHost: string): boolean {
  const pattern = allowedHost.toLowerCase();
  if (pattern.startsWith("*.")) {
    const suffix = pattern.slice(1);
    return hostName.endsWith(suffix) && hostName.length > suffix.length;
  }
  return hostName === pattern;
}
