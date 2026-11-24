import { useSyncExternalStore } from "react";
import { labThemes, type LabId } from "./themes";

/**
 * Which design-lab company is applied (or none: the app's own design). Sets `data-lab` on <html>, keeps the choice in
 * localStorage and loads the company's fonts when it is chosen or previewed. Light / dark is the app's normal theme.
 */

export type LabChoice = LabId | null;

const labStorageKey = "keigan.lab";
const labListeners = new Set<() => void>();
const loadedFontHrefs = new Set<string>();

let currentLab: LabChoice = null;

function isLabId(value: unknown): value is LabId {
  return labThemes.some((theme) => theme.id === value);
}

export function loadLabFonts(labId: LabId): void {
  const fontHref = labThemes.find((theme) => theme.id === labId)?.fontHref;
  if (!fontHref || loadedFontHrefs.has(fontHref)) {
    return;
  }
  loadedFontHrefs.add(fontHref);
  const fontLink = document.createElement("link");
  fontLink.rel = "stylesheet";
  fontLink.href = fontHref;
  document.head.appendChild(fontLink);
}

function applyLabToDocument(labId: LabChoice): void {
  const rootElement = document.documentElement;
  rootElement.classList.add("theme-switching");
  if (labId) {
    rootElement.dataset.lab = labId;
    loadLabFonts(labId);
  } else {
    delete rootElement.dataset.lab;
  }
  window.requestAnimationFrame(() => rootElement.classList.remove("theme-switching"));
}

/** Called once from main.tsx before the first render to avoid a flash of the wrong design. */
export function initializeDesignLab(): void {
  try {
    const storedValue = window.localStorage.getItem(labStorageKey);
    currentLab = isLabId(storedValue) ? storedValue : null;
  } catch {
    currentLab = null;
  }
  applyLabToDocument(currentLab);
}

export function setDesignLab(labId: LabChoice): void {
  if (labId === currentLab) {
    return;
  }
  try {
    if (labId) {
      window.localStorage.setItem(labStorageKey, labId);
    } else {
      window.localStorage.removeItem(labStorageKey);
    }
  } catch {
    // Storage can be unavailable (private mode); the design still applies for this session.
  }
  currentLab = labId;
  applyLabToDocument(labId);
  labListeners.forEach((notifyListener) => notifyListener());
}

function subscribeToLab(onLabChange: () => void): () => void {
  labListeners.add(onLabChange);
  return () => labListeners.delete(onLabChange);
}

function getLabSnapshot(): LabChoice {
  return currentLab;
}

export function useDesignLab(): { labId: LabChoice; setLab: (labId: LabChoice) => void } {
  const labId = useSyncExternalStore(subscribeToLab, getLabSnapshot, getLabSnapshot);
  return { labId, setLab: setDesignLab };
}
