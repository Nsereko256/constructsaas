# Local release checklist

Use this checklist before a demo or local release. It covers the current web application only; hosting and mobile builds are intentionally out of scope.

## Automated checks

- [x] `manage.py check`
- [x] `manage.py makemigrations --check --dry-run`
- [x] Backend API and Finance tests: 202 passed, 3 skipped
- [x] Frontend typecheck
- [x] Frontend lint with zero warnings
- [x] Frontend tests: 13 passed
- [x] Frontend production build

## Browser smoke checks

- [x] Dashboard renders for an authenticated role
- [x] Action queues render on Dashboard, Procurement, Finance, and Work Orders
- [x] Purchase requests, purchase orders, GRNs, inventory, notifications, and work orders render
- [x] Finance payables and reconciliation render
- [x] PR → PO → GRN → invoice linkage verified with seeded records
- [x] Three-way matching reaches `VERIFIED`
- [x] Maker-checker prevents the invoice preparer from approving their own invoice
- [x] A separate reviewer can approve and post the invoice
- [x] Finance audit history records the actor for submit, match, approve, and post
- [x] Cumulative ordered, accepted, invoiced, and paid quantities are visible

## Demo data created during the latest browser run

- Purchase request: `PR-20260822-0050`
- Purchase order: `PO-20260822-0020`
- Goods received note: `GRN-20260822-0018`
- Supplier invoice: `INV-20260824-00014`

The invoice was intentionally posted but not paid. It remains suitable for the next payment-run test.

## Known operational notes

- After rebuilding frontend assets while a page is already open, refresh the browser before testing. The previous page can retain old hashed chunk names.
- Payment approval and release must be tested with separate maker and checker accounts.
- Browser workflow testing should use clearly labelled demo references and should not reuse production supplier invoice numbers.

## Release gate

Do not call the web demo release-ready if any automated check fails, a core route is blank, an action queue is missing, or an approval action bypasses maker-checker controls.
