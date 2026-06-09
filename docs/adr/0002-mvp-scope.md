# ADR 0002: MVP-1 scope

- Status: Accepted
- Date: 2026-05-05

## Context

The product spec covers ~10 domain modules. Shipping all of them in a single
release is how internal systems get stuck at 60% complete forever. We want a
strict cut that delivers something HR can actually use, while still building
the spine that finance and analytics will plug into next.

## Decision

MVP-1 includes:

1. Auth (Keycloak realm, 7 roles, JWT validation in backend, login flow in FE)
2. Master data — Employee, Department, Designation, Location
3. Salary history (append-only, effective-dated)
4. Documents (MinIO + StorageService + presigned URLs)
5. Audit log (cross-cutting; viewer screen for SUPER_ADMIN)
6. Clients + Projects (master data)
7. Employee↔Project Allocations
8. Dashboard v0: headcount, joiners (last 30d), bench % (using allocations)
9. Hardening: pagination, sort, request-id, RBAC matrix tests, Playwright smoke

MVP-2 (deferred):

- Project rate cards + monthly billing snapshot
- Appraisal cycles + due alerts
- Slack presence polling + daily summary
- Probation reminders

MVP-3 (deferred):

- Billing vs salary, profitability, utilization analytics
- Excel + PDF exports
- Redis-cached precomputed dashboards

## Rationale

- Allocations were pulled into MVP-1 (they were originally MVP-2) because
  bench %, profitability, and billing all read from allocations. Building
  the rest on a missing allocations model would force rework.
- Slack presence is genuinely optional and isolated from the financial
  data model — safe to defer.
- Appraisal flow is socially sensitive (managers, HR, employee involved)
  and needs its own UX iteration; not worth half-shipping.

## Consequences

- The phased build order is locked (see `architecture.md` + the project
  todo list). Each phase ends in a runnable system.
- "Just one more module" requests during MVP-1 build will be deferred to
  MVP-2 unless they're a foundation issue (security, audit, error model).
