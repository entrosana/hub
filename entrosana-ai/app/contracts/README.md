# contracts/

Contract templates, Swiss e-signature flow, versioning, status
tracking. Each contract row references a `template_version` so
old signed contracts remain readable even after templates evolve.

## Tables

- `contracts_contracts` — `status ∈ {draft, sent, signed, void}`,
  `template_version`, `signed_at`

## Endpoints

- `GET  /api/v1/contracts/?awaiting_signature=true` — queue view
- `POST /api/v1/contracts/` — draft a new contract

## Planned

- E-signature integration (Skribble / DocuSign / Swisscom Sign)
- Webhook receiver flipping `status` to `signed` and setting `signed_at`
- `ContractTemplate` table holding the rendered template bundles
  alongside their version + the prompt version that produced them
