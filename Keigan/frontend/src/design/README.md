# Keigan design (Mono)

Keigan's own design system: **Mono**, in light and dark. The original blue design stays available as **Classic**.

## What Mono is

- **Colour:** off-white and near-black surfaces, ink text, grey selected states. One green, used only for buttons (with dark text) and
  small dots. No purple, no gradients, no tinted bands; the AI marks are ink or white and the Ask Keigan panel is a dark card.
- **Type:** Inter at weights 400 and 500 only (semibold and bold render as 500). Display sizes use tight tracking; code uses the
  system monospace font. Body text is 16 px.
- **Shape and depth:** radii 4 / 6 / 12 / 12 / 16, buttons 6. Cards are flat with a 1 px hairline; three shadow levels above that.
- **Size:** buttons 30 px, fields 42 px, cards padded 32 px, a 56 px top bar; buttons and fields at least 36 px on a phone.
- **Links:** ink, with a persistent underline in body copy that thickens on hover. The action colour is never used for text.
- **Motion:** buttons press in; the rail below animates. Reduced motion switches it all off.
- **Navigation:** `rail/MonoSidebar.tsx`, a slim icon rail instead of the original sidebar. It opens over the page on hover or keyboard
  focus, a pin button keeps it open, group and item labels fade in, the active page is a pill that slides between items, and the footer
  shows the environment. `rail/NavIcons.tsx` has one two-tone icon per destination, each with its own hover animation
  (`rail/rail.css`).

## Files

- `mono.css`: the tokens (light and dark) and the rules that go beyond tokens, all under `[data-design="mono"]`.
- `rail/`: the sidebar, its icons and its motion.
- `design.css`: imports the two CSS files; `src/styles/global.css` imports this after `tokens.css`.
- `useDesign.ts`: sets `data-design` on `<html>` (`mono` or `classic`), remembers it in `localStorage` (`keigan.design`), loads Inter.
- `DesignChoice.tsx`: the Mono / Classic chooser on the Design system page; the top-bar brush menu has the same choice.

Components read size tokens (`--button-h-md`, `--control-h-md`, `--card-padding-base`, `--chip-h-md`, `--radius-button` and siblings)
with the original size as the fallback, so they look as before whenever Mono is off.

## Making Mono the only design later

Delete the Classic option (`useDesign.ts`, `DesignChoice.tsx`, the Classic part of the top-bar menu), move the contents of `mono.css`
into `styles/tokens.css` under `:root` and `[data-theme="dark"]`, and use `MonoSidebar` directly in `AppShell.tsx`.
