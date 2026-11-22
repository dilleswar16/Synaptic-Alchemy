import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, apiStream, isApiError } from "@/api/httpClient";
import { parseServerSentEvents } from "@/api/serverSentEvents";
import type { Identifier, IsoDateTimeString } from "@/api/types/common";

/**
 * Ask Keigan (spec 23): one chat that calls read-only tools and shows every call. Types mirror the API contract of section 7:
 * the snapshot (7.2), the event protocol (7.3) and the endpoints (7.1). Keys inside tool arguments and tool outputs are the tool's own
 * `snake_case` names; everything else is camelCase.
 */

/* ── Snapshot (7.2) ────────────────────────────────────────────────── */
export type AskKeiganScope = "global" | "investigation";
export type AnswerRunStatus = "running" | "completed" | "failed" | "cancelled";
export type AnswerStopReason = "answered" | "tool_limit_reached" | "token_budget_reached" | "cancelled_by_user" | "failed";
export type RunStepKind = "model_turn" | "tool_call";
export type RunStepStatus = "running" | "succeeded" | "failed" | "refused" | "skipped" | "cancelled";
export type ToolCallingMode = "native" | "prompted_json" | "scripted_mock";
export type ToolPresentation = "record_list" | "record" | "metrics" | "series" | "query_result" | "passages" | "graph";

export interface RecordReference {
  kind: "incident" | "investigation" | "evidence" | "alert_group" | "slo" | "signal" | "runbook" | "knowledge_document" | "application" | "service" | "topology" | "team";
  id: Identifier;
  label: string;
  applicationId: Identifier;
}

export interface RunStepToolView {
  name: string;
  /** The arguments the scope fixed (the model never chose them): the card shows them as "set by this investigation". */
  boundArgumentNames: string[];
  label: string;
  labelKey: string;
  source: string;
  presentation: ToolPresentation;
  citationCode: string | null;
  arguments: Record<string, unknown>;
  target: { applicationId: Identifier | null; applicationName: string | null; records: RecordReference[] };
  summary: string | null;
  /** The masked output (an object, or text when the server cut it at the preview limit); the full output comes from `fetchStepOutput`. */
  outputPreview: unknown;
  outputCharacterCount: number;
  outputIsTruncated: boolean;
  itemCount: number | null;
  /** The three trust flags of the output, computed by the server from the whole output (the preview may be cut); null while the call runs. */
  isSimulated: boolean | null;
  totalCount: number | null;
  isTruncated: boolean | null;
  maskedValueCount: number;
  injectionFlagged: boolean;
  outcomeCode: string | null;
  outcomeMessage: string | null;
  isRedacted: boolean;
}

export interface RunStepView {
  runStepId: Identifier;
  sequenceNumber: number;
  kind: RunStepKind;
  status: RunStepStatus;
  startedAt: IsoDateTimeString;
  durationMilliseconds: number | null;
  /** Text of a model turn that preceded tool calls: shown in the trace, never as the answer. */
  note: string | null;
  /** Set for a `tool_call` step, null for a model turn. */
  tool: RunStepToolView | null;
}

export interface Citation {
  code: string;
  runStepId?: Identifier;
  evidenceCode?: string;
  runbookId?: Identifier;
  title: string;
}

export interface AnswerView {
  messageId: Identifier;
  markdown: string;
  citations: Citation[];
  followUps: string[];
  isUnverified: boolean;
  isRefusal: boolean;
}

export interface ProblemSummary {
  errorCode: string;
  title: string;
  detail: string;
  correlationId: string | null;
  /** From the server's error catalogue (spec 4.10): "Try again" is offered only when true. */
  isRetryable: boolean;
  /** The low-sensitivity values the server's message was written from (a tool label, a limit, a delay); the title and detail are already localised. */
  parameters: Record<string, string | number>;
}

export interface AnswerRunView {
  answerRunId: Identifier;
  conversationId: Identifier;
  status: AnswerRunStatus;
  stopReason: AnswerStopReason | null;
  scope: AskKeiganScope;
  startedAt: IsoDateTimeString;
  completedAt: IsoDateTimeString | null;
  durationMilliseconds: number | null;
  toolCallCount: number;
  maximumToolCalls: number;
  inputTokenCount: number;
  outputTokenCount: number;
  tokenCountsEstimated: boolean;
  modelName: string;
  toolCallingMode: ToolCallingMode;
  steps: RunStepView[];
  answer: AnswerView | null;
  error: ProblemSummary | null;
  lastSequence: number;
}

export interface StepOutputView {
  runStepId: Identifier;
  output: unknown;
  outputCharacterCount: number;
  outputIsTruncated: boolean;
  modelViewText: string;
  modelViewSha256: string;
}

/* ── Events (7.3) ──────────────────────────────────────────────────── */
export const supportedAnswerEventVersion = 1;

interface AnswerEventBase {
  eventVersion: number;
  sequence: number;
  answerRunId: Identifier;
  emittedAt: IsoDateTimeString;
}

export interface ToolIdentity {
  name: string;
  label: string;
  labelKey: string;
  source: string;
  presentation: ToolPresentation;
}

export interface AnswerStartedEvent extends AnswerEventBase {
  type: "answer.started";
  userMessage: { messageId: Identifier; messageText: string; createdAt: IsoDateTimeString };
  scope: AskKeiganScope;
  offeredTools: Array<{ name: string; label: string; labelKey: string }>;
  maximumToolCalls: number;
}

export interface AnswerTextEvent extends AnswerEventBase {
  type: "answer.text";
  turnNumber: number;
  text: string;
}

export interface TurnNoteEvent extends AnswerEventBase {
  type: "turn.note";
  turnNumber: number;
  runStepId: Identifier;
  /** The step's number in the run (the same as in the snapshot): the cards are ordered by it. */
  sequenceNumber: number;
  text: string;
}

export interface ToolStartedEvent extends AnswerEventBase {
  type: "tool.started";
  runStepId: Identifier;
  sequenceNumber: number;
  parentRunStepId: Identifier | null;
  citationCode: string | null;
  boundArgumentNames: string[];
  tool: ToolIdentity;
  arguments: Record<string, unknown>;
  target: { applicationId: Identifier | null; applicationName: string | null };
}

export interface ToolProgressEvent extends AnswerEventBase {
  type: "tool.progress";
  runStepId: Identifier;
  sequenceNumber: number;
  stage: string;
  detail: Record<string, unknown> | null;
}

export interface ToolFinishedEvent extends AnswerEventBase {
  type: "tool.finished";
  runStepId: Identifier;
  sequenceNumber: number;
  status: Exclude<RunStepStatus, "running" | "cancelled">;
  durationMilliseconds: number | null;
  summary: string | null;
  outputPreview: unknown;
  outputCharacterCount: number;
  outputIsTruncated: boolean;
  itemCount: number | null;
  isSimulated: boolean | null;
  totalCount: number | null;
  isTruncated: boolean | null;
  records: RecordReference[];
  maskedValueCount: number;
  injectionFlagged: boolean;
  outcomeCode: string | null;
  outcomeMessage: string | null;
}

export interface AnswerCompletedEvent extends AnswerEventBase {
  type: "answer.completed";
  answer: AnswerView;
  stopReason: AnswerStopReason;
  toolCallCount: number;
  inputTokenCount: number;
  outputTokenCount: number;
  durationMilliseconds: number;
}

export interface AnswerFailedEvent extends AnswerEventBase {
  type: "answer.failed";
  error: ProblemSummary;
  stopReason: Extract<AnswerStopReason, "failed" | "cancelled_by_user">;
}

export type AnswerEvent =
  | AnswerStartedEvent
  | AnswerTextEvent
  | TurnNoteEvent
  | ToolStartedEvent
  | ToolProgressEvent
  | ToolFinishedEvent
  | AnswerCompletedEvent
  | AnswerFailedEvent;

const answerEventTypes: ReadonlySet<string> = new Set<AnswerEvent["type"]>([
  "answer.started",
  "answer.text",
  "turn.note",
  "tool.started",
  "tool.progress",
  "tool.finished",
  "answer.completed",
  "answer.failed",
]);

export function isFinalAnswerEvent(event: AnswerEvent): event is AnswerCompletedEvent | AnswerFailedEvent {
  return event.type === "answer.completed" || event.type === "answer.failed";
}

/** What `streamAnswer` reports when the response body ends. */
export type StreamEnd =
  /** The run's last frame (`answer.completed` or `answer.failed`) arrived. */
  | "final_event_received"
  /** The connection ended first: the run may still be going on the server; recover by polling the snapshot (spec 7.5). */
  | "connection_ended"
  /** The server speaks a newer event protocol than this client; nothing more was read. */
  | "unsupported_event_version";

type DecodedFrame = { kind: "event"; event: AnswerEvent } | { kind: "unsupported_version" } | { kind: "ignored" };

/**
 * Turns one server-sent frame into an `AnswerEvent`. Unknown event names and malformed data are ignored so a newer server stays compatible
 * (spec 7.6); a frame from a newer protocol version is reported so the screen can ask for a reload.
 */
export function decodeAnswerEventFrame(eventName: string, data: string): DecodedFrame {
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    return { kind: "ignored" };
  }
  if (!payload || typeof payload !== "object") {
    return { kind: "ignored" };
  }
  const { eventVersion } = payload as { eventVersion?: unknown };
  if (typeof eventVersion === "number" && eventVersion > supportedAnswerEventVersion) {
    return { kind: "unsupported_version" };
  }
  if (!answerEventTypes.has(eventName)) {
    return { kind: "ignored" };
  }
  return { kind: "event", event: { ...(payload as object), type: eventName } as AnswerEvent };
}

/* ── Endpoints (7.1) ───────────────────────────────────────────────── */
export interface AnswerRequest {
  messageText: string;
  /** A fresh UUID per question; the server answers a repeated id with `409 duplicate_request` instead of asking twice. */
  clientRequestId: string;
}

/**
 * Asks a question and reports every event of the answer as it arrives (server-sent events over a POST, spec 7.4). Resolves when the body
 * ends; rejects with `ApiError` for an error before the stream starts (rate limit, no access, answer already running …) and with an
 * `AbortError` when `signal` aborts.
 */
export async function streamAnswer(conversationId: string, request: AnswerRequest, onEvent: (event: AnswerEvent) => void, signal: AbortSignal): Promise<StreamEnd> {
  const response = await apiStream(`/chat/conversations/${conversationId}/answers`, request, { signal });
  if (!response.body) {
    return "connection_ended";
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bufferedText = "";
  try {
    for (;;) {
      const chunk = await readNextChunk(reader);
      if (!chunk || chunk.done) {
        return "connection_ended";
      }
      const parsed = parseServerSentEvents(bufferedText + decoder.decode(chunk.value, { stream: true }));
      bufferedText = parsed.remainder;
      for (const frame of parsed.frames) {
        const decodedFrame = decodeAnswerEventFrame(frame.event, frame.data);
        if (decodedFrame.kind === "unsupported_version") {
          return "unsupported_event_version";
        }
        if (decodedFrame.kind === "event") {
          onEvent(decodedFrame.event);
          if (isFinalAnswerEvent(decodedFrame.event)) {
            return "final_event_received";
          }
        }
      }
    }
  } finally {
    void reader.cancel().catch(() => undefined);
  }
}

/** The next chunk of the body, or null when the connection dropped mid-stream; an abort of the caller's signal is rethrown. */
async function readNextChunk(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<ReadableStreamReadResult<Uint8Array> | null> {
  try {
    return await reader.read();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    return null;
  }
}

export const askKeiganQueryKeys = {
  answerRun: (answerRunId: string) => ["chat", "answer-run", answerRunId] as const,
  stepOutput: (answerRunId: string, runStepId: string) => ["chat", "answer-run", answerRunId, "step-output", runStepId] as const,
};

export function fetchAnswerRun(answerRunId: string): Promise<AnswerRunView> {
  return apiGet<AnswerRunView>(`/chat/answer-runs/${answerRunId}`);
}

/** Polling spec of 7.5: every second, every three seconds once a run has been going for 20 polls. */
export const answerRunPollFastIntervalMilliseconds = 1000;
export const answerRunPollSlowIntervalMilliseconds = 3000;
export const answerRunPollFastPollCount = 20;
/** Polls in a row that may fail (server error, rate limit, no connection) before the screen stops waiting and offers "Check again": about a minute at the slow interval. */
export const answerRunPollMaximumConsecutiveFailures = 20;

/** The wait before the next read of a running run's snapshot, after `pollCount` reads. */
export function answerRunPollIntervalMilliseconds(pollCount: number): number {
  return pollCount < answerRunPollFastPollCount ? answerRunPollFastIntervalMilliseconds : answerRunPollSlowIntervalMilliseconds;
}

/** A finished run does not change, so it is reused for this long before it is read again. */
const storedRunStaleTimeMilliseconds = 30_000;

/** Why a stored run cannot be shown: the person no longer has access to it (403), or its detailed trace is no longer kept (404, 410). Null for any other failure. */
export function runUnavailableReason(error: unknown): "redacted" | "expired" | null {
  if (!isApiError(error)) {
    return null;
  }
  if (error.status === 403) {
    return "redacted";
  }
  return error.status === 404 || error.status === 410 ? "expired" : null;
}

/** A stored answer run (conversation history). Polls while the run is still `running`, so a reload during an answer catches up. A run the server will not show is not asked for again when the window gets focus: the answer would be the same, and the caption would flash. */
export function useAnswerRun(answerRunId: string | null, enabled = true) {
  return useQuery({
    queryKey: askKeiganQueryKeys.answerRun(answerRunId ?? ""),
    queryFn: () => fetchAnswerRun(answerRunId ?? ""),
    enabled: enabled && Boolean(answerRunId),
    staleTime: storedRunStaleTimeMilliseconds,
    refetchOnWindowFocus: (query) => runUnavailableReason(query.state.error) === null,
    refetchInterval: (query) => {
      if (query.state.data?.status !== "running") {
        return false;
      }
      return answerRunPollIntervalMilliseconds(query.state.dataUpdateCount);
    },
  });
}

/** The full stored output of one tool call, loaded when its drawer opens. */
export function useStepOutput(answerRunId: string, runStepId: string, enabled: boolean) {
  return useQuery({
    queryKey: askKeiganQueryKeys.stepOutput(answerRunId, runStepId),
    queryFn: () => apiGet<StepOutputView>(`/chat/answer-runs/${answerRunId}/steps/${runStepId}/output`),
    enabled,
    staleTime: Infinity,
  });
}

/** Asks the server to stop a running answer; resolves also when it had already finished (`409 answer_not_running`). */
export async function cancelAnswerRun(answerRunId: string): Promise<void> {
  await apiPost<unknown>(`/chat/answer-runs/${answerRunId}/cancel`).catch((error: unknown) => {
    if (!isApiError(error) || error.errorCode !== "answer_not_running") {
      throw error;
    }
  });
}
