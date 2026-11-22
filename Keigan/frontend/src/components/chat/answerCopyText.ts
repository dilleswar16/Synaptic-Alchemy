import type { TFunction } from "i18next";
import type { AnswerView, Citation, RunStepView } from "@/api/askKeiganApi";
import { formatDate, formatList } from "@/utils/formatters";
import { toolTargetLabel } from "./toolCardState";
import { fieldLabel, formatFieldValue } from "./toolValues";

export interface AnswerCopyInput {
  answer: Pick<AnswerView, "markdown" | "citations">;
  steps: readonly RunStepView[];
  /** When the answer was finished; the "Asked in Keigan on" line is left out without it. */
  answeredAt: string | null;
  translate: TFunction;
}

/** The step a `[T#]` citation points at: by its step id when the server sent one, otherwise by the tool call's own citation code. */
function stepOfCitation(citation: Citation, steps: readonly RunStepView[]): RunStepView | undefined {
  return steps.find((step) => (citation.runStepId ? step.runStepId === citation.runStepId : step.tool?.citationCode === citation.code));
}

function describeInputs(step: RunStepView, translate: TFunction): string | null {
  const entries = Object.entries(step.tool?.arguments ?? {});
  if (entries.length === 0) {
    return null;
  }
  const pairs = entries.map(([name, value]) => translate("tool.fieldPair", { label: fieldLabel(translate, name, "arguments"), value: formatFieldValue(translate, value) }));
  return translate("answer.inputsLine", { inputs: formatList(pairs) });
}

/** One line of the sources list: `[T1] Checked SLO status — Claims Processing (JP) — Inputs: … — 6 SLOs: 4 healthy…` (the dash is the locale's own `answer.sourcePartSeparator`); evidence and runbooks have only their title. */
function describeSource(citation: Citation, steps: readonly RunStepView[], translate: TFunction): string {
  const step = stepOfCitation(citation, steps);
  const tool = step?.tool;
  const details = step && tool
    ? [
        translate(tool.labelKey, { defaultValue: tool.label }),
        toolTargetLabel(tool),
        describeInputs(step, translate),
        tool.summary,
      ]
    : [citation.title];
  return translate("answer.sourceLine", { code: citation.code, details: details.filter(Boolean).join(translate("answer.sourcePartSeparator")) });
}

/**
 * The text "Copy answer with sources" puts on the clipboard (spec 8.7): the answer as written, a Sources list that maps every code in it to the
 * tool, its inputs and what it found (or, for evidence and runbooks, to their title), and when it was asked. Plain text, in the person's language;
 * raw tool outputs are not copied.
 */
export function buildAnswerWithSources({ answer, steps, answeredAt, translate }: AnswerCopyInput): string {
  const sections = [answer.markdown.trim()];
  if (answer.citations.length > 0) {
    sections.push([translate("answer.sourcesHeading"), ...answer.citations.map((citation) => describeSource(citation, steps, translate))].join("\n"));
  }
  if (answeredAt) {
    sections.push(translate("answer.askedOn", { date: formatDate(answeredAt) }));
  }
  return sections.join("\n\n");
}
