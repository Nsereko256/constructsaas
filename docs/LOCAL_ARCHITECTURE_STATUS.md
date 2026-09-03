# Local architecture status

This document records the local improvements made without changing hosting,
mobile, or public deployment behavior.

## Current boundaries

- Django/DRF owns authentication, permissions, validation, transactions,
  workflow transitions, audit logs, notifications, and exports.
- React owns presentation, typed API calls, form state, and cached reads.
- Domain changes should be placed in the relevant `apps/<domain>` package.
- `apps/api` is reserved for shared routes, authentication, common serializers,
  and cross-domain dashboard endpoints.

## Local safeguards

- API errors now include `message` and `field_errors` while preserving the
  original DRF payload for existing clients.
- The frontend prefers the stable API `message` field, so users see a useful
  validation message instead of a raw response key.
- Generated uploads, report output, caches, and temporary files are ignored by
  source control rules.
- Seed data is repeatable through `python manage.py seed_demo_data`.

## Change rule

When moving legacy code into a domain package, keep the existing URL and API
contract until all imports and browser tests use the new location. Add a
regression test before removing a compatibility wrapper.

## Local verification gate

Run the following before considering a local change complete:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.api.tests apps.finance.tests --keepdb
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```
