# admin/

Students, parents, staff and the organisational hierarchy that
binds them. Person rows here are the human-readable subjects of
contracts (`app/contracts`), billing (`app/billing`) and
enrolment (`app/signup`).

## Tables

- `admin_persons` — `kind ∈ {student, parent, staff}`, name, email

## Endpoints

- `GET  /api/v1/admin/persons?kind=student` — list students/parents/staff
- `POST /api/v1/admin/persons` — register a person

## Planned

- `Class` + `Enrolment` tables for the student → class graph
- Parent ↔ student relationships (a single parent can hold several
  child rows); this graph drives sibling-discount logic in `billing/`
