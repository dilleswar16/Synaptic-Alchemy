# 04 — UI / UX design system

Corporate in colour, modern in craft. MetLife's palette and type rules (design.metlife.com) applied to a calm,
dense-but-breathable 2026 product UI: generous whitespace, soft depth, crisp hairlines, glass top bar,
subtle motion, and data that is always one click from its source.

## 1. Brand

### 1.1 Name and mark

- Wordmark: **Keigan** in the display font, weight 700, tracking −0.01em, preceded by the mark. Optional kanji **慧眼** in Noto Sans JP 500 at 60 % size, muted, after the wordmark in the sidebar header and login screen.
- Tagline: *The discerning eye for our systems.* (localised).
- **Mark (SVG, 32×32 grid):** an almond eye outline built from two arcs with a 2.25 px stroke using the brand gradient; inside, an iris circle (r = 6) filled with Dark Blue `#0061A0` and a smaller pupil highlight; a short green `#A4CE4E` arc on the iris lower-right suggesting a radar sweep / insight. Works at 16 px (favicon simplifies to iris + outline).
- Never place the mark on Blue 1 backgrounds below 32 px; on dark backgrounds the outline becomes white→green gradient.
- Component: `KeiganLogo` with props `variant: "full" | "mark"`, `size`, `showKanji`.

### 1.2 Colour (MetLife global palette)

| Token | Hex | Use |
|---|---|---|
| `--metlife-blue-1` | `#0090DA` | Brand moments, illustrations, charts, gradient |
| `--metlife-blue-2` | `#007ABC` | **Actionable items**: primary buttons, links, focus ring |
| `--metlife-dark-blue` | `#0061A0` | Button hover/pressed, sidebar active text, headings accent, logo iris |
| `--metlife-green` | `#A4CE4E` | Success fills, progress, positive deltas (fills only, never text) |
| `--metlife-green-dark` | `#528320` | Success **text and icons** (data-viz palette #14) |
| `--metlife-teal` | `#00ACA0` | Accent (charts, info illustration) — sparingly |
| `--metlife-purple` | `#5F259F` | Accent (AI moments: Keigan AI chat badge, hypotheses "Application" lane) |
| `--metlife-yellow` | `#FFC600` | Warning fills (with dark text) |
| `--metlife-berry` | `#DB0A5B` | Alert notifications, P2 |
| `--metlife-red` | `#D42123` | Errors, P1, destructive |
| `--metlife-light-gray` | `#F2F2F2` | Subtle fills |
| `--metlife-gray` | `#D9D9D6` | Strong borders, dividers |
| `--metlife-medium-gray` | `#A7A8AA` | Disabled, placeholders on dark |
| `--metlife-dark-gray` | `#6E6E6E` | Muted text (5.1:1 on white) |
| `--metlife-darkest-gray` | `#333333` | **All body text** |

MetLife rules we keep: ~70 % blue / 30 % green; never more than three colours in one moment; no Blue, Green or Black text; secondary colours never on actionable items;
white text on Blue 1 only ≥ 18 pt. Gradients only for brand moments, progress bars and secondary-CTA strokes — never on type.

**Semantic tokens (light theme)**

| Token | Value |
|---|---|
| `--color-canvas` | `#F5F7FA` (app background; cool near-white) |
| `--color-surface` | `#FFFFFF` (cards, panels) |
| `--color-surface-raised` | `#FFFFFF` + shadow-md |
| `--color-surface-sunken` | `#EEF2F6` (wells, code blocks light, table header) |
| `--color-surface-hover` | `#F3F7FB` |
| `--color-surface-selected` | `#E6F3FB` (Blue 1 at 10 %) |
| `--color-border` | `#E3E8EE` (hairlines) |
| `--color-border-strong` | `#D9D9D6` (dividers, decorative edges) |
| `--color-border-control` | light `#8A8F94`, dark `#6F8398`: edges of inputs, checkboxes, radios and outlined buttons; at least 3:1 against the surface (WCAG 1.4.11), checked by `npm run check:contrast` |
| `--color-text` | `#333333` |
| `--color-text-muted` | `#6E6E6E` |
| `--color-text-subtle` | `#696D72` light, `#8799AB` dark (the code's value, which passes 4.5:1; this page once listed a lighter value that did not) |
| `--color-text-inverse` | `#FFFFFF` |
| `--color-action` | `#0072B0` · hover `#0061A0` · pressed `#00527F` (the MetLife Blue 2 `#007ABC` is darkened so link text passes 4.5:1) |
| `--color-action-subtle` | `#E6F2F8` (secondary button fill, selected chip) |
| `--color-focus-ring` | `0 0 0 3px rgba(0,122,188,.35)` |
| `--color-success` | text `#4B7A1D` · fill `#A4CE4E` · bg `#F1F8E6` (text darkened from `#528320` for 4.5:1) |
| `--color-warning` | text `#7A5A00` · fill `#FFC600` · bg `#FFF8DB` |
| `--color-danger` | text `#B31B1D` · fill `#D42123` · bg `#FDECEC` |
| `--color-alert` | text `#B0084A` · fill `#DB0A5B` · bg `#FDE8F0` |
| `--color-info` | text `#0061A0` · fill `#0090DA` · bg `#E6F3FB` |
| `--color-neutral-chip` | text `#4A4A4A` · bg `#EEF0F2` (facts, "No diagnostic setting") |
| `--color-ai` | text `#5F259F` · bg `#F2ECF8` (AI-generated markers) |
| `--gradient-brand` | `linear-gradient(120deg, #0061A0 0%, #0090DA 55%, #A4CE4E 100%)` |
| `--gradient-brand-soft` | `linear-gradient(120deg, rgba(0,144,218,.10), rgba(164,206,78,.10))` (hero wash) |
| `--gradient-ai` | `linear-gradient(120deg, #0061A0 0%, #5F259F 100%)` (Ask Keigan card) |

**Dark theme** (on-call friendly; toggle in top bar; `system` default):

| Token | Value |
|---|---|
| `--color-canvas` | `#0A1420` |
| `--color-surface` | `#101D2B` |
| `--color-surface-sunken` | `#0C1824` |
| `--color-surface-hover` | `#152639` |
| `--color-surface-selected` | `#12304A` |
| `--color-border` | `#1E3044` · strong `#2A415A` |
| `--color-text` | `#E7EDF3` · muted `#A3B3C2` · subtle `#7D8FA1` |
| `--color-action` | `#3AA9E8` · hover `#62BCEF` |
| success text `#B6DA6E`, warning text `#FFD54D`, danger text `#FF6B6D`, alert text `#FF5C9A`, info text `#62BCEF`, ai text `#B48CE6` | |

**Priority and status mapping**

| Meaning | Chip style |
|---|---|
| P1 | danger (red) solid dot + label "P1" |
| P2 | alert (berry) |
| P3 | warning (yellow fill, dark text) |
| P4 | neutral |
| Healthy / met | success |
| At risk / burning | warning |
| Breached / failing | danger |
| Waiting | info with clock icon |
| Fact (neutral) | neutral chip |
| AI-generated | ai chip with sparkle icon "Keigan" |

Status is never colour alone: every chip has an icon or a text label.

**Charts** use MetLife extended data-viz order: `#0090DA, #333333, #00ACA0, #DB0A5B, #007ABC, #A4CE4E, #6E6E6E, #FFC600, #5F259F, #A7A8AA, #0061A0, #BADDF5, #528320, #D42123`.
SLO target lines: `#528320` dashed. Error budget: area fill `#0090DA` 15 %. Anomalies: `#DB0A5B` dots.

### 1.3 Typography

MetLife: **MetLife Circular** for headlines (proprietary), **Noto Sans** as primary UI font. Keigan uses:

| Role | Stack |
|---|---|
| Display / headings | `"MetLife Circular", "Figtree", "Noto Sans", system-ui, sans-serif` (Figtree from Google Fonts is the open Circular-like substitute; MetLife Circular is used automatically on machines that have it) |
| UI / body | `"Noto Sans", "Noto Sans JP", "Noto Sans SC", system-ui, -apple-system, "Segoe UI", sans-serif` |
| Japanese UI | `"Noto Sans JP"` first when `lang=ja` |
| Chinese UI | `"Noto Sans SC"` first when `lang=zh-CN` |
| Code | `"JetBrains Mono", "Cascadia Code", Consolas, monospace` |

Rules: never mix display and body fonts in one line; no all-caps headlines; no italics for display font; minimum body 14 px with 1.5 line height (MetLife).
Section eyebrows ("OPERATE" in the sidebar) may be small caps-style uppercase 11.5 px / 600 / +0.06em letter-spacing, muted.

**Type scale** (rem based on 16 px root; tokens `--text-*`):

| Token | Size / line-height | Weight | Font | Use |
|---|---|---|---|---|
| `display` | 40 / 48 | 700 | Display | Login hero, empty-state hero |
| `h1` | 30 / 38 | 700 | Display | Page title ("Incident room") |
| `h2` | 22 / 30 | 650 | Display | Section titles, investigation RCA cards |
| `h3` | 18 / 26 | 600 | Display | Card titles |
| `h4` | 16 / 24 | 600 | Body | Sub-section, table group headers |
| `body-lg` | 16 / 26 | 400 | Body | Prose: RCA text, chat messages, reports |
| `body` | 15 / 24 | 400 | Body | **Default UI text**, inputs, buttons |
| `body-sm` | 14 / 21 | 400 | Body | Table cells, helper text, metadata |
| `caption` | 13 / 18 | 500 | Body | Chips, timestamps, axis labels |
| `micro` | 12 / 16 | 600 | Body | Badges and counters only (never sentences) |
| `kpi` | 34 / 40 | 700 | Display, tabular nums | KPI tiles |
| `kpi-sm` | 24 / 30 | 700 | Display, tabular nums | Card metrics |
| `code` | 13.5 / 21 | 400 | Mono | Commands, queries |

Numbers in tables and KPIs use `font-variant-numeric: tabular-nums`. Weights: Noto Sans 400/500/600/700, Figtree 500/600/700.
Japanese text: line-height +0.1, letter-spacing 0.02em on body.

### 1.4 Mono, Keigan's own design (trial, 2026-11-24)

Keigan now has its own design, **Mono**, in light and dark; the original blue design stays selectable as **Classic**. Mono lives in `frontend/src/design/` (README there) and is selected with `data-design="mono"` on `<html>` (`hooks`: `design/useDesign.ts`, stored as `keigan.design`; chooser on the Design system page and in the top-bar brush menu, developer environments). It is a near-monochrome system: off-white and near-black surfaces, ink text, grey selected states, one green used only for buttons (with dark text) and small dots, no purple and no gradients (the AI marks are ink or white, the Ask Keigan panel is a dark card). Type is Inter at weights 400 and 500 only, body 16 px, tight tracking on large sizes, system monospace for code. Radii are 4 / 6 / 12 / 12 / 16 with 6 px buttons; cards are flat with a 1 px hairline and three shadow levels above that. Sizes: buttons 30 px, fields 42 px, cards padded 32 px, a 56 px top bar, buttons and fields at least 36 px on a phone. Links are ink with a persistent underline in body copy; the action colour is never used for text. Motion: buttons press in, and the new navigation rail animates (see below); reduced motion turns it off.

Navigation: `design/rail/MonoSidebar.tsx` replaces the original sidebar while Mono is on. It is a 56 px icon rail that opens over the page on hover or keyboard focus (a pin button keeps it open, `--layout-sidebar-width` / `--layout-sidebar-collapsed-width` set the two widths), group and item labels fade in, the active page is a pill that slides between items, and the footer shows the environment. `design/rail/NavIcons.tsx` has one two-tone icon per destination with its own hover animation. Same destinations, labels and access rules as `Sidebar`.

Components read size tokens with the original size as the fallback (`--button-h-md`, `--button-px-md`, `--button-text-md`, `--button-weight`, `--control-h-md`, `--card-padding-base`, `--chip-h-md`, `--radius-button` and their siblings), so they look as before whenever Mono is off.

Design lab (comparison only, removable): `frontend/src/design-lab/` applies seven other design systems from the `DESIGN.md` files in `Keigan/design/` (Stripe, Coinbase, MongoDB, VoltAgent, Spotify, Lovable, Starbucks), each in light and dark, through `data-lab`. Mono does not depend on it. Open items: review the pages other than Home, an investigation and Applications in Mono; the hover animations have not been watched in a browser; code blocks do not yet use the 16 px padding and 6 px radius; decide whether to keep Classic and then fold Mono into `tokens.css`.

## 2. Space, shape, depth

- **Spacing scale** (4 px base): 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, 64. Card padding 24 (20 on dense cards); page gutters 32 desktop, 20 tablet, 16 mobile; section gap 32; form label→control 8; between fields 20.
- **Radius:** `--radius-xs 6px` (chips, small inputs), `--radius-sm 8px` (buttons, inputs), `--radius-md 12px` (cards, popovers), `--radius-lg 16px` (panels, dialogs, drawers), `--radius-xl 24px` (hero cards), `--radius-full` (pills, avatars).
- **Shadows** (cool-tinted):
  - `--shadow-xs: 0 1px 2px rgba(16,32,48,.06)`
  - `--shadow-sm: 0 1px 3px rgba(16,32,48,.08), 0 1px 2px rgba(16,32,48,.04)`
  - `--shadow-md: 0 6px 16px -4px rgba(16,32,48,.10), 0 2px 4px rgba(16,32,48,.05)`
  - `--shadow-lg: 0 18px 40px -12px rgba(16,32,48,.18)`
  - Cards at rest: border + shadow-xs; hover (interactive cards): shadow-md + translateY(−1px).
- **Glass:** top bar `background: color-mix(in srgb, var(--color-surface) 78%, transparent); backdrop-filter: saturate(160%) blur(14px)`; bottom hairline.
- **Hairline accents:** the active sidebar item and the page hero use a 3 px brand-gradient stripe.

## 3. Layout

```
┌──────────┬──────────────────────────────────────────────────────────────────────┐
│ Sidebar  │ Top bar (64 px, sticky, glass): [≡] [App scope ▾]   [⌘K Search]  [文A] [☾] [🔔] [Avatar]
│ 264 px   ├──────────────────────────────────────────────────────────────────────┤
│ (72 px   │ Page header: breadcrumb · H1 · description · actions (right)         │
│ collapsed│ ─────────────────────────────────────────────────────────────────────│
│ )        │ Content (max width 1440 px, centered; tables may go full width)      │
│          │                                                                      │
└──────────┴──────────────────────────────────────────────────────────────────────┘
```

- **Sidebar:** white surface (dark theme: surface), right hairline. Header: logo + kanji. Section eyebrows. Items 40 px tall, 12 px radius, icon 18 px + label (body 15/500).
  Active: `--color-surface-selected` background, Dark Blue text, 3 px gradient bar on the left edge. Hover: surface-hover. Collapsed mode shows icons with tooltips.
  Bottom: environment badge (LOCAL / DEV / PROD), version, collapse button.
- **Breakpoints:** `sm 640`, `md 900`, `lg 1200`, `xl 1440`, `2xl 1680`. Below `md` the sidebar becomes an overlay drawer. Grids collapse to single column; tables scroll horizontally inside their card.
- **Page header:** breadcrumb (caption, muted) → H1 → one-line description (body, muted) → right-aligned actions (max one primary).
- **Grids:** 12 columns, 24 px gutters. KPI tiles 4 across at ≥ lg, 2 at md, 1 at sm.

## 4. Motion

| Pattern | Spec |
|---|---|
| Page enter | fade + translateY(6px→0), 220 ms, `cubic-bezier(.2,.8,.2,1)` |
| Card hover | 160 ms shadow + 1 px lift |
| Drawer / sheet | slide 24 px + fade, 240 ms; overlay fade 180 ms |
| Popover / tooltip | scale .98→1 + fade, 140 ms |
| KPI numbers | count-up 600 ms on first load only |
| Live investigation | 8 px dot pulsing (2 s) beside "Investigating"; stage chips fill with brand gradient as they complete |
| Skeletons | shimmer 1.4 s, low contrast |
| Chat | messages fade-up 180 ms; typing indicator three dots |

`prefers-reduced-motion: reduce` disables transforms and count-ups (opacity only, 1 ms). No parallax, no bouncing, no confetti.

## 5. Components (`frontend/src/components/ui`)

Every component supports: default, hover, focus-visible (2 px ring `--color-action` at 35 %), active, disabled, loading, empty, error. No validation error before the user interacted.

| Component | Spec |
|---|---|
| `Button` | Variants: `primary` (Blue 2 fill, white text, hover Dark Blue), `secondary` (white, border-control, text), `subtle` (action-subtle fill, Dark Blue text), `ghost`, `danger`, `gradient-outline` (secondary CTA with gradient stroke). Sizes: sm 32 px / md 40 px / lg 48 px; radius 8; body 15/600 (sm 14). Icon-left/right; loading spinner replaces icon. |
| `IconButton` | 36 / 40 px square, ghost by default, tooltip required, `aria-label` required. |
| `Card` | surface, border, radius 12, shadow-xs, padding 24; optional `CardHeader` (title h3 + description + actions), `CardFooter`. `interactive` prop for hover lift. |
| `StatTile` | icon tile (40 px rounded 10 with tinted bg), label (body-sm muted), value (kpi), delta/secondary line, sparkline optional, whole tile is a link. `size="compact"` (32 px icon, 12 px padding, `kpi-sm` value, caption label) is for tiles inside another card, such as a tool result. |
| `StatusChip` / `Badge` | height 24, radius full, caption 13/500, icon 14, tones: neutral, info, success, warning, danger, alert, ai, brand. `PriorityChip` for P1–P4. |
| `Tabs` | underline style: 2 px Blue 2 indicator that slides; tab text body 15/500; counts as micro badges. Also `SegmentedControl` (pill group) for small choices. |
| `Input`, `Textarea`, `Select`, `Combobox`, `TokenInput` | 40 px, radius 8, border-control, focus ring, label above (body-sm 14/600), helper below (caption muted), error text danger with icon. |
| `Switch`, `Checkbox`, `Radio` | Radix-based, Blue 2 when on. |
| `Dialog` | radius 16, max 560 (lg 760), shadow-lg, title h2, focus trap, Esc closes. |
| `Drawer` / `Sheet` | right side, 480 / 640 / 880 widths, header sticky, footer sticky with actions. Opened by `open` alone (no `trigger`), focus returns to the element that had it when the sheet opened; with a `trigger`, to the trigger. |
| `Popover`, `Tooltip` | radius 12 / 8, dark tooltip (`#1B2836`, white text 13 px). Opens on focus and click, not hover only. |
| `DataTable` | real `<table>`; header 40 px sunken, body rows 48 px (dense 40), body-sm, hairline row dividers, row hover, sticky header, first column sticky when scrolling, sortable headers, selection checkboxes, empty and loading states, pagination or virtualisation > 200 rows. |
| `EmptyState` | illustration (simple line icon in gradient circle), title h3, one sentence, primary action. |
| `Skeleton` | rounded blocks with shimmer. |
| `CommandBlock` | dark code surface `#0F1B27`, mono 13.5, tabs (CLI / PowerShell / Terraform / Portal), copy button with "Copied" state, risk label pill (Low / Medium / High risk), horizontal scroll. |
| `MarkdownView` | safe markdown (GFM tables, code with copy), no raw HTML, headings scaled down one level, links open in new tab with `rel=noopener`. |
| `EvidenceChip` | `E3` mono pill; hover shows evidence title; click scrolls to evidence. |
| `ConfidenceMeter` | 5-segment bar + percentage + label (Low / Moderate / High / Very high). |
| `Sparkline` | 96×28 SVG, Blue 1 line, target dashed. |
| `TimeSeriesChart`, `BarChart`, `DonutChart`, `FunnelChart`, `BurnDownChart`, `HeatmapGrid` | Recharts wrappers with tokens, accessible table toggle ("View as table"). |
| `TopologyGraph` | React Flow; node cards (icon by type, name, status ring), animated dashed edges for impacted paths, mini-map, fit view, legend. |
| `Timeline` | vertical, 2 px rail, colored dot per event type, time column 88 px tabular. |
| `FileDrop` | dashed 2 px border radius 12, drag-over Blue 2 tint, accepted types listed, per-file progress rows. |
| `Stepper` | onboarding: stages with steps and sub-steps, status icons (hollow circle, half, clock, triangle, tick), `aria-current="step"`. |
| `ReadinessBar` | progress (gradient) + "6 of 8 required done · Next: …" + "See all". |
| `SaveIndicator` | "Saving…", "Saved 10:42 ✓", "Couldn't save — Retry". |
| `CountWithInfo` | number + ⓘ popover listing top items + "View all" → drawer. |
| `Avatar` | initials on brand-soft background; 24/32/40. |
| `Toast` | bottom-right, radius 12, icon + message + action, 5 s, pause on hover. |
| `ChatPanel` | floating launcher (56 px circle, gradient-ai, sparkle icon) → panel 420 px (expand to 50 vw), header with context chip, message list, suggested prompts chips, composer with Enter to send / Shift+Enter newline. |
| `ChartMessage` | renders AI chart specification with Recharts + "How I got this" disclosure. |
| `LanguageSwitcher`, `ThemeToggle`, `ApplicationScopeSwitcher`, `CommandPalette` | top bar controls. |

### 5.1 Rules added in the UI/UX pass (2026-11-21)

- **Tables on a phone.** Below 640 px every `DataTable` row becomes a stacked card: the first column is the title, the other columns show their header as a label. No column is hidden behind a sideways scroll. `mobileLayout="scroll"` keeps the wide grid for matrices. The scrolling area is a focusable region named by the table caption and carries `aria-busy` while loading.
- **Banners.** Only an error (`danger`) is announced as an alert; warnings and notices are polite status messages. A neutral notice uses the info icon, not the plain circle (it reads as an unchecked radio button).
- **Dialogs.** The open animation only nudges the dialog; it must not translate by -50%, because the overlay's grid already centres it.
- **Phone navigation** is a modal: focus moves into it, the page behind is `inert`, focus returns to the menu button.
- **Commands** wrap by default: a command must be readable before it is copied.
- **Japanese** breaks at phrase boundaries (`word-break: auto-phrase`, `line-break: strict`); Enter that confirms an IME conversion never sends a message.
- **Form errors** are `role="alert"` so a late error is announced.

## 6. Page layouts

### 6.1 Sign-in (local mode)
Split screen: left 44 % brand panel (`--gradient-brand` with soft radial highlights, large mark, "慧眼 Keigan", tagline in white h2); right: card "Choose a test user" listing dummy users as selectable rows (avatar, name, role chip, groups in caption) + "Sign in" primary. Banner "Local mode — not for production". Entra mode: same left panel, right "Sign in with Microsoft" button.

### 6.2 Home
1. Hero strip (no card): greeting `h1` ("Good afternoon, Aiko") + status sentence (body-lg muted), right: synced indicator. Behind: `--gradient-brand-soft` wash fading to canvas, 160 px tall.
2. KPI row: 4 `StatTile`s.
3. Two-column (8/4): left "Application health" grid (cards 2–3 per row) and "Live incidents"; right "Ask Keigan" (gradient-ai card, white text h3 + input + "Ask"), "Intelligence feed", "Maintenance windows".

### 6.3 Incident room
Header with view toggle (Table / Board) and "New investigation". Filter bar (chips + selects) sticky under the top bar. Table with priority chip column first. Board: 5 columns (New, Investigating, Identified, Monitoring, Resolved) with cards (priority, number, title, app, confidence, elapsed).

### 6.4 Investigation
- Header card (radius 16): row 1 breadcrumb; row 2 priority chip + INC number (mono) + title (h1 at 26 px); row 3 chips (status, app, services, source) + timers; right: action buttons (primary: "Resolve and write postmortem").
- While running: `InvestigationProgress` — six stage pills connected by a line that fills with gradient; current stage pulsing; caption with what Keigan is doing ("Querying Log Analytics for claims-api…").
- Sticky section tabs: RCA · Hypotheses · Evidence · Blast radius · Timeline · Alerts · Communications · Postmortem.
- RCA: 3 cards in a row (lg), each with icon tile (What: alert-triangle red tint; Why: search/branch purple tint; How: wrench green tint), h3, markdown body-lg, evidence chips. Above them: executive summary (body-lg) + `ConfidenceMeter` + AI chip "Generated by Keigan · model · 2 min ago" + feedback (👍 correct / partly / wrong).
- Hypotheses: 3 equal columns; column header with perspective icon (Application: code-2 purple; Dependencies: network blue; Infrastructure: server teal), confidence ring, title (h3), statement, evidence chips (supporting green outline, contradicting grey strike), "Fix" sub-card with ordered steps and `CommandBlock`s, code change diff (before red-tinted / after green-tinted mono), runbook badge, risk chip. Leading column has gradient top border 3 px and "Most likely" ribbon.
- Evidence: list of `EvidenceCard`s grouped by service with source icon, code `E4`, title, signal strength chip, matched count vs baseline ("312 vs 4 baseline ×78"), patterns table (template mono, count, badges NEW / ×12), samples collapsible, query in `CommandBlock` (language tab label), deep link.
- Blast radius: left 2/3 `TopologyGraph` (impacted nodes red/berry ring, path edges animated), right 1/3 lists (impacted services, SLOs with budget burned, stakeholders notified, downstream apps) + narrative.
- Timeline: `Timeline` component with filter chips by source.
- Communications: language tabs, cards per draft with status chip, edit (markdown textarea with preview), approve, send.
- Postmortem: document view (max 860 px, prose typography), actions bar (Edit, Finalise, Send, Download .md, Print).
- Chat: floating `ChatPanel`.

### 6.5 Alerts
Funnel chart card on top (5 stages with counts and percentages), then alert groups table (title, services, alerts count, severity, state chip, score bar, decision reason, feedback). Group drawer: member alerts table, decision log (`Timeline` style), linked investigation.

**Why these alerts were grouped (2026-11-21).** Under each group title in the table, and as the first line of the drawer, one muted sentence says why the alerts belong together, for example "Grouped because 3 alerts fired on claims-sql within 10 minutes of each other." It is hidden in the table for a group of one alert (the `single_alert` code). The server sends a code and parameters (`groupingReason`); `GroupingReasonText.tsx` builds the sentence from the `groupingReason.<code>` strings of the `alerts` namespace, and an unknown code reads as "The reason these alerts were grouped was not recorded." See `features/alert-grouping-reason/26_ALERT_GROUPING_REASON.md`.

### 6.6 SLO monitoring
Application selector (or scope), headline SLO hero card (big compliance number kpi, target, budget remaining donut, burn rate chips), grid of SLO cards (name, service, compliance vs target, budget bar with minutes left, 1h/6h burn chips, sparkline, status). Detail drawer: SLI over time with target line, burn-down, recent incidents. Admin ecosystem heatmap (apps × days, cell colour by compliance).

### 6.7 Intelligence
Health score trend per application (line), signals feed (cards with detector icon, severity chip, title, explanation, mini chart, actions Acknowledge / Dismiss / Create investigation), report archive list (title, period, health score, sent).

### 6.8 Keigan AI chat
Two panes from 1200 px: left conversation list (280 px; search; rename and delete in each row's menu), right conversation: header with the title and scope chips (applications), then `AskKeiganConversation` (the Ask Keigan trace below): user right-aligned soft blue bubble; Keigan left with avatar mark, no bubble, its steps (tool cards, live) and the answer with citations; the number and the chart of a log query inside its card; composer docked bottom (multi-line, max 6 lines, Send or Stop). New page button "New chat" in the page header. Empty state: big mark, "What would you like to know?", 6 suggested prompts as cards (the server's six when one application is in scope, otherwise six translated generic ones). **Phone (below 1200 px):** the list is a `Drawer` (sm) opened by a **Conversations** button in the page header beside **New chat** (both 44 px high); the composer's Send and Stop are 44 px icon buttons (the word stays in the accessible name); the empty state starts at its top. A conversation exists only once its first question is asked (`POST /chat/conversations` then the answer; the address changes to it while the answer streams). Messages stored before Ask Keigan (no run) keep their chart, number and "How I got this" through `ChatMessageView`.

### 6.9 Applications
Grid of application cards (name h3, code mono chip, region flag emoji-free (text code), lifecycle chip, component-type icon row, services count, SLO compliance ring, open incidents) + table toggle. Application workspace: header + readiness bar; left 280 px stepper; content panel (form steps max 760 px; table steps full width); sticky action bar at bottom of panel with Back · SaveIndicator · primary.

**Operating notes editor (2026-11-21).** The first section of the Knowledge step (`OperatingNotesSection.tsx`): heading "Operating notes for the AI", a one-line description, a text box with helper text (what to write; guidance, not evidence; no passwords or personal data), a live counter "used of maximum characters" that turns red with an "N characters over the limit" message when too long (Save is then disabled), "Last edited by ... " with a relative time, and Save notes / Discard changes buttons shown only for people who may edit. Readers see the text read-only with a note that only the application's admins can edit it. Moving to another step, closing the tab or reloading with unsaved text asks for confirmation ("Leave without saving?"). See `features/application-operating-notes/25_APPLICATION_OPERATING_NOTES.md`.

### 6.10 Administration
Settings: sectioned cards with key/value rows (effective value, source env var name in caption), "Test connection" buttons. Usage: KPI tiles + stacked bar (tokens by feature per day) + table by application. Audit: filterable table. Outbox: table + preview drawer rendering the email HTML in a sandboxed iframe.

### 6.11 Reliability metrics
Route `/metrics`, sidebar item "Reliability metrics" in the Reliability section, after SLO monitoring and Intelligence (icon `ChartColumn`). Top bar: application selector (all applications or one) and period selector (7, 30 or 90 days), then the date range and a one-line note on how median and p90 are calculated. Sections in order: Incidents (opened and resolved by priority; tiles for time to detect, time to first update and time to resolve; a "Not available" tile for time to acknowledge with its reason), Keigan investigations (counts by status; ratings, with "not enough ratings yet" below the minimum sample), AI usage (tokens per investigation, latency per call, failed calls, estimated cost or a message that no prices are configured, plus the models left out of the estimate), Weekly trend (four bar charts), By application (sortable table) and "How these figures are defined". Every figure shows its sample size as "n = ..."; a figure with no samples reads "No data in this period", never zero. A duration that could not be computed for some items says how many were left out and why. Text is in the `metrics` namespace. See `features/reliability-metrics/24_RELIABILITY_METRICS.md`.

## 7. Content and voice

- Friendly first person in onboarding titles only ("Here's where I'm looking"); everywhere else plain, SRE vocabulary: service, SLO, runbook, assignment group, burn rate.
- Buttons: verb + object ("Add component", "Run investigation"). Never "Submit", "OK".
- Empty states explain the next action in one sentence.
- AI content is always labelled with the Keigan AI chip and a timestamp, and shows evidence citations.
- Dates: relative for < 24 h ("12 min ago"), absolute otherwise in the user's locale and time zone; tooltips show ISO with zone.
- Plurals via i18next plural rules; never "1 checks".

## 8. Accessibility

WCAG 2.1 AA. Focus visible everywhere; skip-to-content link; landmarks (`nav`, `main`, `aside`); tables with headers; dialogs trap focus and restore it; live region announces finished async work;
charts have "View as table"; colour never the only signal; target sizes ≥ 32 px (44 px on touch); text resizes to 200 % without loss.

## 9. Implementation notes

- Tokens live in `frontend/src/styles/tokens.css` as CSS variables for both themes (`:root` and `[data-theme="dark"]`), mapped into Tailwind v4 via `@theme inline` so utilities like `bg-surface`, `text-muted`, `border-hairline`, `text-action` exist.
- Fonts: Google Fonts `Noto Sans` (400–700), `Figtree` (500–700), `JetBrains Mono` (400–500) preloaded; `Noto Sans JP` / `Noto Sans SC` loaded on locale switch.
- `cn()` helper (`clsx` + `tailwind-merge`). Component variants with small typed maps (no CSS-in-JS runtime).
- Icons: `lucide-react` at 16/18/20 px, stroke 1.75.

## 10. Frontend foundation guide

Import with the `@/` alias (= `frontend/src`). Dev: `npm run dev` (port 5173; `VITE_API_PROXY_TARGET=http://localhost:800X` points `/api` at another backend). Check: `npm run build`.

**UI kit** (`@/components/ui/<Name>`): `Button` (variant primary|secondary|subtle|ghost|danger|gradient-outline, size, leadingIcon, trailingIcon, isLoading, asChild) · `IconButton` (icon, label required) · `Card/CardHeader/CardBody/CardFooter` (interactive, dense, accent) · `StatTile` (icon, label, value, secondaryText, trend, to, size default|compact) · `StatusChip`/`Badge` (tone) · `PriorityChip` · `AiGeneratedChip` · `EvidenceChip` (code, title, relation) · `Tabs/TabsList/TabsTrigger(count)/TabsContent` · `SegmentedControl` · `Input/Textarea/Select/Combobox/TokenInput/RadioGroup/Checkbox/Switch` (label, helperText, errorMessage) · `Dialog`, `ConfirmDialog`, `Drawer` (size sm|md|lg), `Popover`, `Tooltip`, `DropdownMenu` (typed `entries`) · `DataTable` (columns, rows, getRowId, caption, sort, selection, serverPagination) · `EmptyState`, `ErrorState` (error, onRetry), `Skeleton`, `Spinner`, `Banner`, `Toast` (`useToast().showToast`) · `CommandBlock`, `MarkdownView`, `ConfidenceMeter`, `Timeline`, `Stepper`, `ReadinessBar`, `SaveIndicator`, `FileDrop`, `CountWithInfo`, `KeyValueList`, `SectionHeader`, `ProgressBar`, `Avatar`, `Kbd`, `RelativeTime`, `CopyButton`. Live examples: `/design-system` (local/dev only).

**Charts** (`@/components/charts`): `Sparkline`, `TimeSeriesChart` (data, series, xKey, targetValue, anomalies), `BarChart` (stacked, isHorizontal), `DonutChart` (slices, centerValue), `FunnelChart` (stages), `HeatmapGrid` (rows, columns, getValue). All take `ariaLabel` and include "View as table". Colours: `chartColorForIndex`, `chartToneColors`. **Topology**: `@/components/topology/TopologyGraph` (nodes `{key,name,type}`, edges `{source,target}`, `highlightedNodeKeys` `{key: "direct"|"indirect"}`, `onNodeSelect`).

**Layout** (`@/components/layout`): `PageHeader` (title, description, breadcrumbs, actions) at the top of every page; `KeiganLogo`; the shell (`AppShell`, `Sidebar`, `TopBar`, `CommandPalette`) is already wired in `app/routes.tsx`.

**Routes**: create `features/<area>/pages/<Name>Page.tsx` (default export) and add `{ path, ...lazyPage(() => import(...)) }` in `app/routes.tsx` (admin pages go inside the `RequireKeiganAdmin` group). Stub pages already exist at the documented paths; replace the file content.

**i18n**: `const { t } = useTranslation("<namespace>")`. Namespaces are the JSON files in `i18n/locales/<locale>/`; to add one, create `en/<ns>.json` (plus other locales as needed; missing keys fall back to English) and add the name to `translationNamespaces` in `i18n/index.ts`. Plurals: `key_one` / `key_other`.

**API client** (`@/api/httpClient`): `apiGet<T>(path, { query })`, `apiPost<T, Body>(path, body)`, `apiPut`, `apiPatch`, `apiDelete`, `apiUpload(path, formData, { onUploadProgress })`; paths are relative to `/api`; arrays in `query` are comma-joined; errors are `ApiError` (`status`, `title`, `detail`, `fieldErrorFor(field)`, `correlationId`). Use TanStack Query (`useQuery`, `useMutation`) with a per-feature `queryKeys` object; shared types in `@/api/types/common` (`PagedResult`, `Priority`, `Identifier`).

**Auth and access** (`@/auth`): `useAuth()` (status, user, signOut), `useCurrentUser()`, `useAccessControl()` (`isKeiganAdmin`, `canRead(applicationId)`, `canEdit(applicationId)`, `highestRole`), `useApplicationScope()` (`applicationIds` to send as `applicationIds=` query param, `availableApplications`). Hide controls the user cannot use; the backend enforces access.

**Formatting** (`@/utils/formatters`): `formatDateTime`, `formatRelativeTime`, `formatDuration`, `formatNumber`, `formatPercentage`, `formatTokens`. Theme: `useTheme()`; runtime config: `useRuntimeConfiguration()`, `useFeatureFlag(name)`.

### Chat components (`@/components/chat`, owned by S5)

- `ChatMessageView` — `{ role: "user" | "assistant", text, payload?: ChatMessagePayload, isCompact?, className? }`. User turns are right-aligned soft-blue bubbles; assistant turns show the Keigan mark with a left rule (omitted when `isCompact`, used in the floating investigation panel), Markdown prose, an optional `ChartMessage`, citation chips (`EvidenceChip`) and a "How I got this" disclosure with the query in a `CommandBlock`. It now draws only messages written before Ask Keigan (they have no run) and the user's questions; the clarification chips of the old router are gone (such a message shows its text).
- `ChartMessage` — `{ specification: ChartSpecification }` (doc 05 §7); renders line/area, bar/stacked_bar, pie or table inside a bordered figure with the shared "view as table" toggle.
- `ChatComposer` — `{ onSend(text), isSending?, onStop?, isDisabled?, placeholder? }`; Enter sends, Shift+Enter adds a line (max 6 lines). With `isSending` and `onStop` the Send button becomes **Stop** and Esc in the field stops the answer. Below 640 px the button is a 44 px square with the icon alone; its word stays in the accessible name.
- Types (`ChatMessagePayload`, `ChartSpecification`) live in `@/api/chatApi`. Strings come from the `chat` i18n namespace.

#### Ask Keigan trace (spec `features/ask-keigan-chat/23_ASK_KEIGAN_CHAT_SPEC.md`; types and calls in `@/api/askKeiganApi`)

| Component | Spec |
|---|---|
| `AskKeiganConversation` | `{ conversationId, isCompact?, introText?, suggestedPrompts?, renderEmptyState?, initialQuestion?, composerPlaceholder?, onSelectEvidence?, onSelectRunbook? }`; `conversationId` is `null` for a new chat together with `startConversation()`, which creates the conversation when the first question is asked and returns its id (the page then moves the address to it and keeps this component, so the answer on screen is not lost). `renderEmptyState(ask)` replaces the intro and prompt buttons (the chat page's larger empty state); `initialQuestion` is asked once when the conversation is shown (the question typed on Home; a timer cleared with the effect, so React's development double mount asks it once). The one conversation component: stored history, the answers asked this session, a bar with the **Show tool details** switch, composer with Stop, error banner, hidden live announcer. Fills its container; the caller provides frame and header. Transcript is `role="log" aria-live="off"` (streamed text is never read token by token); auto-follows only within 80 px of the bottom, otherwise a "New activity" pill (the scroll events of its own smooth scroll do not count as the person leaving the bottom, and a finished tool call, which grows its card, counts as activity; `transcriptActivityKey`). Turn views are memoised (`areConversationTurnsEqual`, stable callbacks) so a stream event redraws only its own turn: earlier answers are not re-parsed and a focused chip keeps focus. A failure with an action (lost connection: **Check again**; another answer running, or a Stop that did not get through: **Stop**) shows it in the banner. Esc anywhere in it stops the answer that is running (and, being handled, does not also close a panel around it). |
| `AssistantRun` / `StoredAssistantRun` | Keigan's side of one question: trace, then answer. The same component draws a streaming run and a stored snapshot (`useAnswerRun`, polls while running). `aria-busy` until the run ends. A stored run the server will not show is a calm caption, not an error: 403 `trace.redacted` (also what an answer hidden after the person lost access shows: the server sends one sentence and the run link, and the run is refused), 404 or 410 `trace.expired`; such a run is asked for once, not again on window focus (`useAnswerRun`, `runUnavailableReason`); a stored failure is a polite status (the alert is only for a run that failed while the screen was open, so reopening a conversation does not announce old failures again). |
| `AnswerRunTrace` | `{ progress, toolProgress?, isCompact?, focusRequest? }`. Collapsible "Keigan's steps · N tools · time" header with a Show / Hide word (pulsing dot and "N of up to M tools" while running; warning icon when collapsed with failed steps), tool cards, notes in muted caption lines. **Show tool details** (`useToolDetailsPreference`) decides whether the section starts open or folded to its header and decides it again whenever the switch is flipped; the header toggles it in between. The reason the answer stopped is shown even when folded, and also alone for a run that stopped before any step ("Stopped by you"); when every call was redacted one caption (`trace.redacted`) replaces the steps. A succeeded call that is the only step of a finished run opens by default while tool details are on (spec 8.3). `focusRequest` (from a `[T#]` citation) opens the section and moves focus to the card header; in a compact container (details in a drawer) it does not open the card. |
| `ToolCallCard` | One tool call. Header button (accessible name `chat:tool.accessibleName`: "label, target, state, duration of a finished call, citation T2"; the running timer is left out because it changes every second and is `aria-hidden` on screen; `aria-describedby` points at the summary and the flags row, so a screen reader hears the summary, "Contains instruction-like text", the masked count, "Simulated data" and "Showing x of y"; `aria-controls` is set only while the body is rendered): state icon, label, target `Badge`, citation chip, duration, code-written summary, flags. The flags come from the server's own fields (`isSimulated`, `totalCount`, `isTruncated`, with `itemCount`), computed from the whole output, not from the preview (which the server cuts for large outputs). A running `query_logs` call shows its `query_generated` stage as the summary line. States: running (spinner, live elapsed), done, failed, refused, skipped, cancelled, redacted; each has an icon and a word. `detailsPlacement="card"` (default): the header is a disclosure (`aria-expanded`) and failed and refused cards open by default. `detailsPlacement="drawer"` (the investigation panel, spec 8.2): the card stays a summary, the header opens `ToolDetailsDrawer` (`aria-haspopup="dialog"`, chevron right). |
| `ToolCardBody` / `ToolDetailsDrawer` | What a card shows once opened: inputs as `KeyValueList` (bound arguments with a lock) or JSON, the result by presentation (`ToolOutputView`), and the actions: **Open in Keigan** (`ToolRecordLink`), View full output, Copy output. A preview the server cut at its limit arrives as text, so the body reads the stored output instead. `ToolDetailsDrawer` is the same body in a `Drawer` (md) with the target and citation chips. |
| `ToolOutputView` | `{ presentation, output }`. Renders by presentation: `record_list`, `record`, `passages` (titled excerpts, Markdown through `MarkdownView`, a match badge when the tool scores them), `query_result` (`QueryResultOutput`: the query in a `CommandBlock`, the number `total` as a compact `StatTile`, the pattern `series` as a chart, sample rows in `DataTable`), `series` (`SeriesOutput`: one chart per unit of number, percentages, values and counts, never two units on one axis; the list is the one named `series`, else the first list of records with an x field and a numeric field; a line over moments or days, bars for names; each chart is the shared `TimeSeriesChart` or `BarChart` with legend and "View as table", and under it the same numbers in words: count, span, lowest, highest, latest, so the chart is never the only way to read them; the output's other fields follow as a field list), `metrics` (`MetricsOutput`: one block per entry with a status chip and compact `StatTile`s, shares as percentages, tiles are not links), `graph` (`GraphOutput`: version and review line, the written understanding, uncertainties, then components and connections as lists, "n of m" when cut). Unexpected shapes fall back to a field list, so a new tool needs no change. Field names are translated through `chat:fields.<name>` and status, kind, category and event tokens through `chat:values.<token>` (a name or token no locale knows is humanised, for a tool added later); lists and metadata lines are joined with `Intl.ListFormat` (`formatList`) and `chat:tool.fieldPair` / `tool.timeRange`, never with a separator written in code. Values are always text, never HTML. |
| `ToolOutputDrawer` | `Drawer` (lg) with the result by presentation, the full stored JSON (copy, download `.json`) and, under "What Keigan's AI saw", the exact model view with its SHA-256. Loads when opened. |
| `AnswerMessage` | Failure `Banner` (danger, with reference id and "Try again" only when the server says retryable), "unverified" warning `Banner`, answer through `MarkdownView` with `renderCitation` (`[T#]` chips that open the trace, `[E#]` chips that select evidence), sources row, follow-up chips. Citations: `[T#]` focuses the card, `[E#]` selects the evidence on the investigation page, `[R#]` shows the matched runbook (RCA tab, the runbook is scrolled to and outlined); a chip without an action is plain. **Copy answer with sources** (`buildAnswerWithSources`, plain text): the answer as written, a Sources list `[T1] label — target — Inputs: … — summary` (evidence and runbooks by title) and "Asked in Keigan on <date>"; the confirmation is the `CopyButton` live region ("Copied"). |
| `LiveAnnouncer` | Hidden `role="status"` polite region, one per conversation; at most one announcement per 2 s, a newer one replaces one still waiting. |
| `useAnswerStream` | Hook over the pure `answerStreamReducer` (`@/components/chat/answerStreamReducer`) and the pure SSE parser `parseServerSentEvents` (`@/api/serverSentEvents`). Streams over a POST (`apiStream`). Stop cancels the run on the server (it waits for the first frame, which names the run, when pressed earlier) and follows it to its real end; a failed Stop says so in its own words, not "your question was not sent". A dropped connection is recovered by polling the snapshot (1 s, 3 s after 20 polls) through the pure `decidePollFailure` / `pollAnswerRun` (`answerRunPolling.ts`): a 5xx, a 429 and no connection are retried; a 403 or 404 hands the run to the stored conversation; after 20 failures in a row the poll gives up with `answer_connection_lost` and a **Check again** action, and the composer leaves Stop. A 409 `answer_in_progress` keeps the other run's id, so it can be stopped. The browser never shows a JavaScript error message (`failureFromError`). |
| Tests | `npm test` (vitest, Node, no DOM) covers the pure logic: SSE parser and event decoding, `answerStreamReducer`, the polling decision, `conversationTurns`, `toolSeriesModels`, `readHomeQuestion`, `citationCodes`, `answerCopyText`, `toolRecordLinks`, `nextFocusTrapTarget`, failure wording and card state. The browser flows are `scripts/check-ask-keigan.mjs` (it reports passed, FAILED and SKIPPED). |
| `useToolDetailsPreference` / `ToolDetailsSwitch` | The **Show tool details** preference: on by default (D1), kept in `localStorage` key `keigan.chat.showToolDetails` inside try/catch (Keigan has no server-side preference for it; theme and language are the only ones that live on the profile), shared by every conversation through `useSyncExternalStore`. `ToolDetailsSwitch` is a `Switch` (sm) bound to it. |
| `useFocusTrap` (`@/hooks`) | Keeps Tab and Shift+Tab inside a container while active (pure `nextFocusTrapTarget` decides the target). Used by the investigation panel on a phone, where the panel is a modal `role="dialog" aria-modal` sheet; on a desktop it is a complementary region. |

`MarkdownView` gains an optional `renderCitation(code)`; without it text renders as before. Uses existing tokens only (no new colour pairs; `npm run check:contrast` unchanged). Motion: cards fade up 180 ms, the status icon fades in 180 ms, the expand chevron turns 150 ms; reduced motion follows the global rule. **Investigation panel keyboard (decision):** opening moves focus into the panel and closing returns it to the "Ask Keigan" launcher; **Esc stops the answer while one runs and otherwise closes the panel** (a layer that handles Esc first, such as an open sheet or tooltip, consumes it, so the next Esc closes the next layer); choosing an `[E#]` or `[R#]` citation on a phone also closes the sheet so the page it points to is seen.
