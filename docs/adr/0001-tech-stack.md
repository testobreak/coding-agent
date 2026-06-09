# ADR 0001: Tech stack

- Status: Accepted
- Date: 2026-05-05
- Decider: project owner

## Context

We are building an internal HRMS / Resource Management / Billing Analytics
platform with sensitive HR and finance data, role-based access for 7 roles,
audit requirements, dashboards, and integrations (Slack, S3). The system must
be secure, structured, auditable, and easy to extend over a multi-year horizon.

## Decision

| Concern              | Choice                                                              |
|----------------------|----------------------------------------------------------------------|
| Language (backend)   | Java 21 (LTS)                                                        |
| Framework            | Spring Boot **4.0.6** (released 2026-04-23)                          |
| Build                | Maven                                                                |
| Persistence          | Spring Data JPA + Hibernate                                          |
| Migrations           | Flyway, forward-only                                                 |
| API style            | Spring MVC `@RestController` (synchronous, blocking)                 |
| Auth                 | Spring Security as OAuth2 Resource Server, JWT from Keycloak 26      |
| Validation           | Bean Validation (Jakarta)                                            |
| API docs             | springdoc-openapi → `/v3/api-docs`, `/swagger-ui`                    |
| Mapping              | MapStruct                                                            |
| Boilerplate          | Lombok                                                               |
| Database             | PostgreSQL 18 (uses native `uuidv7()`)                               |
| Cache                | Redis 7                                                              |
| Object storage       | MinIO local, S3 prod, behind one `StorageService` interface          |
| Background jobs      | Spring `@Scheduled` (no Kafka/Quartz/Rabbit for MVP)                 |
| Frontend             | React 19 + TypeScript + Vite                                         |
| Frontend styling     | Tailwind + shadcn/ui                                                 |
| Frontend data        | TanStack Query (server) + React Hook Form + Zod (forms)              |
| Charts               | Recharts                                                             |
| Frontend types       | `openapi-typescript` (types only, no full client codegen)            |
| Local platform       | Docker Compose (postgres, keycloak, minio, redis)                    |

## Rationale

- Spring Boot is the boring/correct choice for an enterprise CRUD-heavy app
  with rich auth, scheduling, validation, and JPA needs.
- PostgreSQL beats MySQL here: better JSON, partial indexes, partitioning,
  built-in `uuidv7()`, mature analytics patterns, ergonomic for finance data.
- Keycloak removes a category of bugs we should never write ourselves
  (login flows, password reset, MFA, token refresh, role admin UI).
- MapStruct compile-time mapping avoids reflection cost and produces
  debuggable code, unlike runtime mappers.
- Lightweight `openapi-typescript` keeps the FE↔BE contract honest without
  generating an entire SDK that fights TanStack Query idioms.
- MinIO + S3 with a single `StorageService` means dev parity and zero
  rewrites when we move to AWS later.

## Consequences

- We commit to Java 21+ and PG 18+. Older infra is unsupported.
- `pom.xml` pins Spring Boot 4.0.6; bumps require an ADR addendum.
- Keycloak realm is reproduced from a committed JSON export; UI changes that
  aren't ported back to JSON are considered rebellion and will be lost on
  next reset.
- We will not introduce a second chart, mapping, or HTTP-client library
  without an ADR.
