import type { InvestigationDetail } from "@/api/investigationsApi";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { extractCitationCodes } from "./investigationPresentation";

/** The evidence chips for every `[E#]` a piece of AI text cites. */
export function CitationRow({ markdown, detail, onSelectEvidence }: { markdown: string | null; detail: InvestigationDetail; onSelectEvidence: (code: string) => void }) {
  const codes = extractCitationCodes(markdown);
  if (codes.length === 0) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-1.5 border-t border-hairline pt-3">
      {codes.map((code) => (
        <EvidenceChip key={code} code={code} title={detail.evidence.find((item) => item.evidenceCode === code)?.evidenceTitle} onSelect={onSelectEvidence} />
      ))}
    </div>
  );
}
