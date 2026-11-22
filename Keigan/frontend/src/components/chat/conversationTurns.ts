import type { ChatMessage } from "@/api/chatApi";
import type { LiveAnswerRun } from "./answerStreamReducer";

/** What the person asked in one turn; `messageId` is absent for a question that has been sent but not stored yet. */
export interface TurnQuestion {
  messageId: string | null;
  messageText: string;
}

/**
 * One question and Keigan's side of it. Exactly one of `liveRun`, `storedAnswerRunId`, `earlierAnswer` or `isStarting` describes the
 * answer; none of them means a question whose answer is not stored (for example one that was stopped).
 */
export interface ConversationTurn {
  key: string;
  question: TurnQuestion | null;
  /** A run asked in this browser session: drawn from its events, so the cards stay as they were while the run ends. */
  liveRun: LiveAnswerRun | null;
  /** A stored run: its snapshot is loaded from the server. */
  storedAnswerRunId: string | null;
  /** An answer from before runs existed (it has no `answerRunId`): drawn as it always was. */
  earlierAnswer: ChatMessage | null;
  /** The question was sent and the first event has not arrived. */
  isStarting: boolean;
}

/**
 * Whether two lists of turns drew the same turn: `buildConversationTurns` makes new objects on every call, so the views compare what a turn is
 * made of (the run objects are replaced only when an event changes them).
 */
export function areConversationTurnsEqual(first: ConversationTurn, second: ConversationTurn): boolean {
  return (
    first.key === second.key &&
    first.question?.messageId === second.question?.messageId &&
    first.question?.messageText === second.question?.messageText &&
    first.liveRun === second.liveRun &&
    first.storedAnswerRunId === second.storedAnswerRunId &&
    first.earlierAnswer === second.earlierAnswer &&
    first.isStarting === second.isStarting
  );
}

const emptyTurn = { question: null, liveRun: null, storedAnswerRunId: null, earlierAnswer: null, isStarting: false } as const;

/**
 * Lines up the stored messages, the runs of this session and the question still being sent as one list of turns. The server links a stored question
 * to its run from the start (`answerRunId`), so an answer that is still running, was stopped or failed (and has no answer message) is found after a
 * reload. A live run replaces the stored copy of the same question (matched by the user message id), so nothing is drawn twice while the stored
 * conversation catches up.
 */
export function buildConversationTurns(messages: readonly ChatMessage[], liveRuns: readonly LiveAnswerRun[], pendingQuestion: string | null): ConversationTurn[] {
  const turns: ConversationTurn[] = [];
  for (const message of messages) {
    const lastTurn = turns.at(-1);
    if (message.authorRole === "user") {
      turns.push({
        ...emptyTurn,
        key: message.messageId,
        question: { messageId: message.messageId, messageText: message.messageText },
        storedAnswerRunId: message.messagePayload?.answerRunId ?? null,
      });
      continue;
    }
    const answerRunId = message.messagePayload?.answerRunId ?? null;
    if (answerRunId !== null && lastTurn?.storedAnswerRunId === answerRunId) {
      continue; // the question already points at this run, whose stored snapshot carries the answer
    }
    const answerFields = { storedAnswerRunId: answerRunId, earlierAnswer: answerRunId ? null : message };
    const canJoinLastTurn = lastTurn !== undefined && lastTurn.storedAnswerRunId === null && lastTurn.earlierAnswer === null;
    if (canJoinLastTurn) {
      turns[turns.length - 1] = { ...lastTurn, ...answerFields };
    } else {
      turns.push({ ...emptyTurn, ...answerFields, key: message.messageId });
    }
  }

  for (const liveRun of liveRuns) {
    const { messageId, messageText } = liveRun.userMessage;
    const storedTurnIndex = turns.findIndex((turn) => turn.question?.messageId === messageId);
    // The key is the run id before and after the stored conversation catches up, so the turn is not remounted when it does.
    const liveTurn: ConversationTurn = { ...emptyTurn, key: liveRun.progress.answerRunId, question: { messageId, messageText }, liveRun };
    if (storedTurnIndex === -1) {
      turns.push(liveTurn);
    } else {
      turns[storedTurnIndex] = liveTurn;
    }
  }

  if (pendingQuestion !== null) {
    turns.push({ ...emptyTurn, key: "pending-question", question: { messageId: null, messageText: pendingQuestion }, isStarting: true });
  }
  return turns;
}
