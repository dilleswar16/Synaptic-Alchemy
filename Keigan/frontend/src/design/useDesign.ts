import { useSyncExternalStore } from "react";

/**
 * Keigan's own design: "mono" (the default) or "classic" (the original blue design in styles/tokens.css).
 * Sets `data-design` on <html>, keeps the choice in localStorage and loads Mono's font the first time it is needed.
 * Light and dark are the app's normal theme (hooks/useTheme.ts).
 */

export type DesignId = "mono" | "classic";

export interface DesignOption {
  id: DesignId;
  name: string;
  description: string;
}

export const designOptions: readonly DesignOption[] = [
  { id: "mono", name: "Mono", description: "Ink and white with one green for buttons and dots. Inter." },
  { id: "classic", name: "Classic", description: "The original blue design. Figtree and Noto Sans." },
];

export const defaultDesignId: DesignId = "mono";

const designStorageKey = "keigan.design";
const monoFontHref = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap";
const designListeners = new Set<() => void>();

let currentDesignId: DesignId = defaultDesignId;
let isMonoFontRequested = false;

function isDesignId(value: unknown): value is DesignId {
  return designOptions.some((option) => option.id === value);
}

/** Requests Mono's font (once). The Design system page calls this to preview Mono while Classic is active. */
export function loadMonoFont(): void {
  if (isMonoFontRequested) {
    return;
  }
  isMonoFontRequested = true;
  const fontLink = document.createElement("link");
  fontLink.rel = "stylesheet";
  fontLink.href = monoFontHref;
  document.head.appendChild(fontLink);
}

function applyDesignToDocument(designId: DesignId): void {
  const rootElement = document.documentElement;
  rootElement.classList.add("theme-switching");
  rootElement.dataset.design = designId;
  if (designId === "mono") {
    loadMonoFont();
  }
  window.requestAnimationFrame(() => rootElement.classList.remove("theme-switching"));
}

/** Called once from main.tsx before the first render to avoid a flash of the wrong design. */
export function initializeDesign(): void {
  try {
    const storedValue = window.localStorage.getItem(designStorageKey);
    currentDesignId = isDesignId(storedValue) ? storedValue : defaultDesignId;
  } catch {
    currentDesignId = defaultDesignId;
  }
  applyDesignToDocument(currentDesignId);
}

export function setDesign(designId: DesignId): void {
  if (designId === currentDesignId) {
    return;
  }
  try {
    window.localStorage.setItem(designStorageKey, designId);
  } catch {
    // Storage can be unavailable (private mode); the design still applies for this session.
  }
  currentDesignId = designId;
  applyDesignToDocument(designId);
  designListeners.forEach((notifyListener) => notifyListener());
}

function subscribeToDesign(onDesignChange: () => void): () => void {
  designListeners.add(onDesignChange);
  return () => designListeners.delete(onDesignChange);
}

function getDesignSnapshot(): DesignId {
  return currentDesignId;
}

export function useDesign(): { designId: DesignId; setDesign: (designId: DesignId) => void } {
  const designId = useSyncExternalStore(subscribeToDesign, getDesignSnapshot, getDesignSnapshot);
  return { designId, setDesign };
}
