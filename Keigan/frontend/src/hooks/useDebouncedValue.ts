import { useEffect, useState } from "react";

/** Returns `value` after it has stopped changing for `delayMilliseconds` (default 300 ms). */
export function useDebouncedValue<ValueType>(value: ValueType, delayMilliseconds = 300): ValueType {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeoutHandle = window.setTimeout(() => setDebouncedValue(value), delayMilliseconds);
    return () => window.clearTimeout(timeoutHandle);
  }, [value, delayMilliseconds]);

  return debouncedValue;
}
