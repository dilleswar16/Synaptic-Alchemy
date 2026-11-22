import { useEffect, useState } from "react";

/** How often the elapsed time of a running tool call is redrawn (spec 8.3: "updated every second"). */
const elapsedTickMilliseconds = 1000;

/** Milliseconds since `startedAt`, redrawn every second while `isRunning`; frozen otherwise. */
export function useElapsedMilliseconds(startedAt: string, isRunning: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!isRunning) {
      return;
    }
    setNow(Date.now());
    const intervalHandle = window.setInterval(() => setNow(Date.now()), elapsedTickMilliseconds);
    return () => window.clearInterval(intervalHandle);
  }, [isRunning]);
  return Math.max(0, now - Date.parse(startedAt));
}
