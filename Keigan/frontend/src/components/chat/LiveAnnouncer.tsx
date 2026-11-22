import { useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import type { AnswerRunProgress } from "./answerStreamReducer";
import { toolTargetLabel } from "./toolCardState";

/** At most one announcement per this time, so a burst of tool calls is not read out one by one (spec 8.8). */
const announcementMinimumGapMilliseconds = 2000;

export interface RunAnnouncement {
  /** Identifies the moment being announced; the same key is never announced twice. */
  key: string;
  text: string;
}

/**
 * What a screen reader should hear about a run right now: the tool call in progress or just finished, or how the answer ended. Failures are
 * not announced here: the error banner is an alert of its own, and a stored failed run is not announced again when a conversation is reopened.
 */
export function describeRunAnnouncement(progress: AnswerRunProgress, translate: TFunction): RunAnnouncement | null {
  if (progress.status === "completed") {
    const text =
      progress.stopReason === "answered" || progress.stopReason === null
        ? translate("answer.announceReady", { count: progress.answer?.citations.length ?? 0 })
        : translate(`trace.stopped.${progress.stopReason}`, { maximum: progress.maximumToolCalls });
    return { key: `${progress.answerRunId}:completed`, text };
  }
  if (progress.status === "cancelled") {
    return { key: `${progress.answerRunId}:cancelled`, text: translate("trace.stopped.cancelled_by_user") };
  }
  const latestToolStep = progress.steps.findLast((step) => step.tool);
  const tool = latestToolStep?.tool;
  if (!latestToolStep || !tool || progress.status !== "running") {
    return null;
  }
  const label = translate(tool.labelKey, { defaultValue: tool.label });
  const key = `${latestToolStep.runStepId}:${latestToolStep.status}`;
  if (latestToolStep.status === "running") {
    const target = toolTargetLabel(tool);
    return { key, text: target ? translate("tool.announceStartedFor", { label, target }) : translate("tool.announceStarted", { label }) };
  }
  return { key, text: translate("tool.announceFinished", { label, summary: tool.outcomeMessage ?? tool.summary ?? "" }) };
}

/** A visually hidden polite status region (one per conversation) that speaks `announcement`, throttled and coalesced. */
export function LiveAnnouncer({ announcement }: { announcement: RunAnnouncement | null }) {
  const [message, setMessage] = useState("");
  const lastAnnouncedKeyReference = useRef<string | null>(null);
  const lastAnnouncedAtReference = useRef(0);
  const key = announcement?.key;
  const text = announcement?.text;

  useEffect(() => {
    if (key === undefined || text === undefined || key === lastAnnouncedKeyReference.current) {
      return;
    }
    // A newer announcement replaces one still waiting for its turn, so only the latest of a burst is spoken.
    const waitMilliseconds = Math.max(0, announcementMinimumGapMilliseconds - (Date.now() - lastAnnouncedAtReference.current));
    const timeoutHandle = window.setTimeout(() => {
      lastAnnouncedKeyReference.current = key;
      lastAnnouncedAtReference.current = Date.now();
      setMessage(text);
    }, waitMilliseconds);
    return () => window.clearTimeout(timeoutHandle);
  }, [key, text]);

  return <div role="status" aria-live="polite" className="sr-only">{message}</div>;
}
