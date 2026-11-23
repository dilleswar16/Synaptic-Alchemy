import type { FixParameter, FixSegment } from "@/api/investigationsApi";

/** Why a typed value cannot be used, in the order the server checks (`check_value`): the same rules, so a value the screen accepts is a value the server would have inserted. */
export type ValueProblem = "masked" | "too_long" | "starts_with_dash" | "pattern";

const maskingPlaceholder = /^<[A-Z][A-Z_]*(_[0-9]+)?>$/;

export function valueProblem(parameter: Pick<FixParameter, "valuePattern" | "maximumLength">, value: string): ValueProblem | null {
  if (maskingPlaceholder.test(value)) {
    return "masked";
  }
  if (parameter.maximumLength !== null && value.length > parameter.maximumLength) {
    return "too_long";
  }
  if (value.startsWith("-")) {
    return "starts_with_dash";
  }
  // `^…$` also matches before a trailing newline in JavaScript when the `m` flag is set, never without it; a value with a line break fails every kind's character class anyway.
  return parameter.valuePattern !== null && !new RegExp(parameter.valuePattern).test(value) ? "pattern" : null;
}

/** Bare when it needs no quotes, otherwise in single quotes: correct in bash and PowerShell because no valid value contains a quote character. */
export function quoteValue(value: string, barePattern: string): string {
  return new RegExp(barePattern).test(value) ? value : `'${value}'`;
}

export type ComposeResult =
  | { kind: "ready"; text: string }
  | { kind: "incomplete"; missing: string[] }
  | { kind: "invalid"; problems: Array<{ parameterName: string; problem: ValueProblem }> }
  /** A value that needs quotes would touch the literal text around it, which no quoting rule handles in both shells. */
  | { kind: "not_insertable"; parameterName: string };

/**
 * The command a person copies: the server's segments with the values they typed in the gaps. Nothing is guessed: an empty gap is `incomplete`, a value that breaks its kind's rules is `invalid`,
 * and a value that would need quotes next to literal text is `not_insertable`. A rendering the server already completed is returned as it is.
 */
export function composeCommand(segments: FixSegment[], parameters: FixParameter[], entered: Record<string, string>): ComposeResult {
  const parameterByName = new Map(parameters.map((parameter) => [parameter.name, parameter]));
  const missing: string[] = [];
  const problems: Array<{ parameterName: string; problem: ValueProblem }> = [];
  const parts: string[] = [];
  for (const [position, segment] of segments.entries()) {
    if (segment.kind !== "missing_value") {
      parts.push(segment.text);
      continue;
    }
    const name = segment.parameterName ?? "";
    const parameter = parameterByName.get(name);
    const value = (entered[name] ?? "").trim();
    if (value === "") {
      missing.push(name);
      continue;
    }
    const problem = parameter ? valueProblem(parameter, value) : "pattern";
    if (problem) {
      problems.push({ parameterName: name, problem });
      continue;
    }
    const barePattern = parameter?.barePattern ?? "^$";
    const isBare = new RegExp(barePattern).test(value);
    const before = segments[position - 1]?.text ?? "";
    const after = segments[position + 1]?.text ?? "";
    const isGlued = (before !== "" && !/\s$/.test(before)) || (after !== "" && !/^\s/.test(after));
    if (!isBare && isGlued) {
      return { kind: "not_insertable", parameterName: name };
    }
    parts.push(quoteValue(value, barePattern));
  }
  if (problems.length > 0) {
    return { kind: "invalid", problems };
  }
  if (missing.length > 0) {
    return { kind: "incomplete", missing };
  }
  return { kind: "ready", text: parts.join("") };
}
