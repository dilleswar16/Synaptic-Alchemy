import { useCallback, useSyncExternalStore } from "react";

/**
 * "Show tool details" (spec 8.6, decision D1): whether the steps of an answer are shown open or folded to one line. On by default, remembered in this
 * browser (`localStorage`, like the sidebar and theme choices: Keigan keeps no server-side preference for it) and shared by every conversation on the
 * page, so the switch in the panel and the one on the chat page always agree.
 */
export const toolDetailsStorageKey = "keigan.chat.showToolDetails";

/** The stored text as the choice: anything but an explicit "false" (nothing stored, a stale value) leaves the details on. */
export function parseToolDetailsPreference(storedValue: string | null): boolean {
  return storedValue !== "false";
}

function readStoredPreference(): boolean {
  try {
    return parseToolDetailsPreference(window.localStorage.getItem(toolDetailsStorageKey));
  } catch {
    return true; // storage is blocked: the default holds for this page view
  }
}

let currentPreference = typeof window === "undefined" ? true : readStoredPreference();
const listeners = new Set<() => void>();

function writePreference(nextPreference: boolean): void {
  currentPreference = nextPreference;
  try {
    window.localStorage.setItem(toolDetailsStorageKey, String(nextPreference));
  } catch {
    // The choice still applies until the page is reloaded.
  }
  listeners.forEach((notifyListener) => notifyListener());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

export interface ToolDetailsPreference {
  showToolDetails: boolean;
  setShowToolDetails: (showToolDetails: boolean) => void;
}

export function useToolDetailsPreference(): ToolDetailsPreference {
  const showToolDetails = useSyncExternalStore(subscribe, () => currentPreference, () => true);
  return { showToolDetails, setShowToolDetails: useCallback((value: boolean) => writePreference(value), []) };
}
