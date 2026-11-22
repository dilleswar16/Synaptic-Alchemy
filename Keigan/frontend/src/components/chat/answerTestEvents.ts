import type {
  AnswerCompletedEvent,
  AnswerFailedEvent,
  AnswerRunView,
  AnswerStartedEvent,
  AnswerTextEvent,
  RunStepToolView,
  RunStepView,
  ToolFinishedEvent,
  ToolStartedEvent,
  TurnNoteEvent,
} from "@/api/askKeiganApi";

/** Builders for the events and snapshots of the tests: complete values with every field set, so a test names only what it is about. */

export const testRunId = "run-1";
const emittedAt = "2026-11-21T10:00:00Z";

function base(sequence: number) {
  return { eventVersion: 1, sequence, answerRunId: testRunId, emittedAt };
}

export function answerStarted(overrides: Partial<AnswerStartedEvent> = {}): AnswerStartedEvent {
  return {
    ...base(1),
    type: "answer.started",
    userMessage: { messageId: "message-1", messageText: "Is claims-api healthy?", createdAt: emittedAt },
    scope: "global",
    offeredTools: [],
    maximumToolCalls: 8,
    ...overrides,
  };
}

export function answerText(sequence: number, text: string, turnNumber = 1): AnswerTextEvent {
  return { ...base(sequence), type: "answer.text", turnNumber, text };
}

export function turnNote(sequence: number, runStepId: string, sequenceNumber: number, text = "Checking first.", turnNumber = 1): TurnNoteEvent {
  return { ...base(sequence), type: "turn.note", turnNumber, runStepId, sequenceNumber, text };
}

export function toolStarted(sequence: number, runStepId: string, sequenceNumber: number, overrides: Partial<ToolStartedEvent> = {}): ToolStartedEvent {
  return {
    ...base(sequence),
    type: "tool.started",
    runStepId,
    sequenceNumber,
    parentRunStepId: null,
    citationCode: `T${sequenceNumber}`,
    boundArgumentNames: [],
    tool: { name: "get_slo_status", label: "Checked SLO status", labelKey: "chat:tools.get_slo_status.label", source: "keigan", presentation: "metrics" },
    arguments: {},
    target: { applicationId: "app-1", applicationName: "Claims Processing (JP)" },
    ...overrides,
  };
}

export function toolFinished(sequence: number, runStepId: string, sequenceNumber: number, overrides: Partial<ToolFinishedEvent> = {}): ToolFinishedEvent {
  return {
    ...base(sequence),
    type: "tool.finished",
    runStepId,
    sequenceNumber,
    status: "succeeded",
    durationMilliseconds: 120,
    summary: "6 SLOs",
    outputPreview: { summary: "6 SLOs" },
    outputCharacterCount: 40,
    outputIsTruncated: false,
    itemCount: 6,
    isSimulated: false,
    totalCount: 6,
    isTruncated: false,
    records: [],
    maskedValueCount: 0,
    injectionFlagged: false,
    outcomeCode: null,
    outcomeMessage: null,
    ...overrides,
  };
}

export function answerCompleted(sequence: number, overrides: Partial<AnswerCompletedEvent> = {}): AnswerCompletedEvent {
  return {
    ...base(sequence),
    type: "answer.completed",
    answer: { messageId: "message-2", markdown: "All healthy [T1].", citations: [{ code: "T1", title: "SLO status" }], followUps: [], isUnverified: false, isRefusal: false },
    stopReason: "answered",
    toolCallCount: 1,
    inputTokenCount: 10,
    outputTokenCount: 5,
    durationMilliseconds: 900,
    ...overrides,
  };
}

export function answerFailed(sequence: number, overrides: Partial<AnswerFailedEvent> = {}): AnswerFailedEvent {
  return {
    ...base(sequence),
    type: "answer.failed",
    error: { errorCode: "ai_timeout", title: "The AI model did not answer", detail: "Try again.", correlationId: "corr-1", isRetryable: true, parameters: {} },
    stopReason: "failed",
    ...overrides,
  };
}

export function stepToolView(overrides: Partial<RunStepToolView> = {}): RunStepToolView {
  return {
    name: "get_slo_status",
    boundArgumentNames: [],
    label: "Checked SLO status",
    labelKey: "chat:tools.get_slo_status.label",
    source: "keigan",
    presentation: "metrics",
    citationCode: "T1",
    arguments: {},
    target: { applicationId: "app-1", applicationName: "Claims Processing (JP)", records: [] },
    summary: "6 SLOs",
    outputPreview: null,
    outputCharacterCount: 40,
    outputIsTruncated: false,
    itemCount: 6,
    isSimulated: false,
    totalCount: 6,
    isTruncated: false,
    maskedValueCount: 0,
    injectionFlagged: false,
    outcomeCode: null,
    outcomeMessage: null,
    isRedacted: false,
    ...overrides,
  };
}

export function toolStep(runStepId: string, sequenceNumber: number, overrides: Partial<RunStepView> = {}, tool: Partial<RunStepToolView> = {}): RunStepView {
  return { runStepId, sequenceNumber, kind: "tool_call", status: "succeeded", startedAt: emittedAt, durationMilliseconds: 120, note: null, tool: stepToolView(tool), ...overrides };
}

export function noteStep(runStepId: string, sequenceNumber: number, note = "Checking first."): RunStepView {
  return { runStepId, sequenceNumber, kind: "model_turn", status: "succeeded", startedAt: emittedAt, durationMilliseconds: null, note, tool: null };
}

export function snapshot(overrides: Partial<AnswerRunView> = {}): AnswerRunView {
  return {
    answerRunId: testRunId,
    conversationId: "conversation-1",
    status: "running",
    stopReason: null,
    scope: "global",
    startedAt: emittedAt,
    completedAt: null,
    durationMilliseconds: null,
    toolCallCount: 0,
    maximumToolCalls: 8,
    inputTokenCount: 0,
    outputTokenCount: 0,
    tokenCountsEstimated: false,
    modelName: "mock",
    toolCallingMode: "scripted_mock",
    steps: [],
    answer: null,
    error: null,
    lastSequence: 0,
    ...overrides,
  };
}
