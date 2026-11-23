import { describe, expect, it } from "vitest";
import type { FixParameter, FixSegment } from "@/api/investigationsApi";
import catalogueText from "../../../../../backend/keigan/resources/catalogs/fix_parameter_kinds.yaml?raw";
import vectorsText from "../../../../../backend/tests/support/fix_value_quoting_vectors.json?raw";
import { composeCommand, quoteValue, valueProblem } from "./fixCommandComposer";

/** The backend's own test list and kind catalogue: both implementations must give the same answer on every line (spec 33, 5.2). */
const vectors = JSON.parse(vectorsText) as {
  bare_safe: string[];
  needs_quotes: Array<{ value: string; quoted: string }>;
  never_insertable: Array<{ kind: string; value: string; refusal: string }>;
  insertable: Array<{ kind: string; value: string }>;
};
const kinds = new Map(
  [...catalogueText.matchAll(/^ {2}([a-z_]+): \{ pattern: '(.*?)', maximum_length: (\d+),/gm)].map((match) => [match[1] ?? "", { valuePattern: match[2] ?? "", maximumLength: Number(match[3]) }]),
);
const barePattern = /^bare_safe_pattern: '(.*)'$/m.exec(catalogueText)?.[1] ?? "";

function parameterOf(kind: string, name = "value"): FixParameter {
  const rules = kinds.get(kind);
  return {
    name, valueKind: kind, value: null, valueSource: "unknown", sourceCode: null, status: "missing", statusReason: "not_known",
    valuePattern: rules?.valuePattern ?? null, barePattern, maximumLength: rules?.maximumLength ?? null, labelKey: kind,
  };
}

const literal = (text: string): FixSegment => ({ kind: "literal", text, parameterName: null });
const gap = (parameterName: string): FixSegment => ({ kind: "missing_value", text: "", parameterName });

describe("the shared quoting and value vectors", () => {
  it("reads the catalogue", () => {
    expect(kinds.size).toBeGreaterThanOrEqual(12);
    expect(barePattern).toContain("A-Za-z0-9");
  });

  it.each(vectors.bare_safe)("inserts %s as it is", (value) => {
    expect(quoteValue(value, barePattern)).toBe(value);
  });

  it.each(vectors.needs_quotes)("wraps $value in single quotes", ({ value, quoted }) => {
    expect(quoteValue(value, barePattern)).toBe(quoted);
  });

  it.each(vectors.never_insertable.filter((vector) => kinds.has(vector.kind)))("refuses $value as $kind with the reason the server gives", ({ kind, value, refusal }) => {
    expect(valueProblem(parameterOf(kind), value)).toBe(refusal);
  });

  it.each(vectors.insertable)("accepts $value as $kind", ({ kind, value }) => {
    expect(valueProblem(parameterOf(kind), value)).toBeNull();
  });
});

describe("composeCommand", () => {
  const segments = [literal("az webapp restart --name claims-web-jp --resource-group "), gap("resource_group")];
  const parameters = [parameterOf("azure_resource_group", "resource_group")];

  it("returns the server's text unchanged when nothing is missing", () => {
    expect(composeCommand([literal("kubectl get pods -n "), { kind: "value", text: "claims-prod", parameterName: "namespace" }], [], {})).toEqual({ kind: "ready", text: "kubectl get pods -n claims-prod" });
  });

  it("is incomplete until every gap has a value", () => {
    expect(composeCommand(segments, parameters, {})).toEqual({ kind: "incomplete", missing: ["resource_group"] });
    expect(composeCommand(segments, parameters, { resource_group: "   " })).toEqual({ kind: "incomplete", missing: ["resource_group"] });
  });

  it("puts a typed value in its gap, bare when it is safe and in single quotes when it is not", () => {
    expect(composeCommand(segments, parameters, { resource_group: "rg-claims-jp-prod" })).toEqual({ kind: "ready", text: "az webapp restart --name claims-web-jp --resource-group rg-claims-jp-prod" });
    expect(composeCommand(segments, parameters, { resource_group: "rg-claims(jp)" })).toEqual({ kind: "ready", text: "az webapp restart --name claims-web-jp --resource-group 'rg-claims(jp)'" });
  });

  it("refuses a value that breaks its kind's rules and says which", () => {
    expect(composeCommand(segments, parameters, { resource_group: "rg; rm -rf /" })).toEqual({ kind: "invalid", problems: [{ parameterName: "resource_group", problem: "pattern" }] });
    expect(composeCommand(segments, parameters, { resource_group: "<EMAIL_1>" })).toEqual({ kind: "invalid", problems: [{ parameterName: "resource_group", problem: "masked" }] });
  });

  it("never inserts a value that needs quotes next to literal text", () => {
    const glued = [literal("kubectl set env x A="), gap("value")];
    expect(composeCommand(glued, [parameterOf("configuration_value")], { value: "max pool size" })).toEqual({ kind: "not_insertable", parameterName: "value" });
    expect(composeCommand(glued, [parameterOf("configuration_value")], { value: "200" })).toEqual({ kind: "ready", text: "kubectl set env x A=200" });
  });
});
