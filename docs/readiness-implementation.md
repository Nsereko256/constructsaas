# Workflow and UI readiness

This is a working-tree progress report, not a claim of production readiness.
Preserve company isolation, Engineer price privacy, maker/checker controls, Admin
opening-stock posting, immutable receipts, and retired-feature restrictions.

## Implemented

- Server-derived PO next action, owner and blocker; direct approval, dispatch,
  Finance handoff and scoped receipt/related-record navigation.
- Receipt progress uses accepted coverage per material, excludes reversed receipts,
  and does not add unlike units. A paid partial invoice cannot complete an
  outstanding delivery or conceal another unpaid invoice.
- Completion timing uses receipt/payment evidence rather than an arbitrary edit.
- Return/reject forms validate reasons, retain failed submissions and confirm
  discarding changes. Controlled Admin reasons are sent separately.
- Finance review displays the actual submitted amount, blocks missing approval
  data and company-policy violations, and explains independent-review requirements.
  An Admin reason does not bypass the original Finance maker/checker rule.
- Admin company-readiness checks surface missing setup and legacy stock obligations
  without posting stock or restoring Site custody writes.
- MR/PO register summaries cover the scoped dataset, not a 100-row sample.
  MR queue ordering and PO delivery-date ordering happen before pagination.
  Stock queue counts/filtering include requested and partial issues only.
- Request values are labelled catalogue estimates, not commitments or spending.
  Engineer responses omit these values; loading/errors do not appear as zeros.
- Shared pinned action cells follow the measured identity-column width; MR
  next-step explanations wrap rather than hide their operative text.

## Automated evidence

- Full SQLite backend suite: 337 tests run, OK, 4 skipped before the additional MR
  register changes. The skipped tests require PostgreSQL row locking.
- Additional MR register suite: 5 passed, covering >100 records, global ordering,
  stock tab counts, company isolation, Manager scope and Engineer price privacy.
- Frontend after register/sticky-column additions: 43 tests passed (14 files).
- Latest backend progress/MR/PO register checks: 29 passed, including three new
  cases for MR/PO label consistency and invoice-tracking-off completion.
- System check and migration drift passed; no schema change is needed.

## Browser evidence — isolated local QA company only

Company: External Transfers QA SgF5dNQ. No production records, real payments or
external email were used.

- MR-QA-READY-RETURN (70): returned with a controlled reason, corrected via the
  exact-record deep link, and resubmitted for Manager review.
- PO-QA-READY-FINANCE (37), linked to MR71: direct handoff submitted UGX 6,000.
  Review showed 6,000 rather than its zero catalogue estimate. Procurement was
  visibly blocked pending Finance approval.
- A separate QA Finance Manager approved the submission; the UI then handed it
  back to Procurement. Seeded records are not evidence of a freshly created
  end-to-end MR-to-paid-invoice journey.
- Refreshed desktop MR register showed scoped totals and the correct zero Finance
  queue after approval. Final responsive evidence is in the release checklist.
- MR register verified at 1280px and 390px: readable next-step text and no overlap
  between pinned actions and stage timing. PO mobile testing found and corrected
  nested-grid stretching. Final 390px verification confirmed contained cards,
  a readable progress badge, all five workflow stages and in-card table scrolling.

## Remaining work — not claimed complete

- Fresh warehouse and direct-to-site browser journeys through invoice/payment,
  using independent responsible roles.
- Browser matrix for Finance disabled, partial/damaged receipt, stock issue,
  Admin opening-stock posting, and permanent/borrowed external moves.
- Broader form cancellation/retry consistency and large budget-selector lists.
- Legacy records without historical confirmation events may not reconstruct
  original stage wait times accurately; do not invent timestamps.
- Deployment verification and operational email delivery configuration.

## Explicit release prerequisite

The user elected to keep PostgreSQL concurrency verification as a release
prerequisite. SQLite results are not row-locking evidence. Do not mark this gate
passed or request production credentials. RELEASE_CHECKLIST.md records the
disposable-database checks and evidence required.
