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
  const isAllowed = allowedHosts.some((allowedHost) => hostName === allowedHost || hostName.endsWith(`.${allowedHost}`));
  return isAllowed ? url.href : null;
}
