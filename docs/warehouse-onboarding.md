# Warehouse setup and Excel onboarding

## User flow

1. An Admin opens Inventory → Warehouses → New warehouse. Enter a name, unique
   warehouse code and optional address. Select the default receiving warehouse
   when appropriate. Changing the default does not move existing stock.
2. Open Import opening stock from the warehouse directory, or Inventory → More →
   Import opening stock. Admins can also register a missing warehouse inside this
   dialog without leaving the import workflow.
3. The dialog lists active company warehouses with search and five-per-page
   pagination. It is intentionally independent of the active-site filter.
4. Download the Excel template after registering the warehouse. Put its exact code
   in column E, `Warehouse code`. The template's Warehouse reference sheet also
   includes the new warehouse.
5. A Storekeeper/Admin previews the completed `.xlsx` and corrects all row errors,
   then submits the locked snapshot. Submission does not change inventory.
6. An independent Admin opens Confirmations, reviews each material, warehouse,
   quantity, unit cost and total value, then confirms and posts the stock. Existing
   maker/checker and controlled-override rules remain unchanged.

## Verification (local only, 2026-10-02)

- Isolated seeded company: Warehouse Onboarding QA 2c5f767c. No production records
  or external messages were used. This was not a browser company-signup test.
- Browser: empty directory → import dialog → Admin registers QA-MAIN as default.
  Storekeeper sees QA-MAIN but no registration button.
- Generated a real Excel file with two materials: 12 bags at UGX 35,000 and 6 litres
  at UGX 20,000. Both previewed successfully through the authenticated application
  API using the QA Storekeeper identity. Submitted confirmation 6 with zero stock
  movements before approval.
- Browser: independent QA Admin reviewed the new line-level snapshot and posted.
  Database verification found exactly two opening movements in QA-MAIN, quantities
  12 and 6, values UGX 420,000 and UGX 120,000. Confirmation recorded Storekeeper
  preparation and Admin approval.
- Browser file-picker automation timed out twice; file selection itself remains a
  manual browser check. The Excel bytes, parser, validation, submission and posting
  were exercised, but are not claimed as a full UI upload test.
- Backend: 16 tests passed across warehouse onboarding, readiness and import
  services. Coverage includes duplicate/normalised codes, company isolation,
  Admin-only writes, safe default changes, unknown warehouse recovery, independent
  stock approval and duplicate-post prevention.
- Frontend: full suite passed, 49 tests across 16 files, including warehouse
  form/setup (4) and approval snapshot (2) tests. Production build and lint passed.
  No database migration required.
- Visual checks: warehouse directory at 1280px and 390px, and the desktop Admin
  approval table. Inventory displayed both posted materials and UGX 540,000 total.

PostgreSQL concurrency verification remains the existing release prerequisite;
SQLite results do not prove row-lock behavior. No push or deployment performed for
these warehouse changes.
