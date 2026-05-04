---
name: design-system
description: Design system consistency audit. Use this when asked to check spacing, typography, colors, component duplication, or Tailwind token usage across the codebase.
---

You are a design systems engineer. Scan the entire src/ directory
and the tailwind.config file.

## 1. Spacing Audit
- Find all arbitrary Tailwind values (e.g., mt-[13px], p-[7px], gap-[18px])
- List each one with its file path and line number
- Propose a standardized replacement using the 4px/8px grid

## 2. Typography Audit
- List every font size class used across all components
- Is there a clear visual hierarchy? (display > h1 > h2 > body > caption > label)
- Are font weights intentional and consistent?
- Are any font sizes defined with arbitrary values?

## 3. Color Audit
- List all color classes used across the app
- Find any hardcoded hex values in className strings or style props
- Are semantic colors used for status indicators?
  (error = red, success = green, warning = amber, info = blue)
- Are there one-off colors that break the palette?

## 4. Component Duplication
- Find similar UI patterns implemented differently in multiple files
- Look for: multiple card styles, multiple button variants, multiple input styles,
  multiple modal/dialog patterns, multiple badge/tag styles
- List every duplicate with both file paths

## 5. Tailwind Config Review
- What custom tokens are defined?
- What is missing that would reduce arbitrary value usage?
- Recommend additions to the theme config

## 6. Output
Three sections:
1. Token system recommendations (what to add to tailwind.config.ts)
2. Component consolidation list (what to merge and where)
3. Fix priority order — most impactful first