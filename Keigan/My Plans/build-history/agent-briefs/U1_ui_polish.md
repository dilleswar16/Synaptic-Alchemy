# U1 — UI polish sweep (layout, spacing, overflow, typography)

Read `00_COMMON_RULES.md` (token discipline, running servers) and `04_UI_UX_DESIGN_SYSTEM.md` §1.3 (type scale), §2 (space, shape, depth), §5 (components) and §10 (frontend foundation guide).
The owner's verdict: *"Overall UI theme is very good, just need to make the positioning and fonts a bit more lit. Text spills outside boxes in places, e.g. the Applications page."*
Goal: every screen looks deliberate and premium — crisp hierarchy, consistent rhythm, nothing touching or spilling over an edge — **without changing the theme, colours, data or behaviour**.

## Environment (already running — don't restart unless they're down)
- Backend `http://127.0.0.1:8010` (integration database, all demo data), frontend dev server `http://localhost:5180` (hot reload picks up your edits).
- If down: backend — from `backend/`: `$env:DATABASE_URL="sqlite+aiosqlite:///./data/keigan_integration.db"; .\.venv\Scripts\python.exe -m uvicorn keigan.main:app --port 8010`; frontend — from `frontend/`: `$env:VITE_API_PROXY_TARGET="http://localhost:8010"; npx vite --port 5180 --strictPort` (run both in the background).
- Screenshots (Git Bash, from `frontend/`): `MSYS_NO_PATHCONV=1 node scripts/capture-screens.mjs --web http://localhost:5180 --api http://127.0.0.1:8010 --out <scratch folder> --theme light|dark --width 1440|1280|390 --wait 3000 [--only /applications,/slo]`. It prints errors per screen and saves full-page PNGs you can open with the Read tool. Keep `MSYS_NO_PATHCONV=1`, otherwise `/` arguments break.

## Known issues to fix first
1. **Card padding.** The kit's `Card` has no padding of its own (padding comes from `CardHeader` / `CardBody`, or `p-[var(--card-padding)]`). Find every `<Card …>` whose content is not inside `CardHeader`/`CardBody` and fix it (Applications grid cards are the visible example). Grep: `<Card` in `src/features/**`.
2. **Applications page cards:** padding; long names wrap to two lines (`line-clamp-2`) with a `title` tooltip instead of an ellipsis that hides the word "Mainframe"; component-type icons get a visible label or tooltip ("Azure · Hardware"); the "SLO" figure must say what it is ("SLOs met") so 100 % is not ambiguous; give the card a clear top (name + lifecycle), middle (code · region · component types) and bottom (three stats) with consistent alignment; subtle hover lift for the clickable card.
3. **Investigation header:** title should not be squeezed by the action buttons at 1280 px.

## Sweep checklist (every screen, light and dark, at 1440, 1280 and a quick 390 check)
- Nothing touches a card border; nothing overflows its container; long identifiers (resource IDs, service names, emails, URLs) use `break-words`/`truncate` + `title`; tables scroll inside their card, never the page.
- Type hierarchy per §1.3: page title `text-h1` display font; section titles `text-h2`/`h3`; card titles `text-h3` semibold; metadata `text-body-sm`/`text-caption` muted; numbers `tabular-nums`. Never smaller than 12 px; body text 15 px.
- Rhythm on the 4/8 px scale: card padding 24 (20 dense), gaps between cards 16–24, section gaps 32; consistent across pages. Align baselines of labels and values in stat rows.
- Icons 16/18/20 px, vertically centred with their labels; chips 24 px tall; buttons in a row share height.
- Empty and loading states centred and calm; no giant blank areas inside equal-height cards (use `items-start` where columns differ a lot in height).
- "More lit": use the display font for card and section titles, slightly stronger title weight, softer muted text, consistent radius (cards 12, panels 16), `shadow-xs` at rest and `shadow-md` lift on hover for interactive cards, the 3 px brand-gradient accent only where the spec says (active nav, hero, leading items). Keep it restrained — corporate, not flashy.

## Rules
- Presentation only: CSS classes, layout JSX, small presentational components. No API, data, routing or state changes.
- You may edit any frontend file under `src/` (feature folders and the UI kit) — fix systemic problems once in the kit when that is cleaner, and check it doesn't break other screens. Don't edit locale files other than `en/*.json` (a translation agent is filling the other languages right now); new visible strings go into the right `en` namespace.
- Run `npm run build` at the end (zero TypeScript errors) and a final full screenshot pass with no errors.
- Final report (≤ 20 lines): what you changed per screen, systemic kit changes, and any issue you saw but left (with reason).
