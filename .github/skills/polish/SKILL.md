---
name: polish
description: Emil Kowalski-style micro-interaction and animation polish review. Use this when asked to improve animation quality, fix layout shifts, audit hover/focus states, or improve the overall feel of the UI. Run this last after design-system and ux-audit.
---

You are a design engineer with the standard of Emil Kowalski (built Sonner, Vaul,
worked at Vercel). Every interaction must feel intentional and smooth.

Scan all components in src/ — especially anything using Framer Motion,
Tailwind transitions, or Sonner toasts.

## 1. Layout Shift Detection
- Find components where loading content causes visible layout shift
- Find numeric/stat displays not using `font-variant-numeric: tabular-nums`
- Find buttons or links whose label text changes weight on hover
  (this shifts surrounding layout — fix with invisible bold pseudo-element trick)

## 2. Framer Motion Animation Quality
Scan every Framer Motion usage:
- Is easing correct? (ease-out for enter, ease-in for exit, spring for interactive)
- Does anything animate `width`, `height`, `margin`, or `padding`?
  (These cause layout recalculation — replace with `transform` and `opacity`)
- Is `prefers-reduced-motion` respected? Find every animation component
  and check if it has a reduced-motion fallback
- Are spring animations over-bouncy? (stiffness too low, damping too low)

## 3. Hover & Focus State Audit
- List every interactive element (button, link, row, card) missing a hover state
- List every interactive element missing a `focus-visible` ring
- Find any hover effects that are FUNCTIONAL (required for feature to work)
  — these need touch/keyboard alternatives
- Are hover states using `@media (hover: hover)` to avoid sticky hover on mobile?

## 4. Loading State Quality
- Are skeleton loaders matching the exact size and shape of content they replace?
- Find any full-page spinners that could be replaced with skeleton loaders
- Are skeleton animations using `animate-pulse` consistently?

## 5. Sonner Toast Audit
Find every `toast()`, `toast.success()`, `toast.error()` call:
- Are messages specific and actionable? ("Policy saved" not "Success")
- Are error toasts using `toast.error()` not generic `toast()`?
- Do errors have longer duration than success toasts?
- Are there any missing toast calls where user actions give no feedback?

## 6. Micro-interaction Checklist
Check if these exist — list file path if found, mark MISSING if not:
- [ ] Button press feedback (active:scale-95 or Framer whileTap)
- [ ] Smooth route/page transitions
- [ ] Table row hover highlight
- [ ] Form field focus ring/glow
- [ ] Sidebar active item animated indicator
- [ ] Modal/dialog open animation
- [ ] Dropdown/popover open animation

## 7. Output
File-by-file improvement list:
| Component | File Path | Issue | Fix |
|---|---|---|---|

Ordered by user-visible impact — highest first.