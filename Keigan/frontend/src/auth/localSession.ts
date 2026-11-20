/**
 * Local-mode session (AUTH_MODE=local only). The short-lived local token is kept in sessionStorage so it
 * disappears with the tab; Entra tokens are never stored here (MSAL keeps its own session cache).
 */

export interface LocalSession {
  accessToken: string;
  expiresAt: string;
}

export type SessionEndReason = "signedOut" | "expired" | "rejected";

const localSessionStorageKey = "keigan.localSession";
const sessionListeners = new Set<() => void>();
let lastSessionEndReason: SessionEndReason | null = null;

function notifySessionListeners(): void {
  sessionListeners.forEach((notifyListener) => notifyListener());
}

export function readLocalSession(): LocalSession | null {
  try {
    const storedValue = window.sessionStorage.getItem(localSessionStorageKey);
    if (!storedValue) {
      return null;
    }
    const session = JSON.parse(storedValue) as LocalSession;
    if (!session.accessToken || Date.parse(session.expiresAt) <= Date.now()) {
      window.sessionStorage.removeItem(localSessionStorageKey);
      lastSessionEndReason = "expired";
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function writeLocalSession(session: LocalSession): void {
  try {
    window.sessionStorage.setItem(localSessionStorageKey, JSON.stringify(session));
  } catch {
    // Without sessionStorage the user has to sign in again after a reload; nothing else breaks.
  }
  lastSessionEndReason = null;
  notifySessionListeners();
}

export function clearLocalSession(reason: SessionEndReason): void {
  try {
    window.sessionStorage.removeItem(localSessionStorageKey);
  } catch {
    // Ignore storage failures.
  }
  lastSessionEndReason = reason;
  notifySessionListeners();
}

export function getLastSessionEndReason(): SessionEndReason | null {
  return lastSessionEndReason;
}

export function subscribeToLocalSession(onSessionChange: () => void): () => void {
  sessionListeners.add(onSessionChange);
  return () => sessionListeners.delete(onSessionChange);
}
