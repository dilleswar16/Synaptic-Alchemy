import { useSyncExternalStore } from "react";

/**
 * Selectable design system (colour, type and corner treatment) on top of the light / dark theme.
 * Sets `data-design` on <html>; the token overrides for each design live in styles/designs.css and the default
 * ("fresh") lives in styles/tokens.css. The choice is kept in localStorage and is made on the Design system page or
 * from the top bar. Fonts a design needs are requested the first time it is shown or chosen.
 */

export type DesignId = "fresh" | "indigo" | "azure" | "graphite" | "coral" | "ocean" | "violet" | "ledger" | "classic";

export interface DesignOption {
  id: DesignId;
  /** Product-style name shown in the menu; not translated. */
  name: string;
  description: string;
  /** Google Fonts stylesheet for fonts the design adds beyond the ones index.html already loads. */
  fontHref: string | null;
}

const fontsBase = "https://fonts.googleapis.com/css2?family=";

export const designOptions: readonly DesignOption[] = [
  { id: "fresh", name: "Fresh", description: "Light green on off-white. Plus Jakarta Sans.", fontHref: null },
  { id: "indigo", name: "Indigo", description: "Lavender-white with one indigo accent. Manrope.", fontHref: `${fontsBase}Manrope:wght@500;600;700;800&display=swap` },
  { id: "azure", name: "Azure", description: "Cool slate with a precise blue accent. Geist.", fontHref: `${fontsBase}Geist:wght@400;500;600;700&display=swap` },
  { id: "graphite", name: "Graphite", description: "Near-monochrome, one teal accent, tight corners. DM Sans.", fontHref: `${fontsBase}DM+Sans:wght@400;500;600;700&display=swap` },
  { id: "coral", name: "Coral", description: "Navy buttons on cool grey, coral highlights. Hanken Grotesk.", fontHref: `${fontsBase}Hanken+Grotesk:wght@400;500;600;700&display=swap` },
  { id: "ocean", name: "Ocean", description: "Sea-glass canvas with a cyan-teal accent. Outfit.", fontHref: `${fontsBase}Outfit:wght@400;500;600;700&display=swap` },
  { id: "violet", name: "Violet", description: "Soft lavender with a violet accent and a mint finish. Onest.", fontHref: `${fontsBase}Onest:wght@400;500;600;700&display=swap` },
  { id: "ledger", name: "Ledger", description: "Ink buttons and lime highlights on paper. Instrument Sans.", fontHref: `${fontsBase}Instrument+Sans:wght@400;500;600;700&display=swap` },
  { id: "classic", name: "Classic", description: "The original MetLife blue. Figtree and Noto Sans.", fontHref: `${fontsBase}Figtree:wght@500;600;700&display=swap` },
];

export const defaultDesignId: DesignId = "fresh";

const designStorageKey = "keigan.design";
const designListeners = new Set<() => void>();
const loadedFontHrefs = new Set<string>();

let currentDesignId: DesignId = defaultDesignId;

function isDesignId(value: unknown): value is DesignId {
  return designOptions.some((option) => option.id === value);
}

function readStoredDesign(): DesignId {
  try {
    const storedValue = window.localStorage.getItem(designStorageKey);
    return isDesignId(storedValue) ? storedValue : defaultDesignId;
  } catch {
    return defaultDesignId;
  }
}

/** Requests the fonts a design needs (once). The Design system page calls this for every design to preview them. */
export function loadDesignFonts(designId: DesignId): void {
  const fontHref = designOptions.find((option) => option.id === designId)?.fontHref;
  if (!fontHref || loadedFontHrefs.has(fontHref)) {
    return;
  }
  loadedFontHrefs.add(fontHref);
  const fontLink = document.createElement("link");
  fontLink.rel = "stylesheet";
  fontLink.href = fontHref;
  document.head.appendChild(fontLink);
}

function applyDesignToDocument(designId: DesignId): void {
  const rootElement = document.documentElement;
  // Same one-frame transition pause the theme switch uses, so surfaces do not animate between designs.
  rootElement.classList.add("theme-switching");
  rootElement.dataset.design = designId;
  loadDesignFonts(designId);
  window.requestAnimationFrame(() => rootElement.classList.remove("theme-switching"));
}

/** Called once from main.tsx before the first render to avoid a flash of the wrong design. */
export function initializeDesign(): void {
  currentDesignId = readStoredDesign();
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
