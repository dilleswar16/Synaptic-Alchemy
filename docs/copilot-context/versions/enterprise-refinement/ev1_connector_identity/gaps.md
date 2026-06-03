# EV1 — Open Gaps

## Gaps That Must Be Resolved Before EV1 Is Considered Strong

- exact connector scope for this version
- exact identity precedence when both env and managed identity are available
- exact RBAC roles per connector type
- exact migration path for existing env-based deployments
- exact cross-tenant onboarding flow
- exact rules for read-only versus execute-capable identities

## Known Risk Areas

- too many config paths will confuse operators
- hidden fallback logic can make support harder
- local dev convenience can leak into production assumptions
- cross-tenant support can explode scope if not isolated
- connector creation can become UI-heavy unless the flow is tightly staged

## Gaps To Revisit In EV2

- full auth and RBAC enforcement
- audit trail for connector changes
- tenant isolation hardening
- secret lifecycle management
