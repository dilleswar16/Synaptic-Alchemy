# EV1 — Implementation Notes

## What This Version Will Implement

EV1 should implement the minimum connector and identity substrate needed for real onboarding.

### Backend

- application-scoped connector persistence
- connector credential modes
- runtime registry for connector instantiation
- connector test endpoint
- migration path from env-based config into DB-backed config
- identity resolution rules for Azure and local development

### Frontend

- application onboarding form
- connector add/edit modal
- connector test action
- connector status display
- clear separation between app, service, and connector scope

### Ops / Runtime

- local dev fallback
- same-tenant Azure managed identity support
- Key Vault support when selected
- explicit cross-tenant onboarding handling

## Implementation Rules

- keep env support for bootstrap and fallback
- do not hardcode runtime connector creation in multiple places
- do not let the UI own secret resolution
- do not introduce a second hidden connector config model
- preserve backward compatibility during migration where possible

## What To Document As We Implement

For every changed area, document:
- what was added
- why it was needed
- what dependency it replaces or de-risks
- how it affects onboarding
- how it affects identity and RBAC
- what remains unsolved after the slice

## Suggested Write-Up Order After Implementation

1. architecture summary
2. backend changes
3. UI changes
4. migration notes
5. known gaps
6. acceptance evidence
