import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import { buildAnswerWithSources } from "./answerCopyText";
import { noteStep, toolStep } from "./answerTestEvents";

const dictionary: Record<string, string> = {
  "answer.sourcesHeading": "Sources",
  "answer.askedOn": "Asked in Keigan on {{date}}",
  "answer.sourceLine": "[{{code}}] {{details}}",
  "answer.sourcePartSeparator": " | ",
  "answer.inputsLine": "Inputs: {{inputs}}",
  "tool.fieldPair": "{{label}}: {{value}}",
  "tool.yes": "Yes",
  "tool.no": "No",
  "tool.noValue": "-",
};

/** A translator with a small dictionary and `{{name}}` interpolation; a key it does not know answers with its `defaultValue`. */
const translate = ((key: string, options: Record<string, unknown> = {}) =>
  (dictionary[key] ?? (typeof options.defaultValue === "string" ? options.defaultValue : key)).replace(/\{\{(\w+)\}\}/g, (_match, name: string) => String(options[name]))) as unknown as TFunction;

const answer = {
  markdown: "  The SLO is breached [T1] and a deploy came first [T2].  ",
  citations: [
    { code: "T1", title: "SLO status" },
    { code: "T2", title: "Recent changes", runStepId: "step-2" },
    { code: "E3", title: "Evidence three" },
  ],
};

describe("buildAnswerWithSources", () => {
  const steps = [
    noteStep("note-1", 1),
    toolStep("step-1", 2, {}, { citationCode: "T1", arguments: { application_code: "claims", failures_only: true }, outputPreview: { secret_raw_output: "do-not-copy" } }),
    toolStep("step-2", 3, {}, { citationCode: "T2", label: "Checked recent changes", labelKey: "unknown.key", summary: "2 changes", target: { applicationId: "app-1", applicationName: "Claims Processing (JP)", records: [] } }),
  ];

  it("copies the answer, a sources list that maps every code, and the date", () => {
    const text = buildAnswerWithSources({ answer, steps, answeredAt: "2026-11-21T10:00:00Z", translate });
    const sections = text.split("\n\n");
    expect(sections[0]).toBe("The SLO is breached [T1] and a deploy came first [T2].");
    const sourceLines = (sections[1] ?? "").split("\n");
    expect(sourceLines[0]).toBe("Sources");
    expect(sourceLines).toHaveLength(4);
    expect(sections[2]).toMatch(/^Asked in Keigan on /);
  });

  it("writes a tool source as its label, target, inputs and summary, joined by the locale separator", () => {
    const text = buildAnswerWithSources({ answer, steps, answeredAt: null, translate });
    expect(text).toContain("[T1] Checked SLO status | Claims Processing (JP) | Inputs: Application code: claims, Failures only: Yes | 6 SLOs");
    expect(text).toContain("[T2] Checked recent changes | Claims Processing (JP) | 2 changes");
  });

  it("finds the step of a citation by its step id when the server sent one, and by the tool's own code otherwise", () => {
    const text = buildAnswerWithSources({ answer, steps: [toolStep("step-2", 3, {}, { citationCode: "T9", label: "By id" })], answeredAt: null, translate });
    expect(text).toContain("[T2] By id");
  });

  it("writes evidence and runbooks as their title only", () => {
    expect(buildAnswerWithSources({ answer, steps, answeredAt: null, translate })).toContain("[E3] Evidence three");
  });

  it("never copies a raw tool output", () => {
    expect(buildAnswerWithSources({ answer, steps, answeredAt: null, translate })).not.toContain("do-not-copy");
  });

  it("leaves out the sources and the date when there are none", () => {
    expect(buildAnswerWithSources({ answer: { markdown: "Plain.", citations: [] }, steps: [], answeredAt: null, translate })).toBe("Plain.");
  });
});
