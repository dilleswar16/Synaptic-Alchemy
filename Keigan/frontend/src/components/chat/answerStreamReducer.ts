import type { AnswerEvent, AnswerRunView, AnswerStartedEvent, RunStepView } from "@/api/askKeiganApi";

/**
 * State of the answers asked in this browser session (spec 7.6), built from the event protocol (7.3) and from stored snapshots. Everything here is
 * pure, so the protocol can be tested without a browser; `useAnswerStream` wires it to the stream, the cancel call and the polling recovery.
 */

/** A step as built from events: the same shape as a stored step, numbered by the server (`sequenceNumber`). */
export type LiveRunStep = RunStepView;

/** The part of `AnswerRunView` the screen draws; both a stream-built run and a stored snapshot satisfy it, so one renderer serves both. */
export type AnswerRunProgress = Pick<
  AnswerRunView,
  "answerRunId" | "status" | "stopReason" | "startedAt" | "completedAt" | "durationMilliseconds" | "toolCallCount" | "maximumToolCalls" | "answer" | "error" | "lastSequence"
> & { steps: LiveRunStep[] };

export interface ToolProgress {
  stage: string;
  detail: Record<string, unknown> | null;
}

/** `lost`: following the run by polling failed for too long; the person can check again. The run itself may still be going on the server. */
export type StreamConnection = "streaming" | "reconnecting" | "stopping" | "lost" | "closed";

export interface LiveAnswerRun {
  progress: AnswerRunProgress;
  userMessage: AnswerStartedEvent["userMessage"];
  /** Paragraphs of the model turn in progress; becomes the answer on `answer.completed` or a note on `turn.note`. */
  streamingText: { turnNumber: number; text: string } | null;
  /** Latest `tool.progress` per step id (`query_logs` reports `query_generated` with the query it wrote). */
  toolProgress: Readonly<Record<string, ToolProgress>>;
  connection: StreamConnection;
}

export interface AnswerStreamState {
  /** The question that was sent and has no run yet (the POST is in flight). */
  pendingQuestion: string | null;
  runs: LiveAnswerRun[];
}

export type AnswerStreamAction =
  | { kind: "question_sent"; messageText: string }
  | { kind: "question_failed" }
  | { kind: "event"; event: AnswerEvent }
  | { kind: "snapshot"; snapshot: AnswerRunView }
  | { kind: "connection"; answerRunId: string; connection: StreamConnection }
  /** The run cannot be followed any more (the server says it is gone or the person lost access): the stored conversation shows what is left of it. */
  | { kind: "run_dropped"; answerRunId: string };

export const initialAnswerStreamState: AnswerStreamState = { pendingQuestion: null, runs: [] };

/** The steps in the order the server ran them, whichever of a note and its tools arrived first. */
function insertStep(steps: LiveRunStep[], step: LiveRunStep): LiveRunStep[] {
  return [...steps, step].sort((first, second) => first.sequenceNumber - second.sequenceNumber);
}

function updateStep(steps: LiveRunStep[], runStepId: string, update: (step: LiveRunStep) => LiveRunStep): LiveRunStep[] {
  return steps.map((step) => (step.runStepId === runStepId ? update(step) : step));
}

/** After the last event no step is still running: whatever was in flight when the run ended counts as cancelled. */
function settleRunningSteps(steps: LiveRunStep[]): LiveRunStep[] {
  return steps.map((step) => (step.status === "running" ? { ...step, status: "cancelled" } : step));
}

function startLiveRun(event: AnswerStartedEvent): LiveAnswerRun {
  return {
    progress: {
      answerRunId: event.answerRunId,
      status: "running",
      stopReason: null,
      startedAt: event.emittedAt,
      completedAt: null,
      durationMilliseconds: null,
      toolCallCount: 0,
      maximumToolCalls: event.maximumToolCalls,
      steps: [],
      answer: null,
      error: null,
      lastSequence: event.sequence,
    },
    userMessage: event.userMessage,
    streamingText: null,
    toolProgress: {},
    connection: "streaming",
  };
}

/** Applies one event of the protocol (spec 7.3) to a run. Events already seen (`sequence` not above the last one) and unknown shapes change nothing. */
export function reduceAnswerEvent(run: LiveAnswerRun, event: AnswerEvent): LiveAnswerRun {
  if (event.type === "answer.started" || event.sequence <= run.progress.lastSequence) {
    return run;
  }
  const progress = { ...run.progress, lastSequence: event.sequence };
  switch (event.type) {
    case "answer.text": {
      const isSameTurn = run.streamingText?.turnNumber === event.turnNumber;
      const text = isSameTurn && run.streamingText ? `${run.streamingText.text}\n\n${event.text.trim()}` : event.text.trim();
      return { ...run, progress, streamingText: { turnNumber: event.turnNumber, text } };
    }
    case "turn.note": {
      if (progress.steps.some((step) => step.runStepId === event.runStepId)) {
        return { ...run, progress };
      }
      const noteStep: LiveRunStep = {
        runStepId: event.runStepId,
        sequenceNumber: event.sequenceNumber,
        kind: "model_turn",
        status: "succeeded",
        startedAt: event.emittedAt,
        durationMilliseconds: null,
        note: event.text,
        tool: null,
      };
      return {
        ...run,
        progress: { ...progress, steps: insertStep(progress.steps, noteStep) },
        streamingText: run.streamingText?.turnNumber === event.turnNumber ? null : run.streamingText,
      };
    }
    case "tool.started": {
      const toolStep: LiveRunStep = {
        runStepId: event.runStepId,
        sequenceNumber: event.sequenceNumber,
        kind: "tool_call",
        status: "running",
        startedAt: event.emittedAt,
        durationMilliseconds: null,
        note: null,
        tool: {
          ...event.tool,
          boundArgumentNames: event.boundArgumentNames,
          citationCode: event.citationCode,
          arguments: event.arguments,
          target: { ...event.target, records: [] },
          summary: null,
          outputPreview: null,
          outputCharacterCount: 0,
          outputIsTruncated: false,
          itemCount: null,
          isSimulated: null,
          totalCount: null,
          isTruncated: null,
          maskedValueCount: 0,
          injectionFlagged: false,
          outcomeCode: null,
          outcomeMessage: null,
          isRedacted: false,
        },
      };
      return {
        ...run,
        progress: { ...progress, steps: insertStep(progress.steps, toolStep), toolCallCount: progress.toolCallCount + (event.citationCode ? 1 : 0) },
      };
    }
    case "tool.progress":
      return { ...run, progress, toolProgress: { ...run.toolProgress, [event.runStepId]: { stage: event.stage, detail: event.detail } } };
    case "tool.finished": {
      const steps = updateStep(progress.steps, event.runStepId, (step) =>
        step.tool
          ? {
              ...step,
              status: event.status,
              durationMilliseconds: event.durationMilliseconds,
              tool: {
                ...step.tool,
                target: { ...step.tool.target, records: event.records },
                summary: event.summary,
                outputPreview: event.outputPreview,
                outputCharacterCount: event.outputCharacterCount,
                outputIsTruncated: event.outputIsTruncated,
                itemCount: event.itemCount,
                isSimulated: event.isSimulated,
                totalCount: event.totalCount,
                isTruncated: event.isTruncated,
                maskedValueCount: event.maskedValueCount,
                injectionFlagged: event.injectionFlagged,
                outcomeCode: event.outcomeCode,
                outcomeMessage: event.outcomeMessage,
              },
            }
          : step,
      );
      return { ...run, progress: { ...progress, steps } };
    }
    case "answer.completed":
      return {
        ...run,
        progress: {
          ...progress,
          status: "completed",
          stopReason: event.stopReason,
          completedAt: event.emittedAt,
          durationMilliseconds: event.durationMilliseconds,
          toolCallCount: event.toolCallCount,
          steps: settleRunningSteps(progress.steps),
          answer: event.answer,
        },
        streamingText: null,
      };
    case "answer.failed":
      return {
        ...run,
        progress: {
          ...progress,
          status: event.stopReason === "cancelled_by_user" ? "cancelled" : "failed",
          stopReason: event.stopReason,
          completedAt: event.emittedAt,
          durationMilliseconds: Date.parse(event.emittedAt) - Date.parse(progress.startedAt),
          steps: settleRunningSteps(progress.steps),
          error: event.error,
        },
        streamingText: null,
      };
  }
}

function updateRun(state: AnswerStreamState, answerRunId: string, update: (run: LiveAnswerRun) => LiveAnswerRun): AnswerStreamState {
  return { ...state, runs: state.runs.map((run) => (run.progress.answerRunId === answerRunId ? update(run) : run)) };
}

export function answerStreamReducer(state: AnswerStreamState, action: AnswerStreamAction): AnswerStreamState {
  switch (action.kind) {
    case "question_sent":
      return { ...state, pendingQuestion: action.messageText };
    case "question_failed":
      return { ...state, pendingQuestion: null };
    case "event": {
      const { event } = action;
      if (event.type === "answer.started") {
        const isKnownRun = state.runs.some((run) => run.progress.answerRunId === event.answerRunId);
        return { pendingQuestion: null, runs: isKnownRun ? state.runs : [...state.runs, startLiveRun(event)] };
      }
      return updateRun(state, event.answerRunId, (run) => reduceAnswerEvent(run, event));
    }
    case "snapshot":
      // The stored run is the truth: it replaces what the events built, including the streamed text.
      return updateRun(state, action.snapshot.answerRunId, (run) => ({ ...run, progress: action.snapshot, streamingText: null }));
    case "connection":
      return updateRun(state, action.answerRunId, (run) => ({ ...run, connection: action.connection }));
    case "run_dropped":
      return { ...state, runs: state.runs.filter((run) => run.progress.answerRunId !== action.answerRunId) };
  }
}

/** Whether this browser is still waiting for the run to end: it is running and its progress can still arrive (a `lost` connection cannot deliver it). */
export function isRunInProgress(run: LiveAnswerRun): boolean {
  return run.progress.status === "running" && run.connection !== "lost";
}
