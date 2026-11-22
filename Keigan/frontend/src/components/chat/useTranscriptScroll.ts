import { useCallback, useEffect, useRef, useState } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";

/** The transcript counts as "at the bottom" within this many pixels (spec 8.9). */
const bottomToleranceInPixels = 80;
/** A smooth scroll to the bottom is given this long to arrive; its intermediate scroll events do not count as the person scrolling away. */
const smoothScrollSettleMilliseconds = 600;

/** Whether a scroll position is at the bottom of its container, within the tolerance of spec 8.9. */
export function isScrolledToBottom({ scrollHeight, scrollTop, clientHeight }: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">): boolean {
  return scrollHeight - scrollTop - clientHeight <= bottomToleranceInPixels;
}

/**
 * Keeps a chat transcript following new content only while the person is at the bottom; if they scrolled up to read, it stays put and
 * `hasNewActivity` tells the screen to offer "New activity". `activityKey` must change whenever content is added or grows; it is null while the
 * transcript has nothing to follow (an empty conversation shows its suggestions from the top, where a tall one on a phone would otherwise start at its end).
 */
export function useTranscriptScroll(activityKey: string | null) {
  const scrollReference = useRef<HTMLDivElement>(null);
  const isAtBottomReference = useRef(true);
  const isSmoothScrollingReference = useRef(false);
  const settleTimerReference = useRef<number | undefined>(undefined);
  const [hasNewActivity, setHasNewActivity] = useState(false);
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => () => window.clearTimeout(settleTimerReference.current), []);

  const scrollToBottom = useCallback(() => {
    isAtBottomReference.current = true;
    setHasNewActivity(false);
    const transcript = scrollReference.current;
    if (!transcript) {
      return;
    }
    if (prefersReducedMotion) {
      transcript.scrollTo({ top: transcript.scrollHeight, behavior: "auto" });
      return;
    }
    // The scroll events of the animation are ours: until it arrives they must not read as the person leaving the bottom.
    isSmoothScrollingReference.current = true;
    window.clearTimeout(settleTimerReference.current);
    settleTimerReference.current = window.setTimeout(() => { isSmoothScrollingReference.current = false; }, smoothScrollSettleMilliseconds);
    transcript.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
  }, [prefersReducedMotion]);

  const onScroll = useCallback(() => {
    const transcript = scrollReference.current;
    if (!transcript || isSmoothScrollingReference.current) {
      return;
    }
    isAtBottomReference.current = isScrolledToBottom(transcript);
    if (isAtBottomReference.current) {
      setHasNewActivity(false);
    }
  }, []);

  useEffect(() => {
    const transcript = scrollReference.current;
    if (!transcript || activityKey === null) {
      return;
    }
    if (isAtBottomReference.current) {
      transcript.scrollTo({ top: transcript.scrollHeight });
    } else {
      setHasNewActivity(true);
    }
  }, [activityKey]);

  return { scrollReference, onScroll, hasNewActivity, scrollToBottom };
}
