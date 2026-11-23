import { useSyncExternalStore } from "react";
import { updatePreferences, type ThemePreference } from "@/api/authApi";
import { authBridge } from "@/auth/authBridge";

/**
 * Light / dark / system theme (doc 04 §1.2). Sets `data-theme` on <html>, persists the choice in localStorage
 * and, when signed in, on the user profile. One module-level store, so no provider is needed.
 */

export type { ThemePreference };
export type ResolvedTheme = "light" | "dark";

interface ThemeState {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
}

const themeStorageKey = "keigan.theme";
const themeListeners = new Set<() => void>();
const darkSchemeQuery = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

function isThemePreference(value: unknown): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}

function readStoredPreference(): ThemePreference {
  try {
    const storedValue = window.localStorage.getItem(themeStorageKey);
    return isThemePreference(storedValue) ? storedValue : "system";
  } catch {
    return "system";
  }
}

function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") {
    return darkSchemeQuery?.matches ? "dark" : "light";
  }
  return preference;
}

let themeState: ThemeState = { preference: "system", resolvedTheme: "light" };

function applyThemeToDocument(resolvedTheme: ResolvedTheme): void {
  const rootElement = document.documentElement;
  // Suppress transitions for one frame so surfaces do not animate between themes.
  rootElement.classList.add("theme-switching");
  rootElement.dataset.theme = resolvedTheme;
  rootElement.style.colorScheme = resolvedTheme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolvedTheme === "dark" ? "#0A1A14" : "#006C46");
  window.requestAnimationFrame(() => rootElement.classList.remove("theme-switching"));
}

function updateThemeState(preference: ThemePreference): void {
  const resolvedTheme = resolveTheme(preference);
  if (preference === themeState.preference && resolvedTheme === themeState.resolvedTheme) {
    return;
  }
  themeState = { preference, resolvedTheme };
  applyThemeToDocument(resolvedTheme);
  themeListeners.forEach((notifyListener) => notifyListener());
}

/** Called once from main.tsx before the first render to avoid a flash of the wrong theme. */
export function initializeTheme(): void {
  const preference = readStoredPreference();
  themeState = { preference, resolvedTheme: resolveTheme(preference) };
  applyThemeToDocument(themeState.resolvedTheme);
  darkSchemeQuery?.addEventListener("change", () => {
    if (themeState.preference === "system") {
      updateThemeState("system");
    }
  });
}

/**
 * Changes the theme. `persistToProfile` (default true) also saves it on the user profile when signed in;
 * failures are ignored because the local choice already applies.
 */
export function setThemePreference(preference: ThemePreference, options: { persistToProfile?: boolean } = {}): void {
  try {
    window.localStorage.setItem(themeStorageKey, preference);
  } catch {
    // Storage can be unavailable (private mode); the theme still applies for this session.
  }
  updateThemeState(preference);
  if ((options.persistToProfile ?? true) && authBridge.isAuthenticated()) {
    updatePreferences({ preferredTheme: preference }).catch(() => undefined);
  }
}

function subscribeToTheme(onThemeChange: () => void): () => void {
  themeListeners.add(onThemeChange);
  return () => themeListeners.delete(onThemeChange);
}

function getThemeSnapshot(): ThemeState {
  return themeState;
}

export function useTheme(): ThemeState & { setPreference: (preference: ThemePreference) => void } {
  const currentThemeState = useSyncExternalStore(subscribeToTheme, getThemeSnapshot, getThemeSnapshot);
  return { ...currentThemeState, setPreference: setThemePreference };
}
