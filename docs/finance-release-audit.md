# Finance Release Audit

Audited: 2026-08-01. API base: `/api/v1/finance/`. Authentication is Django session
or JWT Bearer. Every queryset derives company scope from the authenticated user;
finance payloads do not accept a writable company field.

## Implemented Capabilities

- Company finance settings, currencies, configurable tax codes, cost centres,
  budget categories, and append-only audit events.
- Project budgets, revisions, transfers, technical/financial PR approval,
  commitments, actuals, exhaustion controls, thresholds, and overrides.
- Immutable GRNs, partial receiving/invoicing, item-level three-way matching,
  controlled match exceptions, supplier invoices, attachments, and credit notes.
- Multi-invoice partial payments, supplier advances, maker-checker approval,
  vouchers, statements, reversals, and posting idempotency.
- Moving weighted-average inventory, opening balances, project issues/returns,
  supplier returns, write-offs, valuation adjustments, and reconciliation.
- Landed-cost preview/allocation/approval/posting/reversal; project expenses,
  petty cash, and staff advances/retirement.
- Configurable double-entry mappings/rules, fiscal periods, journals, reversals,
  account ledger, trial balance, dashboard, reports, CSV/XLSX downloads,
  notifications/WebSockets, and conflict-safe offline draft synchronization.

All journal, budget, and project-cost values are base-currency values. Invoice and
payment balances remain in their transaction currency. Payment-date exchange-rate
differences post to `REALIZED_FX_GAIN_LOSS`; mixed-currency allocations are rejected
because one allocation currently stores one monetary amount.

## Endpoint Catalogue

Foundation: `settings/`, `currencies/`, `tax-codes/`, `cost-centres/`,
`budget-categories/`, `expense-categories/`, `cash-accounts/`, `accounts/`,
`chart-of-accounts/`, `posting-rules/`, `account-mappings/`, `fiscal-periods/`.

Budgeting: `budgets/` with `submit`, `approve`, `reject`, `revise`, `transfer`;
read-only `budget-revisions/`, `budget-transfers/`, `budget-transactions/`,
`financial-approvals/`, `budget-approvals/`.

Payables: `supplier-invoices/` with `submit`, `withdraw-submission`, `verify`,
`run-match`, `match-results`, `approve-exception`, `reject-exception`, `approve`,
`reject`, `post`, `reverse`, `create-credit-note`; read-only
`supplier-credit-notes/`, `three-way-matches/`, `invoice-approvals/`; secured
`invoice-attachments/` and `download`.

Payments: `payments/` with `allocate`, `unallocate`, `submit`, `approve`, `reject`,
`post`, `reverse`, `voucher`; read-only `payment-approvals/`, `supplier-advances/`,
secured `payment-attachments/`; `suppliers/{id}/statement/` and
`suppliers/{id}/outstanding-balance/`.

Inventory/costs: existing `/api/stock-movements/` valuation actions and read-only
valuation/history/reconciliation endpoints; finance `landed-costs/` with `preview`,
`submit`, `approve`, `post`, `reverse`; read-only `project-costs/`.

Expenses/ledger: `expense-claims/`, `staff-advances/`, `cash-accounts/` dedicated
workflow actions; read-only approval/retirement/petty-cash resources; `journals/`
with `post`, `reverse`, `trial-balance`; read-only `journal-entries/` and
`journal-reversals/`.

Summary/integration: `dashboard/`, `sync/drafts/`,
`notification-checks/deadlines/`, and 14 `reports/{slug}/` resources with
`download/csv/` and `download/xlsx/`. Canonical schema: `/api/schema/`; Swagger:
`/api/docs/`. Existing procurement finance actions remain under
`/api/purchase-requests/{id}/...` and `/api/purchase-orders/{id}/...`.

## Request Examples

```http
POST /api/v1/finance/payments/42/post/
Authorization: Bearer <access-token>
Content-Type: application/json

{"idempotency_key":"mobile-pay-42-post-v1"}
```

Successful responses serialize Decimals as strings and include drill-down IDs.
Validation failures use DRF field keys such as
`{"allocations":[{"81":["Allocation exceeds balance of 1000.00."]}]}`.
Stale offline updates return HTTP 409:

```json
{"type":"conflict","code":"stale_version","errors":{"non_field_errors":["The draft changed after the offline copy was made."]},"server":{"id":42,"version":3,"status":"DRAFT"}}
```

## Roles And Permissions

| Capability | Officer | Manager | Viewer | Admin |
|---|---:|---:|---:|---:|
| Read company finance | Yes | Yes | Yes | Yes |
| Prepare/submit drafts | Yes | Yes where retained | No | Yes |
| Maintain configuration | No | Yes | No | Yes |
| Approve/post/reverse | No | Yes | No | Yes |
| Decide match exception | No | Yes | No | No |
| Override budget | No | Yes within threshold | No | Yes |

Project managers retain technical approval and finance-submission access;
procurement officers retain PO/invoice preparation access where existing APIs allow.
Storekeepers receive warehouse GRNs and perform inventory actions. Site engineers
submit PRs and confirm assigned direct-to-site receipts. Maker-checker blocks a user
from approving/posting their own applicable record when enabled.

## Performance And Deployment

Reports use grouped aggregates, `select_related`, and `prefetch_related`; detailed
rows are paginated and authenticated exports stream generated files. Row locking
and uniqueness constraints provide PostgreSQL concurrency safety. SQLite is for
development only and cannot exercise production row-lock behavior.

Deploy with PostgreSQL `DATABASE_URL`, Redis `REDIS_URL`, a rotated
`DJANGO_SECRET_KEY`, explicit hosts/origins, and `DJANGO_DEBUG=false`. Run:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
python -m daphne -b 0.0.0.0 -p 8000 construction_saas.asgi:application
```

Back up first, then apply migrations in sequence. Migration `0014` adds nullable
client UUID/version fields and synchronization receipts without rewriting finance
history. Migration `0015` extends the system-account choice; the FX account/mapping
is created lazily by ledger configuration. Existing valued movement migration data
and historical issue rates are not recalculated.

## Frontend Integration

Treat Decimal values as strings, never JavaScript numbers for calculations. Cache
draft `client_uuid`, `version`, and idempotency key; replay the exact envelope after
timeouts. On HTTP 409, present server state and require user reconciliation. Never
queue approval/post/reversal offline. Load read status through notification REST
APIs and use the existing WebSocket only for instant notification delivery.

## Remaining Limitations

- Production concurrency tests require PostgreSQL; four lock-dependent tests are
  expected skips on SQLite.
- Monetary database columns use two decimal places even when currency metadata
  permits more; currencies requiring three or more minor-unit decimals need a
  planned schema migration.
- Cross-currency allocation within one payment is intentionally unsupported until
  allocations store both payment-currency and invoice-currency amounts.
- Tax rates are configurable, but separate recoverable-tax and withholding-ledger
  mappings are not yet modeled per tax code.
- PDF report generation is not exposed because the project has no authenticated PDF
  rendering dependency; JSON, CSV, and XLSX are available.
- The retained invoice `pay` action is a backward-compatibility shortcut. New
  clients should always use the maker-checker `/payments/` workflow.
