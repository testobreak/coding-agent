# HRMS — RBAC Matrix

> This file is **authoritative**. Every API endpoint and UI screen must trace
> back to a row here. Changes to this matrix require an ADR.

## Roles

| Role              | Intent                                                                 |
|-------------------|------------------------------------------------------------------------|
| `SUPER_ADMIN`     | Full access. Holds the audit log viewer. Use sparingly.                |
| `HR_ADMIN`        | Manages employee master data, salary, documents, appraisals.           |
| `FINANCE_ADMIN`   | Salary read/write, billing, finance reports.                           |
| `LEADERSHIP`      | Sees aggregated dashboards. **Never raw salary amounts.**              |
| `MANAGER`         | Manages own direct reports; runs appraisal cycles for the team.        |
| `PROJECT_MANAGER` | Manages projects and allocations they own; project-level billing input.|
| `EMPLOYEE`        | Self-service: own profile, own salary, own documents, own appraisals.  |

A user can hold multiple roles; effective permissions are the **union**.

## Conventions

- "Self only" means the row whose `employee_id` matches the calling user's
  Keycloak subject (mapped to `employee.keycloak_user_id`).
- "Reports" means any descendant in `employee.manager_id` tree.
- "Project members" means employees with an active `allocation` on a project
  the calling user is `project_manager_id` for.
- "Aggregates only" means the field is allowed in `sum`/`avg`/`count` queries
  but never returned per row.
- Empty cell = denied (HTTP 403).

## 1. Employee

| Action                              | SUPER | HR  | FIN | LEAD          | MGR     | PM             | EMP        |
|-------------------------------------|:-----:|:---:|:---:|:-------------:|:-------:|:--------------:|:----------:|
| List employees (no salary fields)   | All   | All | All | All           | Reports | Project members| Self only  |
| Read profile                        | All   | All | All | All           | Reports | Project members| Self       |
| Create employee                     | ✔     | ✔   |     |               |         |                |            |
| Edit employee — HR fields           | ✔     | ✔   |     |               |         |                |            |
| Edit employee — own contact info    | ✔     | ✔   |     |               |         |                | Self       |
| Terminate / mark inactive           | ✔     | ✔   |     |               |         |                |            |
| Soft-delete employee record         | ✔     | ✔   |     |               |         |                |            |
| Hard delete (audit-only)            | ✔     |     |     |               |         |                |            |

## 2. Department / Designation / Location

| Action            | SUPER | HR  | FIN | LEAD | MGR | PM  | EMP |
|-------------------|:-----:|:---:|:---:|:----:|:---:|:---:|:---:|
| Read              | ✔     | ✔   | ✔   | ✔    | ✔   | ✔   | ✔   |
| Create / Edit     | ✔     | ✔   |     |      |     |     |     |
| Soft delete       | ✔     | ✔   |     |      |     |     |     |

## 3. Salary

| Action                                   | SUPER | HR  | FIN | LEAD                | MGR | PM  | EMP        |
|------------------------------------------|:-----:|:---:|:---:|:-------------------:|:---:|:---:|:----------:|
| Read amount                              | ✔     | ✔   | ✔   | Aggregates only     |     |     | Self only  |
| Read salary history                      | ✔     | ✔   | ✔   |                     |     |     | Self only  |
| Write (new salary record)                | ✔     | ✔   | ✔   |                     |     |     |            |
| Issue correction (supersede prior row)   | ✔     | ✔   | ✔   |                     |     |     |            |
| Export salary report                     | ✔     | ✔   | ✔   |                     |     |     |            |

> Reads of `salary.amount` produce an `AUDIT_READ` row in `audit_log`.

## 4. Documents

| Action                                              | SUPER | HR  | FIN | LEAD | MGR | PM  | EMP                    |
|-----------------------------------------------------|:-----:|:---:|:---:|:----:|:---:|:---:|:----------------------:|
| Upload — public type (e.g. profile photo)           | ✔     | ✔   |     |      |     |     | Self                   |
| Upload — restricted type (offer letter, ID proof)   | ✔     | ✔   |     |      |     |     |                        |
| Download — own non-restricted documents             | ✔     | ✔   |     |      |     |     | Self                   |
| Download — restricted document (HR-only types)      | ✔     | ✔   |     |      |     |     | Self if marked sharable |
| Delete document                                     | ✔     | ✔   |     |      |     |     |                        |

## 5. Projects / Clients / Allocations

| Action                                | SUPER | HR  | FIN | LEAD          | MGR     | PM             | EMP                   |
|---------------------------------------|:-----:|:---:|:---:|:-------------:|:-------:|:--------------:|:---------------------:|
| List clients                          | ✔     | ✔   | ✔   | ✔             | ✔       | Own            |                       |
| Manage clients                        | ✔     |     | ✔   |               |         |                |                       |
| List projects                         | ✔     | ✔   | ✔   | ✔             | ✔       | Own + member of| Member of             |
| Create / edit project                 | ✔     |     | ✔   |               |         | Own (as PM)    |                       |
| List allocations                      | ✔     | ✔   | ✔   | ✔             | Reports | Own projects   | Self                  |
| Create / edit allocation              | ✔     | ✔   | ✔   |               |         | Own projects   |                       |
| Read project rate cards               | ✔     |     | ✔   | Aggregates only|        |                |                       |
| Edit project rate cards               | ✔     |     | ✔   |               |         |                |                       |

## 6. Billing

| Action                                | SUPER | HR  | FIN | LEAD            | MGR | PM            | EMP |
|---------------------------------------|:-----:|:---:|:---:|:---------------:|:---:|:-------------:|:---:|
| Read monthly billing — by project     | ✔     |     | ✔   | Aggregates only |     | Own projects  |     |
| Generate / regenerate billing         | ✔     |     | ✔   |                 |     |               |     |
| Export billing report                 | ✔     |     | ✔   |                 |     |               |     |

## 7. Appraisals

| Action                              | SUPER | HR  | FIN | LEAD | MGR              | PM  | EMP        |
|-------------------------------------|:-----:|:---:|:---:|:----:|:----------------:|:---:|:----------:|
| Manage appraisal cycles             | ✔     | ✔   |     |      |                  |     |            |
| Read appraisal — own                | ✔     | ✔   |     |      | Reports          |     | Self       |
| Submit reviewer ratings             | ✔     | ✔   |     |      | Reports          |     |            |
| Submit self-review                  | ✔     |     |     |      |                  |     | Self       |
| Read appraisal letter (document)    | ✔     | ✔   |     |      |                  |     | Self       |

## 8. Slack presence

| Action                          | SUPER | HR  | FIN | LEAD | MGR     | PM            | EMP |
|---------------------------------|:-----:|:---:|:---:|:----:|:-------:|:-------------:|:---:|
| View daily presence summary     | ✔     | ✔   |     | ✔    | Reports | Project members|    |
| View raw presence snapshots     | ✔     |     |     |      |         |                |    |

> Presence is informational only. It is **never** an input to salary,
> attendance, or appraisal.

## 9. Audit log

| Action                  | SUPER     | HR  | FIN | LEAD | MGR | PM  | EMP |
|-------------------------|:---------:|:---:|:---:|:----:|:---:|:---:|:---:|
| View audit log          | ✔         |     |     |      |     |     |     |
| Export audit log        | ✔         |     |     |      |     |     |     |

## 10. Dashboards

| Card / Section                    | SUPER | HR  | FIN | LEAD                 | MGR     | PM            | EMP |
|-----------------------------------|:-----:|:---:|:---:|:--------------------:|:-------:|:-------------:|:---:|
| Headcount, joiners, leavers       | ✔     | ✔   |     | ✔                    | Reports |               |     |
| Bench % / utilization             | ✔     |     | ✔   | ✔                    |         | Own projects  |     |
| Billing vs salary (aggregated)    | ✔     |     | ✔   | ✔                    |         |               |     |
| Project profitability             | ✔     |     | ✔   | ✔                    |         | Own projects  |     |
| Appraisals due                    | ✔     | ✔   |     | ✔                    | Reports |               |     |

## Test policy

For every cell in the matrix marked ✔ (or with a scope) there is at least one
integration test asserting **200**. For every empty cell there is at least one
test asserting **403**. Tests live in
`backend/src/test/java/com/acme/hrms/security/RbacMatrixTest.java`.

A red CI on `RbacMatrixTest` blocks merge. Period.
