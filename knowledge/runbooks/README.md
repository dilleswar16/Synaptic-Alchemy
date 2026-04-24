# Corvin Runbooks

## What Is a Runbook

A runbook is a structured investigation guide for a specific alert type or
failure pattern.  The investigation engine matches an incoming alert against
the runbooks registered in `catalog.json` by keyword and injects the matching
runbooks into the system prompt.

## Naming Convention

`<alert-type-keyword>.md`

Keep filenames lowercase and hyphen-separated.  The filename should stay aligned
with the catalog entry, but matching is driven by `catalog.json`, not by
scanning markdown filenames directly.

## Required Sections

Each runbook should contain:

1. **Trigger** — what condition triggers this runbook
2. **Evidence to collect** — which adapters and queries to prioritise
3. **Common root causes** — ranked list of likely causes
4. **Fix patterns** — high-level remediation approaches (no execution in V1)
5. **Escalation path** — when to escalate and to whom

## Registering a New Runbook

1. Add a new `.md` file to this folder following the naming convention above.
2. Add an entry to `catalog.json` with the runbook file path and the keywords
	or match patterns that should trigger it.

No code changes are needed when the catalog entry is present.
