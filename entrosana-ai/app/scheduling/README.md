# scheduling/

Class schedules, substitute teacher matching, payroll handover.

A `Schedule` row is one occurrence of a class (single date-time window
with a room). Recurring classes expand into many rows; the recurrence
spec lives upstream.

## Tables

- `scheduling_schedules` — title, starts_at, ends_at, room

## Endpoints

- `GET  /api/v1/scheduling/schedules?start=...&end=...` — window query
- `POST /api/v1/scheduling/schedules` — register a class occurrence

## Planned

- `SubstituteRequest` table — when a teacher is out, the DLM proposes
  a substitute by matching qualifications + availability against the
  schedule window
- Payroll handover to `app/taxes` — paid hours per teacher, per period
