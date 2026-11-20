/**
 * The same rule the server applies (backend `keigan/utils/email_address.py`), so a typo is shown beside the field instead of after the save.
 * Strict on purpose: an address that passes is one a mail server accepts. The server stays the last word.
 */
const emailAddressPattern = /^[a-z0-9_%+'-]+(\.[a-z0-9_%+'-]+)*@([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/;
const maximumEmailAddressLength = 320;
const maximumLocalPartLength = 64;

export function isValidEmailAddress(typedAddress: string): boolean {
  const address = typedAddress.trim().toLowerCase();
  return address.length <= maximumEmailAddressLength && (address.split("@")[0] ?? "").length <= maximumLocalPartLength && emailAddressPattern.test(address);
}
