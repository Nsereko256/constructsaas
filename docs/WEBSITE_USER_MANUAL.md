# ConstructSaaS Website Manual

**Product:** ConstructSaaS construction procurement, inventory, project delivery, work-order, and finance platform  
**Audience:** Administrators, project managers, site engineers, procurement officers, storekeepers, finance officers, finance managers, finance viewers, and demo operators  
**Document status:** Current web application guide  
**Last reviewed:** 25 August 2026

## 1. Purpose of the system

ConstructSaaS connects the operational and financial life of a construction or infrastructure company in one system. It links:

```text
Projects and sites
        ↓
Work orders and material requests
        ↓
Purchase requests and approvals
        ↓
Supplier pricing and purchase orders
        ↓
Deliveries, GRNs, accepted/rejected quantities
        ↓
Warehouse stock and project/site issue
        ↓
Supplier invoices, matching, payments, and accounting
        ↓
Budgets, reports, audit history, and month-end control
```

The system is designed around three principles:

1. **The next responsible person must be clear.** Action queues and next-action messages are shown at the top of major screens.
2. **Financial and stock records must not be silently changed.** Approvals, amendments, reversals, receipts, issues, invoices, and payments are audited.
3. **The project remains the operational centre.** Requests, work orders, sites, costs, stock issues, invoices, and progress can be tied back to a project and, where applicable, a specific site or work-order site package.

## 2. Getting started

### 2.1 Sign in

1. Open the website.
2. Enter the company username and password.
3. Select **Sign in**.
4. A user is placed on the **Dashboard** after login. The system does not reopen the previous user's last page.
5. If the account is already active on another device, the new login may require the previous session to be closed.

Use **Forgot password?** on the login screen to start password recovery. Do not share passwords between roles; approvals and audit records depend on the individual account.

### 2.2 Main navigation

The left navigation is role-aware. Users see the areas relevant to their role. A hidden menu item is not a security boundary: the backend also checks permissions on every protected action.

Common areas include:

- Dashboard
- Projects
- Project staffing
- Purchase requests
- Work orders
- Work-order invoices
- Site progress
- Purchase orders
- Goods received notes
- Supplier claims
- Deliveries
- Inventory
- Bin locations
- Inventory movements
- Site custody
- Suppliers
- Messages
- Notifications
- Reports
- Finance overview
- Budgets
- Supplier invoices
- Cash and payments
- Payment batches
- Reconciliation
- Expenses and advances
- Ledger
- Month end
- Finance reports
- Setup and audit

### 2.3 Action-first screens

On lists, records requiring action appear before informational records. Look first for:

- status badges;
- the next-action message;
- the action queue or dashboard count;
- warning or overdue indicators;
- the action buttons on the record card or row.

Use search, filters, and pagination to narrow a list. Select fields support search where the list is long.

## 3. Roles and responsibilities

### 3.1 Administrator

The Administrator owns company-wide control and exception handling.

Typical responsibilities:

- manage users, roles, company settings, and access;
- create and manage projects, sites, staffing, and contractors;
- approve the administrative gate for warehouse stock issue;
- approve or override budget-controlled exceptions where permitted;
- manage finance settings and reference data;
- review audit events, reports, and system-wide action queues;
- correct configuration and resolve escalated operational issues.

The Administrator should not use overrides as a shortcut. Every override requires a clear reason and remains in the audit history.

### 3.2 Project Manager

The Project Manager owns project delivery decisions.

Typical responsibilities:

- review and approve project purchase requests;
- return requests for correction with a reason;
- manage project sites, goals, staffing, and delegations;
- monitor project budget position and delivery progress;
- approve the project-manager gate before an Admin can approve a warehouse stock issue;
- review work orders, assignments, site progress, and completion evidence;
- monitor overdue deliveries and project exceptions.

The Project Manager should only act on projects to which they are assigned or which their permission scope allows.

### 3.3 Site Engineer

The Site Engineer raises and follows up technical requirements.

Typical responsibilities:

- create project-linked material requests;
- describe the technical need, site, work order, quantities, and required date;
- respond to correction requests;
- receive or acknowledge direct-to-site deliveries where assigned;
- update assigned work-order progress and site evidence;
- communicate through project messages.

An Engineer cannot create an unassigned, project-free project request. Replenishment requests are created through the procurement process, not as engineer project requests.

### 3.4 Procurement Officer

Procurement converts approved demand into controlled supply.

Typical responsibilities:

- review approved requests;
- check warehouse availability before requesting stock issue or buying;
- obtain supplier quotations and record supplier pricing;
- adjust proposed PO prices to match supplier quotes before Finance review;
- create purchase orders from approved quantities;
- send quoted requests or POs to Finance for review;
- follow supplier delivery dates and delays;
- request warehouse issue when the request has the required Manager and Admin approvals;
- manage supplier claims, replacements, credits, and follow-up;
- coordinate partial delivery and remaining balance procurement.

Procurement must not change an approved quantity or commercial value silently. Changes use the PO amendment workflow.

### 3.5 Storekeeper

The Storekeeper controls physical warehouse custody.

Typical responsibilities:

- receive deliveries into the warehouse;
- record accepted, rejected, damaged, and remaining quantities;
- create or review GRNs;
- fulfil approved warehouse stock-issue requests;
- issue stock to projects, work orders, and sites;
- record transfers, returns, adjustments, and movements;
- maintain bin and location information;
- raise supplier exceptions for rejected or damaged goods;
- provide evidence for receipt and custody.

The Storekeeper does not delete stock history. Corrections use reversals, adjustments, returns, or an Admin-controlled record correction.

### 3.6 Finance Officer

The Finance Officer prepares and processes finance records without bypassing maker-checker controls.

Typical responsibilities:

- review requests and quoted POs submitted by Procurement;
- prepare supplier invoices and verify attachments;
- run or review three-way matching;
- prepare payments and payment batches;
- prepare expense claims, staff advances, petty cash, and reconciliations;
- prepare journals and supporting evidence;
- monitor budget commitments and actual expenditure.

Approval or posting rights depend on the configured approval policy. The person who prepares a transaction must not approve their own transaction when maker-checker is enforced.

### 3.7 Finance Manager

The Finance Manager has the Finance Officer’s preparation access plus approval and exception authority.

Typical responsibilities:

- approve or reject budget submissions and revisions;
- review and approve finance requests;
- approve invoice exceptions and price/quantity variances;
- approve supplier invoices and payments where assigned;
- authorize budget overrides with reasons;
- approve expense claims, advances, payment batches, and journals;
- review reconciliation and month-end control;
- monitor audit history and financial reports.

Every action is recorded with the acting user, timestamp, object, decision, and reason where required.

### 3.8 Finance Viewer

The Finance Viewer is oversight-only.

Typical responsibilities:

- view budgets and budget positions;
- view payables, invoices, payments, reports, and audit history;
- monitor exceptions and pending work;
- export permitted reports.

The Finance Viewer cannot create, approve, post, pay, amend, reverse, or configure financial records.

## 4. Dashboard and action management

The Dashboard is the starting point for daily work.

It provides:

- role-specific action queues;
- workflow counts;
- project and inventory signals;
- budget utilization information for permitted roles;
- low-stock alerts;
- pending requests and invoice/payment actions;
- links to the exact record or filtered work queue requiring action.

Each role sees a different workspace. For example:

- Storekeeper: deliveries, low stock, stock issues, and warehouse movements.
- Procurement: manager-approved requests, POs, supplier follow-up, and invoice handoffs.
- Finance Officer: quoted POs, invoices, payment drafts, and preparation work.
- Finance Manager: quoted POs requiring decision, invoices, payments, journals, and budget approvals.
- Project Manager: request approvals, returned requests, project budget signals, and site progress.

Treat the Dashboard as a queue, not as a replacement for opening the record. The record contains the authoritative quantities, budget, evidence, and audit information.

## 5. Projects, sites, staffing, and goals

### 5.1 Create a project

A project should contain:

- project name and unique code;
- client and location;
- description;
- project budget or Finance budget linkage;
- project manager;
- assigned engineers;
- start and end dates;
- status.

Project access is scoped by role and assignment. A project manager or engineer should not see or act on unrelated project charts, requests, work orders, or messages.

### 5.2 Add project sites

A project can have many physical sites. Each site should have:

- site name and code;
- location;
- description;
- site manager or responsible person;
- assigned engineers;
- active/inactive status;
- open or closed status.

Site closure is an acceptance decision. Closing a site contributes to project completion percentage; it is not the same as completing a work order or receiving materials.

### 5.3 Project goals and progress

Projects can be broken into smaller goals or milestones.

Each goal can contain:

- title;
- related site or project-wide scope;
- description;
- weight;
- completion percentage;
- status;
- due date.

When goals exist, weighted goal completion becomes the project progress basis. Without goals, progress is calculated from active physical sites closed.

### 5.4 Staffing

For a long engineer list, use the searchable and bulk assignment control instead of manually scrolling. Staffing records should identify:

- project role;
- primary contact;
- assignment start and end date;
- allocation percentage;
- active/inactive state.

The system should be used to check assignment scope before approving or updating project records.

## 6. Work orders

Work orders represent controlled operational work for a project, site, contractor, or internal team.

### 6.1 Work-order information

A work order may contain:

- generated work-order number;
- project and site;
- title and detailed description;
- work category and priority;
- requester;
- responsible person, team, or contractor;
- estimated start date and due date;
- estimated, approved, and actual cost;
- status, notes, attachments, and audit history;
- one or more site packages;
- tasks and progress updates;
- linked material requests, issues, invoices, and supplier costs.

A single contractor may work across multiple sites in one project. Each site package must record its own work, progress, budget/cost, tasks, and completion state so the combined work order does not hide site-level overruns or delays.

### 6.2 Work-order lifecycle

```text
Draft → Submitted → Approved → Assigned → In Progress → Completed → Verified → Closed
```

Additional states:

- Rejected: the request is not accepted;
- On Hold: work is paused with a reason, owner, and recovery date;
- Cancelled: work will not proceed.

Typical ownership:

1. Requester creates the draft.
2. Manager or configured approver reviews the work order.
3. Responsible person or contractor accepts assignment.
4. Assigned team updates tasks and site progress.
5. Responsible person marks work completed with evidence.
6. Manager or verifier checks the result.
7. Authorized closer closes the work order.

### 6.3 Work-order materials and costs

Materials required for a work order are requested through the existing material-request workflow. They do not create a second procurement process.

```text
Work order
  → Material request
  → Purchase request
  → Supplier pricing / RFQ where used
  → Purchase order
  → GRN or direct-to-site receipt
  → Warehouse issue or site custody
```

Warehouse issues tied to the work order contribute to actual material cost. Contractor/service invoices should identify the work order and site package so Finance can calculate total actual cost.

## 7. Purchase requests

### 7.1 Project material request

An Engineer or authorized requester creates a request with:

- project;
- site or work order where relevant;
- title and justification;
- required date;
- priority;
- material lines, units, quantities, and notes.

The request must be tied to a project for project demand. Replenishment demand is a procurement/warehouse process and should not be made as an engineer project request.

### 7.2 Request lifecycle

The normal flow is:

```text
Draft
  → Submitted/Pending
  → Project Manager approval
  → Procurement review and supplier pricing
  → Sent to Finance
  → Finance review
  → Purchase order or approved stock issue
```

If returned for correction:

1. The approver gives a reason.
2. The requester or permitted editor corrects the specified fields.
3. The system preserves the return and resubmission history.
4. The request returns to the required approval step.

### 7.3 Existing stock versus procurement

Before buying, Procurement should check warehouse availability.

If stock is available:

1. Manager approval is recorded.
2. Admin approval is recorded for the stock-issue gate.
3. Procurement requests stock issue.
4. Storekeeper fulfils the issue.
5. The issue is recorded against the project, site, request, and work order.
6. The issue value updates the project budget when a Finance budget exists.

Stock issue does not require a separate Finance approval, but it must not bypass the configured Manager and Admin approvals.

If stock is insufficient:

1. Available stock can be issued as a partial issue when permitted.
2. The remaining quantity remains visible.
3. Procurement creates a purchase order only for the outstanding quantity.
4. The original request and stock issue history remain linked.

## 8. Procurement and supplier pricing

### 8.1 Supplier management

Procurement maintains suppliers and contractors, including:

- supplier or contractor identity;
- contact information;
- specialty;
- compliance records;
- preferred supplier status;
- delivery performance;
- open claims and outstanding invoices.

### 8.2 Supplier quote pricing

Material catalogue prices are reference values. Supplier quotes may differ.

When creating a PO:

1. Procurement selects the approved request.
2. Procurement selects the supplier.
3. Procurement enters the quoted unit price for each PO line.
4. Procurement attaches or records quote evidence where required.
5. The revised total and budget impact are displayed.
6. Procurement sends the quoted request/PO to Finance.
7. Finance reviews the commercial value and budget availability.

Procurement must not edit a committed PO silently. Use an amendment when a submitted or approved PO changes.

### 8.3 PO amendment workflow

Use an amendment for changes to:

- quantity;
- unit price;
- supplier;
- delivery destination;
- material substitution;
- delivery dates where approval is required.

The amendment should include:

- reason;
- changed fields;
- original and proposed values;
- budget impact;
- supporting evidence;
- resubmission and approval history.

For an approved amendment, the system releases the old open commitment and creates the revised commitment. It does not change historic receipts, invoices, issues, or payments.

## 9. Purchase orders

### 9.1 PO controls

Purchase orders are created from approved demand and must preserve approved quantities. Procurement should not create a PO for more or less than the approved outstanding quantity unless the approved workflow explicitly permits the change.

The PO should show:

- request and project;
- supplier;
- destination;
- lines, quantities, units, unit prices, and totals;
- currency and exchange rate where relevant;
- delivery dates;
- budget line and commitment;
- amendment history;
- next action.

### 9.2 PO lifecycle

The detailed status labels may vary by screen, but the control flow is:

```text
Draft/Pending
  → Finance-approved request
  → PO approval and budget commitment
  → Dispatch confirmation
  → Partial or complete delivery
  → GRN acceptance/rejection
  → Invoice matching
  → Payment
  → Closed or cancelled
```

Cancelled POs release their remaining commitment. Received quantities and invoice history are retained.

## 10. Deliveries and GRNs

### 10.1 Warehouse delivery

The Storekeeper receives a warehouse delivery against the PO.

For every line, record:

- ordered quantity;
- quantity on the current delivery;
- accepted quantity;
- rejected quantity;
- damaged quantity;
- remaining quantity;
- delivery note and evidence;
- receiving notes.

The cumulative rule is:

```text
accepted + rejected + damaged + prior accounted quantities
must never exceed the PO ordered quantity
```

The system blocks over-receipt and duplicate receipt lines.

### 10.2 Direct-to-site delivery

If the PO is marked for direct-to-site delivery, the delivery is recorded at the site or by the responsible site user. The Storekeeper does not need to receive the goods into the warehouse first.

Direct-to-site accepted quantities contribute to the project/site cost and remain linked to the PO, GRN, site, and invoice path.

### 10.3 Replacement delivery

Rejected or damaged goods create a supplier exception/claim. A replacement is not considered complete merely because a claim exists.

The replacement flow is:

1. Record the rejected/damaged quantity.
2. Create a supplier claim.
3. Set the disposition: replacement, supplier return, credit note, write-off, or concession.
4. Assign an owner and due date.
5. Track replacement delivery against the affected PO/claim.
6. Receive and accept the replacement quantity.
7. Only then make the replacement quantity available for invoice matching.

## 11. Supplier claims

Supplier claims are exception records for rejected, damaged, short, late, or commercially disputed goods.

Each claim should include:

- supplier;
- PO and GRN;
- affected material and quantity;
- project/site;
- claim reason;
- disposition;
- owner;
- due date;
- evidence and attachments;
- replacement or credit linkage;
- status and follow-up history.

Claims must not be automatically treated as resolved. A replacement claim remains open until the replacement is actually received and accepted, or the chosen commercial disposition is completed.

## 12. Warehouse and inventory

### 12.1 Inventory catalogue

Materials have a code, name, category, unit, reference price, minimum stock level, and active status.

The catalogue supports material selection in requests, POs, GRNs, stock issues, work orders, and reports.

### 12.2 Warehouse operations

The warehouse module supports:

- receiving;
- accepted/rejected/damaged quantities;
- stock issue to project/site/work order;
- stock transfers;
- site custody;
- returns;
- opening balances;
- bin and rack locations;
- inventory movements;
- valuation and movement history.

### 12.3 Stock issue

A stock issue must identify:

- project;
- site or work order where applicable;
- material;
- quantity;
- warehouse;
- requester and approvals;
- issue date;
- valuation cost;
- recipient or destination.

The system protects reserved project stock and blocks issuing more than available quantity. Partial issues leave the unissued quantity visible for procurement follow-up.

### 12.4 Stock corrections

Do not delete stock movements. Use:

- a return;
- a reversal;
- an adjustment with reason;
- a cycle-count variance workflow;
- an Admin-controlled correction with audit history.

## 13. Site custody

Site custody records material delivered or transferred to a project site.

Use it to track:

- direct-to-site receipts;
- warehouse-to-site transfers;
- engineer acknowledgement;
- site-to-warehouse returns;
- unused material;
- material consumption or issue;
- balances by site and project.

Material at a site should not remain invisible in the main warehouse balance or be available for unrelated requests if it is reserved for an active project.

## 14. Finance budgets

### 14.1 Budget structure

A Finance project budget contains:

- project;
- budget name;
- budget lines;
- budget categories;
- original amounts;
- approved revisions;
- commitments;
- actual expenditure;
- available balance;
- approval and audit history.

The budget position is:

```text
Available balance = revised budget - open commitments - actual expenditure
```

### 14.2 Budget lifecycle

```text
Draft → Submitted → Approved
              ↘ Rejected
```

Approved budgets are immutable. Changes use a revision or transfer workflow.

### 14.3 Commitment and actual timing

- A budget-controlled PO creates a commitment when approved.
- PO cancellation releases the remaining commitment.
- PO amendment releases the previous commitment and creates a new one.
- Invoice posting converts the applicable commitment into actual expenditure.
- Credit notes and reversals create compensating entries.
- Stock issue records actual material expenditure for projects with an approved Finance budget.
- Payment settles a liability; it does not consume the project budget again.
- Expense claims affect the budget when paid.
- Staff advance expenditure affects the budget when retired with an expense category.

### 14.4 Budget display

Project and Finance screens should be read together using the same figures:

- revised budget;
- open commitments;
- actual expenditure;
- available balance;
- material cost where separately shown;
- budget source.

Projects still using the legacy project budget are identified separately until a Finance budget is approved.

## 15. Supplier invoices and matching

### 15.1 Invoice preparation

Finance prepares an invoice with:

- supplier;
- supplier invoice number;
- internal invoice number;
- PO;
- GRN/accepted quantities;
- currency and exchange rate;
- tax;
- attachment/evidence;
- project, work order, or site where applicable.

Duplicate supplier invoice numbers for the same supplier are blocked.

### 15.2 Three-way matching

The match compares:

1. Purchase order: ordered quantity and price.
2. GRN: accepted quantity and physical receipt.
3. Supplier invoice: invoiced quantity and price.

The system maintains cumulative line-level quantities:

- ordered;
- accepted;
- rejected;
- damaged;
- invoiced;
- paid;
- remaining invoiceable;
- remaining payable.

An invoice cannot exceed the accepted, remaining quantity. A price variance becomes an exception requiring the configured Finance authority.

### 15.3 Partial invoices and payments

One PO can have multiple GRNs, invoices, and payments. Each new document is checked against cumulative history. Payment allocations cannot exceed the invoice balance.

## 16. Payments and payment batches

Payment preparation should include:

- supplier invoice;
- amount to pay;
- allocation to one or more invoices where permitted;
- cash/bank account;
- payment reference;
- payment date;
- attachment/evidence;
- approval and posting state.

A payment is not considered fully paid merely because it is drafted or posted. The status should reflect the actual workflow stage and bank/payment evidence.

Payment batches allow Finance to prepare multiple approved payments, obtain approval, and release them under maker-checker control.

## 17. Expenses, advances, and petty cash

### 17.1 Expense claims

An expense claim must contain:

- claimant;
- project, cost centre, or approved overhead category;
- currency and exchange rate;
- expense category;
- date and description;
- amount;
- evidence where required.

Project-linked claims require an approved project Finance budget and a category mapped to a budget line before approval/payment.

### 17.2 Staff advances

The flow is:

```text
Draft → Submitted → Approved → Paid → Retired → Closed
```

The recipient later retires the advance by recording:

- amount spent;
- amount refunded;
- expense category;
- evidence;
- reason.

Only the spent amount becomes project actual expenditure. A refund returns cash and does not become project expense.

### 17.3 Petty cash

Petty cash supports controlled cash-account activity, replenishment, disbursement, advances, refunds, and reversals.

Every transaction should have:

- cash account;
- reference;
- reason;
- amount and currency;
- posting user;
- journal linkage;
- evidence where required.

Posted petty-cash records are not edited or deleted; use a reversal.

## 18. Ledger and reconciliation

### 18.1 Ledger

The ledger records posted financial entries with:

- accounts;
- debit and credit lines;
- project and supplier dimensions;
- source document;
- fiscal period;
- posting user;
- reversal linkage.

Use the ledger for accounting truth. Use operational screens for workflow context.

### 18.2 Bank reconciliation

The reconciliation workflow compares imported or manually entered bank statement lines with posted payments and cash transactions.

Typical steps:

1. Import or enter statement lines.
2. Match to system transactions.
3. Review unmatched lines.
4. Resolve differences or post corrections.
5. Mark the reconciliation complete.

Do not close a period while material unreconciled items remain without documented approval.

## 19. Month end

Month end should check:

- open GRNs;
- unmatched invoices;
- draft or unapproved payments;
- unreconciled bank lines;
- unresolved supplier claims;
- unretired advances;
- unapproved budget revisions;
- draft journals;
- pending reversals or adjustments.

Finance should document exceptions before closing the period.

## 20. Reports and exports

### 20.1 General reports

Management reports include:

- inventory valuation;
- low-stock materials;
- procurement pressure;
- project budget versus actual;
- material cost by project;
- supplier performance;
- procurement aging;
- work-order progress;
- site progress;
- open claims;
- invoice and payment control packs.

### 20.2 Finance reports

Finance reports include:

- budget versus actual;
- payables aging;
- supplier statements;
- invoice matching exceptions;
- payments;
- expense claims;
- staff advances;
- petty cash;
- general ledger;
- bank reconciliation;
- month-end control status.

### 20.3 PDF and Excel exports

Exports should use the same filters currently applied on the screen. Before exporting:

1. Set project, site, status, supplier, date, or role filters.
2. Confirm the visible result count.
3. Select PDF or Excel.
4. Open the downloaded file and confirm the title, filters, totals, and detail rows.

Documents that commonly require PDF/Excel output include:

- purchase requests;
- purchase orders;
- GRNs;
- inventory movements;
- inventory valuation;
- supplier claims;
- work-order progress;
- work orders;
- supplier invoices;
- payment batches;
- ledger extracts;
- budget reports;
- reconciliation reports;
- month-end control packs.

## 21. Notifications and messages

Notifications are concise action summaries. Open a notification to view its detail and navigate to the linked record.

Important notification types include:

- request awaiting Manager approval;
- request returned for correction;
- request awaiting Admin approval;
- request sent to Finance;
- PO awaiting Finance review;
- PO amendment submitted;
- delivery due or overdue;
- GRN requiring action;
- rejected/damaged goods claim;
- replacement receipt required;
- stock issue awaiting Storekeeper action;
- invoice matching exception;
- invoice approval required;
- payment approval or posting required;
- budget override required;
- advance due or overdue;
- work-order assignment;
- work-order approval, deadline, overdue, or verification.

Messages are project conversations. Once a conversation is open, the header identifies the project or group rather than repeating a generic “Messages” label.

## 22. Offline web behavior

The web application has PWA/offline support for suitable draft and field operations.

When offline:

- the offline banner shows connection state;
- supported drafts can be saved locally;
- queued actions show pending sync state;
- retry and conflict states must be reviewed after reconnection.

Financial approvals, posting, reversals, budget overrides, and other high-risk decisions should be performed online. Offline data must not be assumed final until synchronization succeeds.

After rebuilding the frontend, refresh an already-open browser tab so it loads the new hashed assets.

## 23. Settings and configuration

Finance settings currently include:

- base currency;
- financial year start;
- quantity matching tolerance;
- price matching tolerance;
- Finance Officer approval threshold;
- Finance Manager approval threshold;
- maker-checker enforcement;
- negative-stock policy;
- document retention years;
- invoice evidence requirement;
- payment evidence requirement.

Reference data includes:

- currencies;
- tax codes;
- cost centres;
- budget categories;
- expense categories;
- expense accounts;
- append-only audit events.

Before go-live, confirm that every project expense category has a valid budget-category mapping and that every required project has an approved Finance budget.

## 24. Audit and control rules

The following records should be treated as immutable history:

- approvals and rejections;
- budget transactions;
- PO amendments;
- GRNs and receipt lines;
- stock movements;
- posted invoices;
- payment allocations;
- journal entries;
- reversals;
- audit events.

When a correction is needed, use the domain workflow rather than editing the historical record. The audit history should answer:

- who acted;
- what changed;
- when it changed;
- which role acted;
- which record was affected;
- why it changed;
- what approval or evidence supported it.

## 25. Common operating scenarios

### Scenario A: New material request through payment

1. Engineer creates a project/site request.
2. Project Manager approves.
3. Procurement checks warehouse availability.
4. If buying is required, Procurement obtains supplier price.
5. Procurement creates or updates the PO using the quote price.
6. Procurement sends the quoted request/PO to Finance.
7. Finance checks budget and approves.
8. Procurement approves/dispatches the PO as permitted.
9. Storekeeper receives goods and records GRN.
10. Finance creates supplier invoice.
11. Matching checks PO, accepted GRN, and invoice.
12. Finance approves/posts invoice.
13. Finance prepares and approves payment.
14. Payment is allocated and reconciled.

### Scenario B: Existing warehouse stock

1. Engineer creates a project request.
2. Project Manager approves.
3. Admin approves the stock-issue gate.
4. Procurement requests stock issue.
5. Storekeeper issues available quantity.
6. The system records the stock movement against the project/site/work order.
7. Any shortfall remains visible for procurement follow-up.

There is no supplier invoice for the warehouse-issued quantity.

### Scenario C: Partial delivery and replacement

1. Storekeeper records the delivered quantity.
2. Accepted, rejected, and damaged quantities are entered separately.
3. A supplier claim is created for the rejected/damaged quantity.
4. Procurement selects replacement or credit-note disposition.
5. Replacement delivery is received and accepted.
6. The cumulative PO balance is recalculated.
7. Finance invoices only quantities that are accepted and invoiceable.

### Scenario D: Price change after PO approval

1. Procurement starts a PO amendment.
2. Procurement records the reason and revised price.
3. The system shows original total, proposed total, change amount, and budget effect.
4. Procurement submits the amendment.
5. Finance reviews and approves/rejects it.
6. If approved, the old commitment is released and the revised commitment is created.
7. The PO can proceed only after the required approval state is complete.

### Scenario E: Project expense claim

1. Finance prepares the claim for the employee.
2. The claim is linked to a project and expense category.
3. The category must map to an approved project budget line.
4. Finance Manager/Admin approves according to threshold and maker-checker rules.
5. Finance pays the claim.
6. The project budget records the base-currency actual expenditure.

## 26. Troubleshooting guide

### The user cannot see a button

Check:

- current role;
- record status;
- project assignment;
- required previous approval;
- whether another user must act first;
- whether the action queue filter hides the record;
- whether the browser needs a refresh after a frontend build.

### “Failed to fetch”

Check:

- the web server is running;
- the device can reach the host address;
- the tunnel has not expired;
- the API URL is reachable from the device;
- browser HTTPS and host settings;
- the user is not using `127.0.0.1` from a phone, because that points to the phone itself.

### “Disallowed host”

The server does not recognize the host name being used. Add the development/tunnel host to the configured allowed hosts and restart the server. Do not disable host protection for a production deployment.

### Receipt is blocked

Check:

- the PO is approved and dispatched where required;
- the PO has the required budget commitment;
- the delivery destination is correct;
- previous accepted/rejected/damaged quantities do not already account for the line;
- the quantity entered is no greater than the remaining PO quantity;
- a direct-to-site delivery is not being sent through warehouse receiving.

### Invoice cannot be created

Check:

- at least one accepted GRN quantity exists;
- the invoice quantity does not exceed cumulative accepted quantity;
- the supplier invoice number is not duplicated for that supplier;
- replacement goods have actually been received and accepted;
- the PO and GRN are linked;
- the supplier and currency are valid.

### Amendment says no changed value

Check:

- the changed field was actually selected or entered;
- a number field was not left as an unchanged formatted value;
- a changed line item was saved in the amendment form;
- the browser has loaded the latest frontend build;
- the amendment preview shows the proposed value before submission.

### Budget is different on two screens

Compare the following four values:

- revised budget;
- open commitments;
- actual expenditure;
- available balance.

If a project is still using the legacy budget, set up and approve a Finance project budget before relying on Finance control totals.

## 27. Local launch checklist

Before a demo or local release:

- create or restore seeded demo data;
- confirm each demo role can sign in;
- confirm every project has sites and assignments;
- confirm Finance budgets and budget categories exist;
- confirm expense categories map to budget categories;
- confirm warehouse materials and opening stock;
- confirm supplier and contractor records;
- test a project request from start to finish;
- test a stock issue with Manager and Admin approval;
- test a partial delivery;
- test rejected/damaged goods and replacement receipt;
- test PO amendment and Finance approval;
- test invoice matching and partial payment;
- test expense claim, advance retirement, and petty cash;
- test project budget, Finance budget, dashboard, and report totals;
- test PDF and Excel exports;
- test notifications and action links;
- refresh browser tabs after rebuilding frontend assets;
- confirm no core automated check fails.

## 28. System architecture for maintainers

The system uses one Django REST/Channels backend and a React web frontend.

Backend domain areas:

- `accounts`: companies, users, roles, active sessions;
- `api`: shared routes, permissions, serializers, authentication, workflow actions;
- `projects`: projects, sites, goals, staffing, messages;
- `materials`: catalogue and material definitions;
- `warehouse`: stock, valuation, receipts, issues, transfers, site custody;
- `procurement`: requests, supplier prices, POs, amendments, GRNs, claims;
- `suppliers`: suppliers, contractors, compliance, performance;
- `finance`: budgets, invoices, matching, payments, expenses, ledger, reports;
- `workorders`: work orders, site packages, tasks, progress, verification;
- `notifications`: in-app, real-time, and web-push notifications;
- `dashboard`: role-aware summaries and action counts.

The intended backend flow is:

```text
URL → API view → serializer/permission → service → model
                          └→ selector → model for reads
```

The intended frontend flow is:

```text
route → page → module component → typed API service → shared API client
```

Business rules belong in backend services. The frontend controls presentation and user interaction but is not the security boundary.

## 29. Source documentation

Additional maintainer references are available in:

- `docs/ARCHITECTURE.md`
- `docs/codebase-map.md`
- `docs/finance-api.md`
- `docs/finance-release-audit.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/LOCAL_ARCHITECTURE_STATUS.md`
- `docs/api-auth.md`
- `docs/openapi.yaml`

This manual is the operational guide. The source documents remain the technical references for API contracts, development, architecture, and release verification.
