import { useSyncExternalStore } from "react";

/**
 * Page background style (plain, dots, square grid, gradient, aurora, aurora grid) on top of the chosen design.
 * Sets `data-backdrop` on <html>; the rules live in styles/backdrops.css and are painted by the `app-backdrop` utility.
 * The choice is kept in localStorage.
 */

export type BackdropId = "plain" | "dots" | "grid" | "gradient" | "aurora" | "aurora-grid";

export interface BackdropOption {
  id: BackdropId;
  name: string;
  description: string;
}

export const backdropOptions: readonly BackdropOption[] = [
  { id: "plain", name: "Plain", description: "The flat canvas colour." },
  { id: "dots", name: "Dots", description: "A fine dotted grid." },
  { id: "grid", name: "Square grid", description: "Graph-paper lines." },
  { id: "gradient", name: "Gradient", description: "A soft diagonal wash." },
  { id: "aurora", name: "Aurora", description: "Glows in the brand colours from the corners." },
  { id: "aurora-grid", name: "Aurora grid", description: "Aurora glows over a square grid." },
];

export const defaultBackdropId: BackdropId = "plain";

const backdropStorageKey = "keigan.backdrop";
const backdropListeners = new Set<() => void>();

let currentBackdropId: BackdropId = defaultBackdropId;

function isBackdropId(value: unknown): value is BackdropId {
  return backdropOptions.some((option) => option.id === value);
}

function readStoredBackdrop(): BackdropId {
  try {
    const storedValue = window.localStorage.getItem(backdropStorageKey);
    return isBackdropId(storedValue) ? storedValue : defaultBackdropId;
  } catch {
    return defaultBackdropId;
  }
}

/** Called once from main.tsx before the first render to avoid a flash of the wrong background. */
export function initializeBackdrop(): void {
  currentBackdropId = readStoredBackdrop();
  document.documentElement.dataset.backdrop = currentBackdropId;
}

export function setBackdrop(backdropId: BackdropId): void {
  if (backdropId === currentBackdropId) {
    return;
  }
  try {
    window.localStorage.setItem(backdropStorageKey, backdropId);
  } catch {
    // Storage can be unavailable (private mode); the background still applies for this session.
  }
  currentBackdropId = backdropId;
  document.documentElement.dataset.backdrop = backdropId;
  backdropListeners.forEach((notifyListener) => notifyListener());
}

function subscribeToBackdrop(onBackdropChange: () => void): () => void {
  backdropListeners.add(onBackdropChange);
  return () => backdropListeners.delete(onBackdropChange);
}

function getBackdropSnapshot(): BackdropId {
  return currentBackdropId;
}

export function useBackdrop(): { backdropId: BackdropId; setBackdrop: (backdropId: BackdropId) => void } {
  const backdropId = useSyncExternalStore(subscribeToBackdrop, getBackdropSnapshot, getBackdropSnapshot);
  return { backdropId, setBackdrop };
}
