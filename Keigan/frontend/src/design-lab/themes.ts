/**
 * The companies in the design lab. Each one has a file in ./themes (CSS) generated from its DESIGN.md in /design.
 * `fontHref` loads the closest free font for the company's own (usually licensed) typeface; `fontNote` says which.
 */

export type LabId = "stripe" | "coinbase" | "mongodb" | "voltagent" | "spotify" | "lovable" | "starbucks";

export interface LabTheme {
  id: LabId;
  company: string;
  /** The mode the company's file is written for; the other mode is derived from it. */
  nativeMode: "light" | "dark" | "both";
  fontNote: string;
  fontHref: string;
}

const fontsBase = "https://fonts.googleapis.com/css2?family=";

export const labThemes: readonly LabTheme[] = [
  { id: "stripe", company: "Stripe", nativeMode: "light", fontNote: "Geist stands in for Söhne", fontHref: `${fontsBase}Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap` },
  { id: "coinbase", company: "Coinbase", nativeMode: "light", fontNote: "Inter stands in for Coinbase Sans", fontHref: `${fontsBase}Inter:wght@400;500;600;700&display=swap` },
  { id: "mongodb", company: "MongoDB", nativeMode: "both", fontNote: "Albert Sans stands in for Euclid Circular A", fontHref: `${fontsBase}Albert+Sans:wght@400;500;600;700&family=Source+Code+Pro:wght@400;500&display=swap` },
  { id: "voltagent", company: "VoltAgent", nativeMode: "dark", fontNote: "Inter, as in the file", fontHref: `${fontsBase}Inter:wght@400;500;600;700&display=swap` },
  { id: "spotify", company: "Spotify", nativeMode: "dark", fontNote: "Figtree stands in for SpotifyMixUI", fontHref: `${fontsBase}Figtree:wght@400;500;600;700&display=swap` },
  { id: "lovable", company: "Lovable", nativeMode: "light", fontNote: "Instrument Sans stands in for Camera Plain", fontHref: `${fontsBase}Instrument+Sans:wght@400;500;600;700&display=swap` },
  { id: "starbucks", company: "Starbucks", nativeMode: "light", fontNote: "Inter stands in for SoDoSans, as the file suggests", fontHref: `${fontsBase}Inter:wght@400;500;600;700&display=swap` },
];
