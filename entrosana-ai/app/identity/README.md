# identity/

Tenants (schools), users, roles, permissions, JWT.

Every other module's queries are filtered by `tenant_id`; this module
issues those tenant ids and (eventually) the JWTs that carry them.

## Tables

- `identity_users` — staff, parents, students; tenant-scoped

## Endpoints

- `GET /api/v1/identity/users` — list users in the caller's tenant
- `POST /api/v1/identity/users` — create a user

## Planned

- `Tenant` (school) table + admin endpoints for tenant CRUD
- `Role` / `Permission` tables and an RBAC dependency
- JWT issuer (HS256, 60min access + 30d refresh) replacing the
  `X-Tenant-Id` header stub in `app/core/dependencies.py`
