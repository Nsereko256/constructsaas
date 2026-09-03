# Finance API

All endpoints require session or JWT authentication and derive the company from
`request.user.company`. Company IDs are never accepted as writable input.

Base URL: `/api/v1/finance/`

## Roles

- Finance Officer can prepare and submit financial records.
- Finance Manager can maintain finance configuration and approve, post, or reverse records.
- Finance Viewer has read-only finance access.
- Company Administrator has manager-equivalent finance access for their own company,
  except three-way-match exception decisions, which remain Finance Manager only.

Legacy project-manager and procurement access remains available on the original
finance workflow endpoints for backward compatibility. Foundation configuration is
restricted to the dedicated finance roles and company administrators.

## Foundation Resources

- `settings/`: retrieve and patch the singleton company settings record
- `currencies/`: list, retrieve, create, and patch company currencies
- `tax-codes/`: list, retrieve, create, and patch configurable Decimal tax rates
- `cost-centres/`: list, retrieve, create, and patch project-aware cost centres
- `budget-categories/`: list, retrieve, create, and patch budget categories
- `audit-events/`: list and retrieve append-only audit events

Each company receives its own active UGX currency and finance settings. Settings
include financial-year start, quantity and price matching tolerances, officer and
manager approval thresholds, maker-checker enforcement, and negative-stock policy.

## Workflow

1. Existing PR technical approval changes the PR to `APPROVED`.
2. Submit it with `/api/purchase-requests/{id}/submit-finance/`, then use a finance
   decision action.
3. Procurement creates and approves the PO; a storekeeper or authorized site
   engineer records an accepted GRN through the existing receipt API.
4. Create a draft `/supplier-invoices/` with nested PO line items.
5. Use `submit/`, `run-match/`, `approve/`, and `post/` actions in order.
6. Prepare `/payments/`, allocate invoices, then use `submit/`, `approve/`, and
   `post/`. Payment allocations and project costs are posted atomically.
7. Use invoice or payment `reverse/` actions for corrections. Posted rows are not edited.

## Project Budgeting

- `budgets/`: list, retrieve, create with lines; `submit/`, `approve/`, `reject/`, `revise/`, `transfer/`
- `budget-revisions/`: list and retrieve immutable approved revisions
- `budget-transfers/`: list and retrieve immutable transfers
- `budget-transactions/`: list and retrieve the immutable budget ledger
- `financial-approvals/`: list and retrieve purchase-request finance decisions

Budget responses calculate original budget, approved revisions, revised budget, open
commitments, actual expenditure, and available balance. Clients cannot write these
totals. Available balance is `revised budget - open commitments - actual expenditure`.

Purchase-request finance actions remain on the existing procurement router:

- `purchase-requests/{id}/submit-finance/`
- `purchase-requests/{id}/finance-approve/`
- `purchase-requests/{id}/finance-reject/`
- `purchase-requests/{id}/finance-return/`
- `purchase-requests/{id}/finance-hold/`

Purchase-order `approve/` creates a locked budget commitment. `cancel/` releases the
remaining commitment. Posting an invoice releases the applicable commitment and
records actual expenditure atomically, keeping commitments and actuals in separate
summary buckets.

PRs created before finance remain compatible. If a PR has a budget approval record,
PO creation is blocked until that record is approved.

## Resources

- `budget-approvals/`: list, retrieve, create; `submit/`, `approve/`, `reject/`
- `accounts/`: list, retrieve, create
- `supplier-invoices/`: list, retrieve, create, patch drafts; `submit/`,
  `withdraw-submission/`, `run-match/`, `match-results/`, `approve-exception/`,
  `reject-exception/`, `verify/`, `approve/`, `reject/`, `post/`, `reverse/`,
  `create-credit-note/`
- `three-way-matches/`: list and retrieve immutable match results
- `payments/`: list, retrieve, create, patch drafts; `allocate/`, `unallocate/`,
  `submit/`, `approve/`, `reject/`, `post/`, `reverse/`, `voucher/`
- `journal-entries/`: list and retrieve immutable entries and lines
- `project-costs/`: list and retrieve costs and reversal records

List endpoints support the shared page-number pagination contract, filters, search,
and ordering. The generated OpenAPI schema is available at `/api/schema/` and Swagger
UI at `/api/docs/` in development.

## Receipt Evidence

Three-way matching uses immutable accepted `GoodsReceivedNoteItem` quantities.
Warehouse receipts create valued `StockMovement` rows; direct-to-site receipts
create GRN evidence without changing warehouse quantity or value. For historical
POs received before canonical GRNs, matching retains a read-only compatibility
fallback to linked receipt movements or the received site PO.

## Idempotency

Invoice creation, matching, payment, landed-cost posting, synchronization, and
reversal requests accept an `idempotency_key`. Repeating the same operation returns
its original record; reusing the key for a different target or payload returns a
field error. Offline draft synchronization also requires a client UUID and server
version for updates and returns structured HTTP 409 conflicts rather than applying
last-write-wins.
