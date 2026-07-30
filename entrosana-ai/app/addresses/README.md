# addresses/

Swiss postal address validation + geocoding.

A dedicated module so other modules (`admin`, `billing`, `signup`)
can reference normalised addresses by id rather than denormalising
street/postcode/city into every row that needs them.

## Tables

- `addresses_records` — line1/line2, postcode, city, country (ISO2),
  optional lat/lon

## Endpoints

- `GET  /api/v1/addresses/?postcode=8001` — lookup by postcode
- `POST /api/v1/addresses/` — register a new address

## Planned

- Validate against the SwissPost MAT[CH] address dataset on POST
- Geocode via swisstopo / Google as a Celery side-job after insert
- Soft-dedupe on `(postcode, line1)` per tenant
