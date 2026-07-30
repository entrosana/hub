# signup/

Student enrolment flow: parent submits a public application → school
admits → contracts get drafted automatically → bills get scheduled.

This module is the only one with a **public** endpoint family. Once
admitted, the application becomes a `Person(kind='student')` in
`app/admin` and a draft contract in `app/contracts`.

## Tables

- `signup_applications` — `status ∈ {received, reviewing, admitted, rejected}`

## Endpoints

- `GET  /api/v1/signup/applications` — staff queue
- `POST /api/v1/signup/applications` — public submission (rate-limited)

## Planned

- Public form rate-limiting (per IP + per email) ahead of admin queue
- On `admitted`: create Person + draft contract + open billing schedule
- Email notifications via `app/documents` template rendering pipeline
