/** A piece of text: plain, or one citation code such as `T2` (a tool call), `E3` (evidence) or `R1` (a runbook). */
export type CitationTextPart = { kind: "text"; text: string } | { kind: "citation"; code: string };

const citationCodePattern = /\[(T\d{1,2}|E\d{1,3}|R\d{1,2})\]/g;

/**
 * Splits text at its bracketed citation codes (`[T2]`, `[E3]`, `[R1]`; the same codes the server keeps in an answer). Text without a code
 * comes back as a single text part, and the parts always join back to the original text with the brackets restored.
 */
export function splitCitationCodes(text: string): CitationTextPart[] {
  const parts: CitationTextPart[] = [];
  let textStart = 0;
  for (const match of text.matchAll(citationCodePattern)) {
    parts.push({ kind: "text", text: text.slice(textStart, match.index) }, { kind: "citation", code: match[1] ?? "" });
    textStart = match.index + match[0].length;
  }
  parts.push({ kind: "text", text: text.slice(textStart) });
  return parts;
}
