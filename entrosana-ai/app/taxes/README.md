# taxes/

Swiss source tax (Quellensteuer), AHV/IV/EO, payroll tax, year-end
forms. Each `Filing` row represents one period's filing of one kind
(e.g. monthly source-tax for March 2026, or year-end 2025).

## Tables

- `taxes_filings` — `kind`, `period_year`, `period_month`,
  `status ∈ {draft, ready, submitted, accepted, rejected}`,
  `submitted_at`

## Endpoints

- `GET  /api/v1/taxes/filings?year=2026` — annual view
- `POST /api/v1/taxes/filings` — draft a new filing

## Planned

- Per-canton source-tax rate tables + applicable tariff per employee
- AHV/IV computation against `app/scheduling` paid-hours feed
- Year-end form generation via DLM with strict template versioning
