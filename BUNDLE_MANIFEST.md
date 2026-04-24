# Corvin Bundle Manifest

## Purpose

This file describes what is inside the Corvin Copilot pack and how to use it in a fresh repository.

## Copy Strategy

When starting the new Corvin repository:

1. Copy the contents of this folder into the root of the new repo.
2. Keep `.github/` at the repo root.
3. Keep `docs/copilot-context/` inside the repo so Copilot and future sessions can reference the deeper product blueprint.
4. Keep `progress.md` at the root so work can resume cleanly.

## Contents

- `.github/copilot-instructions.md`
- `.github/instructions/`
- `.github/prompts/`
- `docs/copilot-context/shared/`
- `docs/copilot-context/versions/v1/`
- `docs/copilot-context/versions/v2/`
- `docs/copilot-context/versions/v3/`
- `docs/copilot-context/config-blueprints/`
- `README.md`
- `progress.md`

## Intent Of Each Area

| Area | Purpose |
|---|---|
| `.github/copilot-instructions.md` | always-on workspace rules |
| `.github/instructions/` | scoped design and implementation guidance |
| `.github/prompts/` | repeatable prompt entrypoints for phased work |
| `docs/copilot-context/shared/` | A-to-Z product context |
| `docs/copilot-context/versions/` | version-specific scope and sequencing |
| `docs/copilot-context/config-blueprints/` | replaceable configuration strategy |
| `progress.md` | resumable task tracking |

## Expected Usage Pattern

- Use the shared docs to establish product context.
- Use the version docs to constrain the current implementation.
- Use the prompts to continue one slice at a time.
- Update `progress.md` after major milestones.

## Final Reminder

This pack is a planning and implementation-context bundle. It is not the application code itself.