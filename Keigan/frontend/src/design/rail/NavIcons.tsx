import type { ReactNode } from "react";

/**
 * Two-tone navigation icons for the navigation rail. Each has a soft filled shape (it turns green when the item is the
 * current page) and one or two parts that move on hover (see rail.css). They are drawn on a 24 px grid with a 1.6
 * stroke so they sit with the app's other line icons.
 */

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg className="ni" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

const icons: Record<string, () => ReactNode> = {
  home: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
      <path d="M3.5 11.5L12 4l8.5 7.5M5 10v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9" />
      <path className="ni-door" d="M10 20v-5h4v5" />
    </Svg>
  ),
  incidents: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M7 20v-6a5 5 0 0 1 10 0v6z" />
      <path d="M7 20v-6a5 5 0 0 1 10 0v6M5 20h14" />
      <path className="ni-rays" d="M12 3v1.5M4.8 6.3l1.1 1.1M19.2 6.3l-1.1 1.1" />
    </Svg>
  ),
  alerts: () => (
    <Svg>
      <g className="ni-bell">
        <path className="ni-fill" stroke="none" d="M6 16c1.5-1.3 2-3.2 2-6a4 4 0 0 1 8 0c0 2.8.5 4.7 2 6z" />
        <path d="M6 16c1.5-1.3 2-3.2 2-6a4 4 0 0 1 8 0c0 2.8.5 4.7 2 6zM12 4V3" />
      </g>
      <path className="ni-clapper" d="M10.2 19a2 2 0 0 0 3.6 0" />
    </Svg>
  ),
  actionItems: () => (
    <Svg>
      <rect className="ni-fill" stroke="none" x="5" y="4" width="14" height="16" rx="2.5" />
      <rect x="5" y="4" width="14" height="16" rx="2.5" />
      <path className="ni-draw" d="M8.8 12.2l2.2 2.2 4.2-4.6" />
    </Svg>
  ),
  slo: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M4.5 17a7.5 7.5 0 1 1 15 0z" />
      <path d="M4.5 17a7.5 7.5 0 1 1 15 0M4 17h16" />
      <path className="ni-needle" d="M12 17l3.5-4.5" />
    </Svg>
  ),
  intelligence: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M5 19v-3.5l4-4 3 3 5-6.5V19z" />
      <path d="M4 4v15a1 1 0 0 0 1 1h15" />
      <path className="ni-draw" d="M7.5 15.5l3.5-3.5 3 3 5-6.5" />
      <circle className="ni-dot" cx="19" cy="8.5" r="1.1" fill="currentColor" />
    </Svg>
  ),
  metrics: () => (
    <Svg>
      <path className="ni-bar ni-bar-1" strokeWidth="2.6" d="M6.5 20v-6" />
      <path className="ni-bar ni-bar-2" strokeWidth="2.6" d="M12 20V6" />
      <path className="ni-bar ni-bar-3" strokeWidth="2.6" d="M17.5 20v-9" />
    </Svg>
  ),
  chat: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M10 4l1.7 4.3L16 10l-4.3 1.7L10 16l-1.7-4.3L4 10l4.3-1.7z" />
      <path d="M10 4l1.7 4.3L16 10l-4.3 1.7L10 16l-1.7-4.3L4 10l4.3-1.7z" />
      <path className="ni-twinkle" d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8z" />
    </Svg>
  ),
  applications: () => (
    <Svg>
      <rect className="ni-sq ni-sq-1 ni-fill" x="4" y="4" width="6.5" height="6.5" rx="1.5" />
      <rect className="ni-sq ni-sq-2" x="13.5" y="4" width="6.5" height="6.5" rx="1.5" />
      <rect className="ni-sq ni-sq-3" x="4" y="13.5" width="6.5" height="6.5" rx="1.5" />
      <rect className="ni-sq ni-sq-4" x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" />
    </Svg>
  ),
  platformSettings: () => (
    <Svg>
      <path d="M4 7h16M4 12h16M4 17h16" />
      <circle className="ni-knob ni-knob-1 ni-fill" cx="9" cy="7" r="2.1" />
      <circle className="ni-knob ni-knob-2" cx="15.5" cy="12" r="2.1" />
      <circle className="ni-knob ni-knob-3" cx="8" cy="17" r="2.1" />
    </Svg>
  ),
  usageAndAudit: () => (
    <Svg>
      <circle className="ni-fill" stroke="none" cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.5" />
      <path className="ni-sweep" d="M12 12l5-4.2" />
    </Svg>
  ),
  outbox: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M20 4L4 10.5l6.2 2.3L12.5 20z" />
      <path d="M20 4L4 10.5l6.2 2.3L12.5 20z" />
      <path className="ni-plane" d="M10.2 12.8L20 4" />
    </Svg>
  ),
  designSystem: () => (
    <Svg>
      <path className="ni-fill" stroke="none" d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.4-1.8-.4-1 .2-2.2 1.4-2.2H17a3.5 3.5 0 0 0 3.5-3.5C20.5 7 16.8 3.5 12 3.5z" />
      <path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.4-1.8-.4-1 .2-2.2 1.4-2.2H17a3.5 3.5 0 0 0 3.5-3.5C20.5 7 16.8 3.5 12 3.5z" />
      <circle className="ni-dot ni-dot-1" cx="8" cy="11" r="1" fill="currentColor" />
      <circle className="ni-dot ni-dot-2" cx="11" cy="7.5" r="1" fill="currentColor" />
      <circle className="ni-dot ni-dot-3" cx="15.5" cy="8.5" r="1" fill="currentColor" />
    </Svg>
  ),
};

/** The icon for a navigation item key, or null when this set has none (the caller falls back to the app's icon). */
export function NavIcon({ name }: { name: string }): ReactNode {
  return icons[name]?.() ?? null;
}
