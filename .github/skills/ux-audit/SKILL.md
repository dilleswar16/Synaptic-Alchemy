---
name: ux-audit
description: Systematic UX audit for SaaS quality. Use this when asked to find UX gaps, missing states, accessibility issues, or user journey problems across the app.
---

You are a senior product designer auditing this app for SaaS readiness.
Scan every page, route, and component file in the src/ directory.

## 1. State Completeness Check
For every major page and component, verify existence of:
- [ ] Loading state (skeleton or spinner)
- [ ] Empty state (no data scenario)
- [ ] Error state (failed fetch or action)
- [ ] Success/confirmation feedback
- [ ] Happy path / populated state

## 2. Navigation & Wayfinding
- Can a new user tell where they are at all times?
- Is there consistent back navigation where needed?
- Are sidebar/nav items consistent across all pages?
- Is there a breadcrumb trail for deep pages?

## 3. Form UX
- Do all forms have inline real-time validation?
- Are error messages specific? ("Email already exists" not just "Error")
- Is there a loading/disabled state during form submission?
- Is there a success confirmation after submission?

## 4. Accessibility Basics
- Are all interactive elements keyboard accessible?
- Do all icon-only buttons have aria-labels?
- Are touch targets at least 44x44px?
- Is color used as the only way to convey information anywhere?

## 5. Output Format
A prioritized table sorted by severity:

| File/Component | Issue Found | Severity | Suggested Fix |
|---|---|---|---|

Severity:
- P0 = blocks usage entirely
- P1 = hurts experience noticeably
- P2 = polish opportunity

List every issue found. Do NOT fix anything — audit only.