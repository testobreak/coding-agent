# HRMS — Architecture

> Last updated: Phase 0. This document is the single source of truth for **how**
> the system is structured. **Why** specific decisions were made lives in
> [`adr/`](adr/).

## 1. System context

A single-tenant internal web application used by Acme staff and finance to manage:

- Employee master data, salary history, documents, appraisals
- Clients, projects, employee↔project allocations
- Monthly billing & profitability reporting
- Slack presence (informational only — never used for payroll)
- Dashboards for HR, Finance, and Leadership

There are seven roles defined in Keycloak. Authoritative permissions are in
[`rbac-matrix.md`](rbac-matrix.md).

```
┌──────────────────┐    OIDC PKCE     ┌──────────────────┐
│  Browser (React) │ ───────────────▶ │     Keycloak     │
│                  │ ◀─── id+access ──│  realm: hrms     │
└──────┬───────────┘                  └──────────────────┘
       │ Bearer JWT
       ▼
┌──────────────────┐  JPA   ┌──────────────────┐
│  Spring Boot API │ ─────▶ │   PostgreSQL 18  │
│  com.acme.hrms   │        └──────────────────┘
└──┬─────────┬─────┘
   │         │  AWS SDK v2 / S3 protocol
   │         ▼
   │  ┌──────────────────┐
   │  │   MinIO  (S3)    │   documents bucket
   │  └──────────────────┘
   │
   ▼ Spring Data Redis
┌──────────────────┐
│      Redis       │   dashboard cache, dropdown cache
└──────────────────┘
```

## 2. Backend packaging — feature-first

Single Maven module, package root `com.acme.hrms`. Code is organised **by
feature, not by layer**.

```
com.acme.hrms
├── HrmsApplication.java
├── common/
│   ├── audit/           AuditLog entity, AuditService, @Auditable aspect
│   ├── error/           ApiError, GlobalExceptionHandler, problem+json
│   ├── persistence/     BaseEntity (id, createdAt/By, updatedAt/By, deletedAt), SoftDeleteRepo
│   ├── security/        JwtRoleConverter, SecurityConfig, @CurrentUser, role constants
│   ├── storage/         StorageService interface, S3StorageService, presigner
│   ├── time/            Clock provider, time utilities
│   └── web/             pagination DTOs, request-id filter, OpenAPI config
├── employee/            Employee, Department, Designation, Location
├── salary/              Salary history (append-only)
├── project/             Client, Project, Allocation
├── billing/             Rate cards, monthly billing, invoices
├── appraisal/           Cycles, reviews, ratings
├── document/            Document metadata + storage interaction
├── slack/               Presence snapshots, daily summary, polling job
└── report/              Read-side projections, export endpoints
```

Each feature package contains its own `*Entity`, `*Repository`, `*Service`,
`*Controller`, `dto/`, `mapper/`. Cross-feature reuse goes through `common/` —
**never** through reaching into another feature's package.

## 3. Cross-cutting conventions

### 3.1 IDs
- Every entity has `id uuid PRIMARY KEY DEFAULT uuidv7()` (PG18 builtin).
- IDs are safe to expose in URLs (time-ordered, not sequential, not predictable
  enough to enumerate at scale).

### 3.2 Time
- DB: `timestamptz`, always UTC.
- Java: `Instant` for points in time, `LocalDate` for calendar dates (DOB,
  effective_from). Never `Date`, never `LocalDateTime` for instants.
- A `Clock` bean is injected into services so tests can advance time.

### 3.3 Money
- DB: `amount numeric(18,4) NOT NULL`, `currency_code char(3) NOT NULL`
  (default `'INR'`, application default from `APP_DEFAULT_CURRENCY`).
- Java: `BigDecimal` always. The `Money` value object lives in
  `common/persistence` and provides arithmetic + JSON serialisation.

### 3.4 Soft delete
- Every business entity (not `audit_log`) has `deleted_at timestamptz NULL`.
- Hibernate `@SQLRestriction("deleted_at IS NULL")` filters reads by default.
- "Hard delete" endpoints are SUPER_ADMIN-only and audited.

### 3.5 Auditing
- Every write goes through `AuditService.record(AuditEvent)`.
- `AuditEvent` carries `actor_id`, `action` (enum), `entity`, `entity_id`,
  `before_json`, `after_json`, `request_id`, `ip`, `at`.
- Reads of sensitive data (`salary.amount`, document blobs) call
  `AuditService.recordRead(...)` explicitly.
- `audit_log` is partitioned monthly (declarative partitioning) starting V1
  to avoid future re-partitioning pain.

### 3.6 Error contract
- All errors return RFC 7807 `application/problem+json`:
  ```json
  {
    "type": "https://hrms.acme/errors/validation",
    "title": "Validation failed",
    "status": 400,
    "code": "VALIDATION_ERROR",
    "detail": "joinDate must be in the past",
    "instance": "/api/employees",
    "traceId": "5b7e1f0a…",
    "fieldErrors": [{ "field": "joinDate", "code": "PAST_REQUIRED" }]
  }
  ```
- `traceId` matches the `X-Request-Id` response header for log correlation.

### 3.7 Pagination
- All list endpoints accept `?page=&size=&sort=`. Max `size` is 200.
- Responses use `Page<T>` Spring shape: `content`, `pageable`, `totalElements`,
  `totalPages`. Frontend has a typed wrapper.

### 3.8 OpenAPI
- `springdoc-openapi` exposes `/v3/api-docs` and `/swagger-ui/index.html`.
- Frontend types are generated from `/v3/api-docs` via `openapi-typescript`
  (types only — no full client). Output is gitignored.

## 4. Security

- Spring Boot configured as **OAuth2 Resource Server**, validating Keycloak JWTs.
- A `JwtRoleConverter` maps `realm_access.roles` to `ROLE_*` granted authorities.
- Endpoint authorisation uses `@PreAuthorize("hasRole('HR_ADMIN')")` etc.
- **Field-level** authorisation for sensitive responses (e.g. salary `amount`)
  happens in the service layer, not the controller — list endpoints must not
  leak fields the role isn't allowed to see.
- Bearer-only API. **No cookies, no CSRF.** CORS allowlist = the frontend origin.
- Keycloak realm `hrms` is bootstrapped from
  [`infra/keycloak/realm-hrms.json`](../infra/keycloak/realm-hrms.json).
  Roles, clients, password policy, and seed users live there. Modify the JSON
  + reset the volume to change.

## 5. Storage abstraction

```java
public interface StorageService {
    StoredObject put(String bucket, String key, InputStream data, ObjectMetadata meta);
    Optional<StoredObject> head(String bucket, String key);
    URL presignGet(String bucket, String key, Duration ttl);   // ttl <= 5 min
    URL presignPut(String bucket, String key, Duration ttl, String contentType);
    void delete(String bucket, String key);
}
```

A single `S3StorageService` implementation talks to MinIO locally and to S3
in production (only env vars differ). `key` includes a UUIDv7 + tenant-safe
prefix; original filename is metadata only.

Documents are written with SSE-S3 server-side encryption, and access is
gated through a server-side ACL check **before** a presigned URL is issued.
TTL is capped at 5 minutes.

## 6. Caching

- Redis for: dashboard summaries, dropdown lists (departments, designations,
  clients), recently-fetched employee profiles for managers.
- Cache keys are namespaced: `hrms:v1:<feature>:<id>`.
- TTLs default to 60s; dashboards 5 min.
- **Never** cache anything containing salary amounts.

## 7. Background jobs (Spring Scheduler)

| Job                       | Cadence            | What it does                                  |
|---------------------------|--------------------|-----------------------------------------------|
| Slack presence poll       | every 15 min       | snapshot `slack_presence_snapshots`           |
| Slack daily roll-up       | 23:55 IST          | aggregate to `slack_daily_summary`            |
| Appraisal due alert       | daily 09:00 IST    | enqueue notifications for upcoming reviews    |
| Probation reminder        | daily 09:05 IST    | notify HR of confirmations due in 14 days     |
| Monthly billing snapshot  | 1st of month, 02:00 IST | generate `monthly_billing` rows from allocations × rate cards |
| Dashboard precompute      | every 5 min        | refresh Redis-cached dashboard payloads       |

All jobs use `ShedLock` (or PG advisory lock) to be safe under multi-instance
deployment later. Each job writes a row to `job_run` for observability.

## 8. Database — guiding principles

- **Forward-only migrations.** Files under
  `backend/src/main/resources/db/migration` are immutable once committed.
  Need to fix something? Add `V<next>__fix_…sql`.
- **Constraints in the DB**, not just in Java. Unique indexes for natural keys,
  check constraints for invariants (e.g. `effective_to IS NULL OR effective_to > effective_from`).
- **No store-procedure business logic** for MVP.
- Use **PostgreSQL views** for read-heavy reports rather than denormalising.
- Index every FK; index every column used in `WHERE` clauses on hot tables.

## 9. Frontend conventions

- Folder layout: `src/{app,features,components,lib,api,routes}`.
- Each feature has `pages/`, `hooks/`, `components/`, `schemas/`.
- API calls go through `lib/api/client.ts` — a thin fetch wrapper that:
  attaches the bearer token from `keycloak-js`, retries 401 once after silent
  refresh, surfaces RFC-7807 problem+json errors as typed exceptions.
- Server state: TanStack Query. Form state: React Hook Form + Zod. Never mix.
- Generated API types: `frontend/src/api/generated/` (gitignored, regenerated
  via `npm run gen:api`).
- Tailwind + shadcn/ui for UI. Recharts for graphs. No second chart library.

## 10. Observability

- Logback JSON logs to stdout, `traceId` and `userId` in MDC.
- `/actuator/health`, `/actuator/info`, `/actuator/flyway`, `/actuator/metrics`
  exposed; `/actuator/**` itself authorised for SUPER_ADMIN only beyond health.
- Request/response timing logged at INFO; bodies never logged.
- A redaction filter strips `amount`, `salary`, `password`, `token` keys from
  any log line built via the structured logger.

## 11. Out of scope (for now)

- Multi-tenancy
- Multi-currency conversion (column exists; no FX engine)
- Real-time event streaming (Kafka/RabbitMQ)
- Mobile app
- Performance management beyond appraisal cycles
- Payroll calculation (we record salary; we do not run payroll)
