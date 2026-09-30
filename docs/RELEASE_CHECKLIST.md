# Workflow readiness release checklist

Current working-tree verification, 2026-09-30. Supersedes the August demo checklist.
Local success does not mean deployed or fully browser-verified.
See readiness-implementation.md for scope and remaining work.

## Local automated checks

- [x] Django system check: no issues.
- [x] Migration drift check: no changes.
- [x] Full backend suite: 337 run, OK, 4 skipped (before added MR register tests).
- [x] Additional MR register suite: 5 passed.
- [x] Frontend suite after register/sticky-column changes: 43 passed (14 files).
- [x] TypeScript/production build after sticky-column and linked-order changes.
- [x] Lint and whitespace checks passed.
- [x] Latest progress/MR/PO register backend checks: 29 passed, including independent
  review, truthful lifecycle labels, Finance-off receipt completion and global totals.

## Browser gates

- [x] Exact MR return/correction/resubmission in the isolated local QA company.
- [x] PO-to-Finance handoff, actual submitted amount, separate reviewer approval.
- [x] Desktop MR summary uses full scoped backend totals.
- [x] MR register at 1280px and 390px: no pinned-column overlap, readable next-step
  text, mobile card layout and no page-wide overflow. Temporary viewport reset.
- [x] PO detail at 390px: cards stay contained, the progress badge is readable,
  all five workflow stages are visible, and material columns scroll inside their
  card. Verified after the final production build; temporary viewport reset.
- [ ] Fresh warehouse MR -> PO -> partial/full GRN -> invoice -> paid balance.
- [ ] Fresh site MR -> PO -> dispatch -> assigned Engineer receipt -> invoice ->
  paid balance, with prices hidden from the Engineer.
- [ ] Finance-off completes at receipt without a hidden Finance blocker; Admin can
  re-enable Finance.
- [ ] Correction, amendment/reapproval, damaged receipt, retry and return paths
  preserve quantities and audit history.
- [ ] Opening stock prepared by its responsible role, posted only by Admin.
- [ ] Permanent/borrowed move receipt and return preserve ownership, valuation and
  PDF/Excel exports.

## PostgreSQL gate — deferred by user decision, still required

Use a disposable, non-production PostgreSQL database and dedicated database role.
Set DATABASE_URL privately in that test environment. Never paste production
credentials or point tests at production. The role needs Django test-database
creation permissions. Record server version, commit SHA, command, full result and
all skips.

Run the full backend suite, then explicitly run:

```text
python manage.py test apps.warehouse.tests.ConcurrentReceiptValuationTests apps.finance.tests.test_matching_api.MatchConsumptionConcurrencyTests apps.finance.tests.test_payments_api.ConcurrentSupplierPaymentTests apps.finance.tests.test_expenses_api.ConcurrentPettyCashPaymentTests --noinput
```

- [ ] All four locking suites execute (zero feature skips) and pass.
- [ ] Concurrent receipt valuation, matching, supplier payment and petty cash
  cannot double-post or overspend.
- [ ] Edited PO budget approval/receipt pricing, stock issue/import/move retries
  and concurrent submission behavior verified on PostgreSQL.
- [ ] Migrations, system checks and full suite pass on that database engine.

SQLite cannot prove SELECT FOR UPDATE behavior. Its four skipped tests remain
NOT VERIFIED even when every executable SQLite test passes.

## Deployment and operational controls

- [ ] Back up the target database and verify a recoverable restore.
- [ ] Confirm intended Git SHA, build and service deployment.
- [ ] Verify deployed assets in a fresh browser, not localhost. Refresh after local
  rebuilds: existing tabs can retain old hashed lazy-chunk URLs.
- [ ] Privately configure verified sender/SMTP and outbox processing; verify actual
  delivery to an authorized test recipient and retry behavior.
- [ ] Role/company/project scope, independent confirmation rules and Engineer price
  privacy verified in API, exports and UI.
- [ ] Site custody writes remain disabled. Legacy obligations need explicit audited
  resolution, not silent balance changes.
- [ ] Do not restore retired Work Orders, Messages, quotations, supplier claims,
  ledger, reconciliation or payment-batch navigation.

Do not declare release readiness until required unchecked gates have evidence.
No commit, push or deployment was performed by these verification steps.
