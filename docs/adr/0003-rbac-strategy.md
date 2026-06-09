# ADR 0003: RBAC strategy — defense in depth

- Status: Accepted
- Date: 2026-05-05

## Context

HRMS holds salary, contracts, ID proofs, and appraisals. A role-leak between
LEADERSHIP and salary amounts, or between MANAGER and a non-report's profile,
is a reputational and possibly legal incident. URL-level role checks alone
are insufficient because list endpoints can return fields the caller's role
shouldn't see.

## Decision

Three-layer authorisation:

1. **Endpoint level — `@PreAuthorize`**
   Every controller method declares which roles can hit the URL. No
   `permitAll()` on business endpoints.

2. **Service level — field redaction**
   Services responsible for sensitive resources accept the `Authentication`
   (or a `CurrentUser` wrapper) and produce DTOs whose sensitive fields are
   conditionally populated. E.g. `EmployeeService.list()` always omits
   `salaryAmount`; `EmployeeService.read()` includes it only for SUPER_ADMIN /
   HR_ADMIN / FINANCE_ADMIN, or self.

3. **Row level — scope predicates**
   For roles whose access is "self / reports / project members", the
   repository layer composes a `Specification`/predicate adding the WHERE
   clause. Never trust the controller to filter.

In addition:

- Every read of `salary.amount` and every download of a document calls
  `AuditService.recordRead(...)` — this is enforced by aspect, not by
  service-author discipline.
- The `RbacMatrixTest` integration test asserts the entire matrix in
  [`docs/rbac-matrix.md`](../rbac-matrix.md). It runs on every CI build and
  blocks merge on red.
- Roles come from the JWT claim `realm_access.roles` and are mapped to
  Spring authorities prefixed `ROLE_`. No DB-stored roles for MVP — Keycloak
  is the source of truth.

## Rationale

- Endpoint-only checks have leaked sensitive fields in past projects (list
  view returns 100 rows including a field the role can't read).
- Putting the matrix into a runnable test means future contributors who
  break a rule see CI fail rather than ship a leak.
- Audit on read is cheap; a salary-leak post-mortem without an audit trail
  is much, much more expensive.

## Consequences

- Service authors must accept a `CurrentUser` argument in any method
  returning sensitive fields. Lint rule (custom Spring AOP guard) flags
  exposed entities returned directly from controllers.
- Role names are constants in `common.security.Roles` — typos in
  `@PreAuthorize` strings become compile errors via the constant import.
- Adding a new role or permission requires:
  1. Update `infra/keycloak/realm-hrms.json`.
  2. Update `docs/rbac-matrix.md`.
  3. Update `RbacMatrixTest`.
  4. Reset local Keycloak volume (or run migration script).
