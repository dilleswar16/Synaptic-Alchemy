# 20 — Application team members: design

Written 2026-11-21 while the owner was away. The owner asked for a complete team-member experience in application setup (name, email, role: lead, developer, infra, devops, tester; invitations, roles and permissions, membership management, access control, invitation lifecycle, edge cases) and said to decide on their behalf. Every decision below is a call I made; each has its reason, so it can be changed cheaply.

## What exists today

- A **stakeholder** is a person, a distribution list or a Teams channel that Keigan notifies for an application: role, email, channels, minimum priority, subscribed services, language. CRUD, a directory search and a test email already exist (`stakeholder_service.py`, `NotificationsStep.tsx`).
- Roles today: `sre, developer, manager, executive, business_owner, vendor_contact`. The role decides the audience of a communication (`TECHNICAL_ROLES` get the fix details, `EXECUTIVE_ROLES` get the summary).
- **Access to an application is not stored in Keigan.** Two AD groups per application (`<CODE>_admin`, `<CODE>_reader`) decide who can open it; people get into them through SailPoint. Keigan only reads group membership at sign-in.
- Gaps: the create dialog captures no team; four of the five roles the owner named are missing; email is not format-checked; the same person can be added twice; there is no invitation, no record of whether the person ever signed in, and nothing stops removing the only lead.

## Goals

1. A team can be entered when the application is created, and managed afterwards in the same place the notification recipients live (one list, not two).
2. Roles the owner named exist and are meaningful: they decide what a person is sent.
3. A person can be invited; Keigan records whether the invitation went out, when, and whether the person has since signed in.
4. The list can never silently contradict itself: no duplicate people, no invalid addresses, no application left without a lead.

## Non-goals and anti-goals

- **Keigan does not grant access.** Putting someone on the team does not put them in an AD group, and an invitation does not bypass SailPoint. Granting access from Keigan would need a Graph write permission (`GroupMember.ReadWrite.All`) that the platform team has not approved, and it would route around the company's access review. The invitation email says which group to request, and the team list shows whether the person has signed in yet.
- No invitation token or accept link. A token would add a public endpoint and a secret to protect, for no gain: signing in with the company account *is* the acceptance, and it is already authenticated.
- No per-member permission levels. Permission levels are the two AD groups; the team role is a job role.

## Decisions

| Area | Decision | Why |
|---|---|---|
| Model | Extend the existing `stakeholder` table; do not add a second table | One list, one source of truth; notification routing already reads it |
| Roles | Add `lead`, `infra`, `devops`, `tester`. `lead`, `infra`, `devops` and `tester` count as technical (they get fix details) | They work the incident; executives keep their short summary |
| Status | Derived, not stored: `inactive` (deactivated) → `active` (has signed in) → `invited` (invitation sent) → `listed` (only a recipient) | A stored status can disagree with the facts it summarises; the facts are four nullable columns |
| New columns | `invited_at`, `invited_by_user_principal_name`, `last_invitation_sent_at`, `joined_at` (all nullable; no backfill, existing rows read as `listed`) | Additive on top of the existing schema, through Alembic |
| Acceptance | First `GET /api/auth/me` by a person whose sign-in name or email matches sets `joined_at` | Reuses the existing sign-in record; no new surface |
| Duplicates | One person per application per email, case-insensitive. Stored lower-case; a filtered unique index enforces it; the service answers with a clear message before the index would | The database must be the last word (same rule as the job queue) |
| Email format | Checked in the service on create and update, and in the create request | `email-validator` is not a dependency; a short, strict pattern is enough for an address Keigan will mail |
| Last lead | If an application has an active lead, the last one cannot be removed, deactivated or changed to another role | Someone must own the team; legacy applications with no lead are not blocked |
| Resend | Allowed while the member has not signed in; one per `TEAM_INVITATION_RESEND_COOLDOWN_MINUTES` (default 15) | Prevents the button being used to mail-bomb a person |
| Stale invitation | Shown when an invitation is older than `TEAM_INVITATION_STALE_AFTER_DAYS` (default 14) with no sign-in | Tells an admin to chase the access request; nothing expires in the backend |
| Size | At most `TEAM_MEMBERS_MAXIMUM_PER_APPLICATION` (default 100) people | Stops a runaway import; the list is rendered whole |
| Who may do what | Readers list the team; application admins add, edit, invite, resend, deactivate and remove (unchanged); every change is audited | Matches the existing rights |
| At creation | `ApplicationCreateRequest.teamMembers` (name, email, role), saved in the same transaction as the application; invitations are queued only for applications that are not merely *requested* | A requested application is not approved yet: nobody should be emailed about a workspace that may be rejected |
| Email mode | Unchanged: `EMAIL_MODE=simulated` by default. The team list shows an honest "Simulated: no email leaves Keigan" note when it is on | The infra switch is the owner's; the screen must not imply real mail |

## Edge cases covered

Invalid or missing email; same email twice in one request; same email already on the team (any letter case); more than the maximum; unknown role; removing or demoting the last lead; resend before the cooldown; resend after the person signed in; resend for a deactivated member; invite for a distribution list or Teams channel (rejected: only people are invited); a member who signs in with a different spelling of their address (match on both sign-in name and email, case-insensitive); an application that is only requested (no email).

## Verification

Backend: pytest for every rule above (unit for the email check, integration for the service, the creation flow and the sign-in hook), a drift test for the migration, the AST status-literal guard. Frontend: typecheck, locale check, production build. Not verifiable here: real email delivery and Entra sign-in matching on a real tenant.
