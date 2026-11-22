import { useEffect, type RefObject } from "react";

const focusableSelector = ["a[href]", "button:not([disabled])", "textarea:not([disabled])", "input:not([disabled])", "select:not([disabled])", '[tabindex]:not([tabindex="-1"])'].join(",");

/**
 * Where Tab should go instead of leaving the trap: the first element when Tab is pressed on the last (or from outside the list), the last when
 * Shift+Tab is pressed on the first; null when the browser's own next step stays inside.
 */
export function nextFocusTrapTarget<T extends object>(focusableElements: readonly T[], activeElement: object | null, isBackwards: boolean): T | null {
  const first = focusableElements.at(0);
  const last = focusableElements.at(-1);
  if (first === undefined || last === undefined) {
    return null;
  }
  const isInside = focusableElements.some((element) => element === activeElement);
  if (!isInside) {
    return isBackwards ? last : first;
  }
  if (isBackwards && activeElement === first) {
    return last;
  }
  return !isBackwards && activeElement === last ? first : null;
}

function visibleFocusableElements(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(focusableSelector)].filter((element) => element.getClientRects().length > 0);
}

/**
 * Keeps Tab and Shift+Tab inside `containerReference` while `isActive` (a full-screen sheet): without it the keyboard would move to the page behind.
 * Dialogs opened from inside (a drawer in a portal) are not inside the container's DOM, so they keep their own trap.
 */
export function useFocusTrap(containerReference: RefObject<HTMLElement | null>, isActive: boolean): void {
  useEffect(() => {
    const container = containerReference.current;
    if (!container || !isActive) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") {
        return;
      }
      const target = nextFocusTrapTarget(visibleFocusableElements(container), document.activeElement, event.shiftKey);
      if (target) {
        event.preventDefault();
        target.focus();
      }
    };
    container.addEventListener("keydown", onKeyDown);
    return () => container.removeEventListener("keydown", onKeyDown);
  }, [containerReference, isActive]);
}
