# HRMS

Internal HR / Resource Management / Billing Analytics platform.

| Layer       | Tech                                                                 |
|-------------|----------------------------------------------------------------------|
| Backend     | Java 21, Spring Boot 4.0.6 (Web MVC, Data JPA, Security, OAuth2 RS, Validation, Scheduler, Actuator), Maven, Flyway, MapStruct, Lombok, springdoc-openapi |
| Database    | PostgreSQL 18 (native `uuidv7()`, `citext`, `pgcrypto`)              |
| Auth        | Keycloak 26 (OAuth2 / OIDC, PKCE)                                    |
| Frontend    | React 19, TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, React Router, React Hook Form, Zod, Recharts, keycloak-js |
| Storage     | MinIO locally, S3 in production (single `StorageService` abstraction) |
| Cache / Jobs | Redis, Spring `@Scheduled`                                          |

## Quick start (local)

Prerequisites:
- Docker Desktop (or Docker Engine + Compose v2)
- JDK 21
- Node.js 20+ and npm

```powershell
# 1. configure env
Copy-Item .env.example .env

# 2. bring up the platform (postgres, keycloak, minio, redis)
docker compose -f infra/docker-compose.yml --env-file .env up -d

# 3. wait until healthy
docker compose -f infra/docker-compose.yml ps
```

After step 3 you should have:

| Service       | URL / Port                 | Credentials (defaults)                     |
|---------------|----------------------------|---------------------------------------------|
| PostgreSQL    | localhost:5432             | `hrms` / `POSTGRES_PASSWORD` from `.env`    |
| Keycloak      | http://localhost:8081      | `admin` / `KEYCLOAK_ADMIN_PASSWORD`         |
| Keycloak realm | `hrms` (auto-imported)    | seeded users: admin@acme.local, hr@…, employee@… |
| MinIO API     | http://localhost:9000      | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`   |
| MinIO Console | http://localhost:9001      | same as above                               |
| Redis         | localhost:6379             | no auth in dev                              |

Backend and frontend run on the host (not in Docker) during dev so reload is fast. Their setup will land in Phase 1 / Phase 3.

## Running the backend (Phase 1)

Once the compose stack is healthy:

```powershell
cd backend
mvn spring-boot:run "-Dspring-boot.run.profiles=local"
```

Then probe:

| URL                                              | Expectation                                                   |
|--------------------------------------------------|----------------------------------------------------------------|
| `http://localhost:8080/actuator/health`          | `200 {"status":"UP"}` (no auth)                                |
| `http://localhost:8080/swagger-ui.html`          | OpenAPI explorer (no auth in dev)                              |
| `http://localhost:8080/api/me` (no token)        | `401` with `application/problem+json` body, `WWW-Authenticate` |
| `http://localhost:8080/api/me` with bearer JWT   | `200` with `subjectUuid`, `username`, `email`, `roles[]`       |

### Getting a token for `/api/me`

```powershell
$body = "client_id=hrms-frontend&grant_type=password&username=hr@acme.local&password=Hr#1234567"
$tok  = Invoke-RestMethod -Method Post `
        -ContentType "application/x-www-form-urlencoded" `
        -Uri "http://localhost:8081/realms/hrms/protocol/openid-connect/token" `
        -Body $body
Invoke-RestMethod -Headers @{ Authorization = "Bearer $($tok.access_token)" } `
                  -Uri "http://localhost:8080/api/me"
```

> The seeded users (`admin@acme.local`, `hr@acme.local`, `employee@acme.local`)
> have `temporary: true` passwords — log in once via the SPA when it lands
> (Phase 3) to clear the temp flag, or set `temporary: false` in
> `infra/keycloak/realm-hrms.json` for headless flows.

### Maven prereqs / quirks

- JDK 21 and Maven 3.9+ on `PATH`.
- On Windows, if the JDK truststore can't see Maven Central (corporate
  proxy / MITM), run with `-Djavax.net.ssl.trustStoreType=Windows-ROOT
  -Djavax.net.ssl.trustStore=NUL` so the JDK trusts whatever Windows trusts.
- Integration tests use Testcontainers (real PostgreSQL 18). Docker Desktop
  must be running and reachable. If `mvn test` reports "Could not find a
  valid Docker environment", enable **Docker Desktop → Settings → General →
  Expose daemon on `tcp://localhost:2375` without TLS** and set
  `DOCKER_HOST=tcp://localhost:2375`.

## Repo layout

```
HRMS/
├── backend/                 Spring Boot service (added in Phase 1)
├── frontend/                React app (added in Phase 3)
├── infra/
│   ├── docker-compose.yml   local platform stack
│   ├── keycloak/
│   │   └── realm-hrms.json  realm definition, auto-imported on first start
│   ├── postgres/init/       extensions + version guard (run once on empty volume)
│   └── minio/               (reserved for future bootstrap assets)
├── docs/
│   ├── architecture.md      system-level design
│   ├── rbac-matrix.md       authoritative role × resource × action matrix
│   └── adr/                 architecture decision records (immutable history)
├── .env.example             every env var the system reads
├── .gitignore
└── .gitattributes
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system design, packaging, conventions
- [`docs/rbac-matrix.md`](docs/rbac-matrix.md) — what each role can see and do
- [`docs/adr/`](docs/adr/) — why we made the decisions we made

## Resetting local state

```powershell
docker compose -f infra/docker-compose.yml --env-file .env down -v
```

The `-v` flag deletes volumes (postgres data, minio data). On next `up`, the realm is re-imported and the documents bucket is recreated.

## Conventions (TL;DR)

- All timestamps stored as `timestamptz` UTC; `Instant` in Java; format in the frontend with the user's TZ.
- All money columns are `numeric(18,4)` paired with `currency_code char(3) NOT NULL` (default `INR`). Never use `double`.
- Primary keys are `uuid DEFAULT uuidv7()`.
- Soft delete everywhere via `deleted_at timestamptz` — except `audit_log`, which is append-only.
- Audit on every write; audit on read only for sensitive fields (salary `amount`, document blobs).
- No salary amounts in logs, ever. `@ToString.Exclude` enforced on sensitive fields.
- Never edit a committed Flyway migration. Add a new one.
