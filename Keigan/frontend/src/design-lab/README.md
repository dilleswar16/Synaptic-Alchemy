# Design lab

Seven real design systems (Stripe, Coinbase, MongoDB, VoltAgent, Spotify, Lovable, Starbucks), each in light and dark, built from
the `DESIGN.md` files in `Keigan/design/<company>/`. A comparison tool only: Keigan's own design is Mono (`src/design/`), which does
not depend on anything in this folder. With the lab off nothing here has any effect.

## Using it

- Design system page (`/design-system`, developer environments): the "Design lab" section has a tile per company with a Light and a
  Dark preview. Click one and the whole app switches.
- Top bar, in developer environments: the brush button picks Keigan's design (Mono or Classic), the company and Light / Dark.
- The choice is kept in `localStorage` (`keigan.lab`); light / dark is the app's normal theme.

## How it maps a DESIGN.md to the app

Every page takes its colours, fonts, corners and shadows from semantic tokens (`styles/tokens.css`), so a company file only sets
those tokens when `data-lab="<id>"` is on `<html>`:

| From the file | Becomes |
|---|---|
| Colours (canvas, surfaces, ink, primary, hairlines) | `--color-canvas`, `--color-surface*`, `--color-text*`, `--color-action*`, `--color-brand-*`, `--color-border*` |
| Typography (size, weight, line height, letter spacing) | `--text-display`, `--text-h1` to `--text-h3`, `--text-body*`, `--text-caption`, `--text-micro`, `--text-kpi*`, and per-level weight and tracking (`--lab-*`) |
| Rounded scale and the button shape | `--radius-xs` to `--radius-xl`, and `--radius-button` |
| Shadows and elevation | `--shadow-xs` to `--shadow-lg` |
| Font family | `--font-family-display`, `--font-family-body`, `--font-family-mono` (closest free font where the company's own is licensed) |

Values a file does not give are derived and are the author's choice, not the company's: the other colour mode when the file is
written for one, hover and pressed shades, chart accents, shadow levels the file does not name, and control borders (darkened to
meet 3:1 where the file's input border is lighter). The status colours and the purple AI tone stay the app's own unless the file
defines them.

Component sizes (button, input, card, chip) are matched for Stripe only, through size tokens (`--button-h-md`, `--button-px-md`,
`--button-text-md`, `--button-weight`, `--control-h-md`, `--card-padding-base`, `--chip-h-md` and their siblings). `Button`, `Card`,
`FormField`, `StatusChip` and `Textarea` read them with the app's old size as the fallback; Mono uses the same hooks.

Known limits: green or light-blue action colours (MongoDB, Spotify, VoltAgent) are fine for buttons but fail contrast when the app
uses the action colour for link text. Spotify's uppercase tracked button labels are not applied. Licensed fonts are replaced; see the
note under each company in the picker.

## Layout of this folder

- `themes/<id>.css`: one file per company.
- `design-lab.css`: imports the themes and holds the rules every theme shares (heading weight and tracking).
- `themes.ts`: the list of companies, their fonts and font notes.
- `useDesignLab.ts`: sets `data-lab`, remembers the choice, loads fonts.
- `DesignLabPicker.tsx`, `DesignLabMenu.tsx`: the two ways to choose.

## Removing the lab

1. Delete this folder.
2. `src/main.tsx`: remove the `initializeDesignLab` import and call.
3. `src/styles/global.css`: remove the `@import "../design-lab/design-lab.css";` line.
4. `src/components/layout/TopBar.tsx`: remove the `DesignLabMenu` import and element.
5. `src/app/DesignSystemShowcasePage.tsx`: remove the `DesignLabPicker` import and its section.
6. Remove the lab paragraph of section 1.4 in `My Plans/ui-ux/04_UI_UX_DESIGN_SYSTEM.md`.
