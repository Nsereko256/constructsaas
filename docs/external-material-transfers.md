# External-company materials

Open **Inventory → External transfers → New move order**.

This workflow records non-purchase materials arriving from an external company.
It does not create a PO, invoice, payable or payment. Use normal procurement for a purchase.

## Workflow

1. Admin, Procurement or Storekeeper records the sender, sender's move-order reference,
   ownership, destination warehouse, expected arrival and material lines. Materials must
   already exist in the company's catalogue. Bins are optional and must belong to that warehouse.
2. Storekeeper or Admin confirms the physical delivery: delivery reference, receipt date,
   accepted quantities and any damaged/rejected quantities. Partial deliveries are supported.
   Nothing becomes available yet. Admin receives an in-app notification.
3. Admin opens **Review & post**, checks quantities and ownership, confirms permanent-transfer
   unit values and enters an authorization reason (at least 10 characters). Rejected
   confirmations release their allocation so a corrected count can be submitted under a new reference.
4. Permanent stock enters the existing weighted-average inventory ledger. Use an approved
   material request to issue it. Borrowed stock enters a separate owner-specific custody record.

## Borrowed stock

A return due date is mandatory. The register flags overdue obligations. The detail page
shows warehouse-held stock, quantities issued to each project in the history, and the total
still owed to the sender. Borrowed materials are deliberately excluded from owned stock,
owned valuation, normal MR availability and project material costs.

Admin can record **Issue borrowed**, **Return from project**, and **Return to sender**.
Issuing does not reduce what is owed. Only a return to sender reduces the obligation.
An action cannot exceed the relevant warehouse or project balance. Borrowed stock from
different move orders/owners cannot be mixed by these actions. Consumed borrowed materials
remain owed; this workflow does not silently write off debt or convert a loan into a purchase.

## Corrections and controls

- Sender/reference duplicates and delivery-reference duplicates are rejected. Matching ignores
  case and extra spaces. A pending receipt reserves its accepted quantities to prevent over-receipt.
- Damaged/rejected quantities never enter available stock. Explain exceptions in count notes.
  Their replacement can arrive in a later receipt.
- Posted quantities are not editable through the API. Admin can reverse a posted receipt only
  before later stock/custody activity; compensating entries preserve the original history.
- After later activity, use a controlled return to sender. Permanent returns use the current
  warehouse average cost and cannot take stock reserved for another project or create negative stock.
- **Close to receipts** cancels further arrivals, not existing stock or outstanding return obligations.
  Close and replace an incorrect unreceived move order; existing references remain auditable.
- Requests are company-scoped. Site Engineers and Project Managers cannot access this central
  warehouse register. Finance staff can read but cannot receive, post or return stock.
- Each receipt/post/rejection/reversal/return records its actor and reason. Role enforcement
  is on the server as well as in the UI. Notifications contain no prices.

## Release

Run `python manage.py migrate` (warehouse migration 0014), build the frontend with
`npm run build` in `frontend`, and restart application workers. No existing records are rewritten.

Tests: `python manage.py test apps.warehouse.test_external_transfers apps.warehouse.tests`;
`npm test` and `npm run lint` in `frontend`.

## Local acceptance verification — 28 September 2026

Verified through the browser in a separate local QA company, without changing an existing
company's stock:

- Permanent transfer: received 10 bags, held them pending approval, then approved a revised
  unit value of UGX 1,200. The receipt retained that value and normal inventory showed
  10 bags worth UGX 12,000.
- Borrowed transfer: received 8 bags, issued 3 to a project (5 in warehouse, 8 still owed),
  returned the 3 from the project, then returned all 8 to the owner. Held and owed balances
  both reached zero; custody history remained intact and owned inventory was unaffected.
- Checked desktop and narrow mobile layouts, including early placement of actions and
  borrowed balances. Pending receipts did not expose posting actions to a Storekeeper.
- Backend suite: 23 passed, 1 database-feature-dependent skip. Frontend suite: 29 passed.
  Lint, production build, Django system checks and migration drift checks passed.

These are local verification results, not confirmation of a production deployment.
