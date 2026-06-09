# HRMS backend

Spring Boot 4.0.6 / Java 21 service. See top-level
[`../README.md`](../README.md) for the full project context, and
[`../docs/architecture.md`](../docs/architecture.md) for design conventions.

## Layout

```
src/main/java/com/acme/hrms
├── HrmsApplication.java
├── common/
│   ├── audit/      AuditLog entity + AuditService (writes audit_log rows)
│   ├── error/      RFC 7807 ApiError + GlobalExceptionHandler + domain exceptions
│   ├── security/   SecurityConfig (OAuth2 RS), JwtRoleConverter, CurrentUser,
│   │               problem+json 401/403 handlers, Roles constants
│   ├── time/       Clock bean
│   └── web/        RequestIdFilter (X-Request-Id + MDC), OpenApiConfig
└── me/             /api/me endpoint (identity probe, demonstrates audit)

src/main/resources
├── application.yml          base profile
├── application-local.yml    developer profile, talks to docker-compose stack
├── logback-spring.xml       JSON logs in non-local, console in local
└── db/migration/V1__init_audit_log.sql

src/test
├── java/com/acme/hrms/AbstractIntegrationTest.java   Testcontainers PG18 base
├── java/com/acme/hrms/HrmsApplicationTests.java      smoke + Flyway assertions
├── java/com/acme/hrms/me/MeControllerTest.java       401 / 200 / role parsing
└── resources/application-test.yml
```

## Run

```powershell
mvn spring-boot:run "-Dspring-boot.run.profiles=local"
```

Defaults: `http://localhost:8080`, profile `local`, datasource
`jdbc:postgresql://localhost:5432/hrms` from the compose stack.

## Test

```powershell
mvn test
```

Requires Docker (Testcontainers spins up a PG18 container per JVM).

## Build a fat jar

```powershell
mvn -DskipTests clean package
java -jar target/hrms.jar
```

## Conventions enforced by this skeleton

- All errors return `application/problem+json` shaped per
  `common/error/ApiError.java`. Includes `traceId` matching `X-Request-Id`.
- Bearer-only auth — no cookies, no CSRF. Roles come from JWT
  `realm_access.roles`, mapped to `ROLE_*` authorities by
  `JwtRoleConverter`.
- `audit_log` is partitioned monthly. V1 seeds 13 partitions
  (last + current + 12 future). A scheduler to roll partitions forward
  lands in a later phase.
- No JPA `@EnableJpaAuditing` or `@EnableScheduling` yet — both light up
  in later phases when their first consumer arrives.
