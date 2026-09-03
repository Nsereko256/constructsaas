# ConstructSaaS — Lovable UI/UX Handoff

## 1. Product context

ConstructSaaS is a construction operations system for projects, sites, material requests, procurement, warehouse control, supplier exceptions, work orders, finance, budgets, reports, notifications, and auditability.

The application already has a Django REST Framework backend and a React frontend. Lovable should improve the existing web UI and user experience without replacing the backend, duplicating business logic, or weakening permissions.

Primary users:

- Admin
- Site Engineer
- Project Manager
- Procurement Officer
- Storekeeper
- Finance Officer
- Finance Manager
- Finance Viewer

The system must remain usable on desktop and phone-sized browser screens. Web UI is the current priority; do not redesign the separate React Native app as part of this brief.

## 2. Non-negotiable architecture rules

1. Django/DRF remains the source of truth for authentication, authorization, validation, workflow transitions, financial calculations, inventory valuation, audit logs, notifications, and exports.
2. React remains responsible for presentation, form state, API calls, loading states, responsive layout, and cached reads.
3. Do not move approval or financial rules into frontend-only code.
4. Do not create duplicate procurement, inventory, invoice, payment, or notification workflows.
5. Preserve existing API routes and field names. If a new API field is necessary, add it backward-compatibly.
6. Every mutation must show the actor, result, and next action. Never silently refresh a changed record.
7. Destructive actions require confirmation and must be restricted by role and record state. Financial and stock records must remain auditable and generally immutable after posting.
8. Existing roles and permissions must be respected even when the user reaches a page through a direct URL.

## 3. Current-state audit

### Strengths to preserve

- Role-based navigation and API permissions already exist.
- Purchase requests, purchase orders, GRNs, supplier claims, warehouse movements, budgets, invoices, payments, work orders, and audit records are integrated.
- Stock issues now require Project Manager and Admin approval, but do not require Finance approval.
- When stock is issued to a project, the movement value is recorded against the approved project budget actuals.
- Partial deliveries and cumulative stock movements are supported.
- Work orders can contain multiple project sites, tasks, materials, contractors, progress, close-out, and cost data.
- PDF and Excel export patterns already exist.
- Offline draft/sync infrastructure exists; approvals, posting, reversals, and stock decisions must remain online-only.

### Main UI weaknesses to fix

1. Users cannot always tell what requires their action without opening a record.
2. Status labels are not consistently paired with a plain-language next step.
3. The same workflow sometimes uses different wording on dashboards, tables, modals, and notifications.
4. Procurement requests, purchase orders, payables, ledger, inventory movements, and work-order cards become visually dense on smaller screens.
5. Searchable selects are needed for employees, engineers, contractors, suppliers, projects, sites, materials, budget lines, and accounts.
6. Large tables need better mobile transformation into compact cards or horizontal scroll with pinned identity fields.
7. Important actions are sometimes hidden below long detail content instead of being placed in a sticky action area.
8. Notifications should be concise in the list and reveal full detail only when opened.
9. Empty, loading, error, blocked, and permission-denied states need consistent explanations and recovery actions.
10. Finance needs stronger visibility of pending approvals, budget impact, match status, payment status, and outstanding exceptions.
11. Warehouse users need clearer queues for receipts, rejected goods, stock issues, returns, and low stock.
12. Work-order progress should make site completion, goals, task completion, material cost, actual cost, and overdue work understandable at a glance.
13. Repeated headings and redundant helper text should be removed; the record identity should remain visible instead.
14. Controls need consistent rounded corners, compact spacing, icon support, keyboard focus, readable contrast, and touch targets.
15. Filters need to persist while navigating within a module and be resettable with one action.
16. Every action queue should link directly to the exact record requiring action, not only to a generic module page.

## 4. Design language

Use a calm operational interface rather than a decorative dashboard.

- Prioritize action queues over vanity metrics.
- Use one strong primary action per panel.
- Use compact cards with clear hierarchy: identity, status, next action, key amount/date, then secondary metadata.
- Use status colors consistently: neutral for draft/in progress, warning for waiting/overdue, success for completed/approved, critical for rejected/blocked.
- Pair color with text and icons; never use color alone.
- Use familiar icons for approve, return, reject, send, receive, issue, pay, export, edit, delete, audit, and notifications.
- Use concise labels such as `Awaiting Admin approval`, `Awaiting Storekeeper issue`, and `Finance review required`.
- Put the most important action at the top or in a sticky footer on detail panels.
- Keep forms single-column on phone screens and use two columns only where fields remain readable.
- Make cards and inputs compact but keep touch targets at least 44px high.
- Use progressive disclosure for long details, audit history, attachments, and line items.

## 5. Universal interaction requirements

Every list page must provide:

- Search with clear button.
- Relevant filters with searchable selects.
- Active-filter summary and `Clear filters`.
- Pagination with Previous/Next and page count.
- Loading skeleton.
- Empty state explaining how to create or find records.
- Error state with retry.
- Export buttons using the current filters.
- Mobile-friendly list/card presentation.

Every detail view must provide:

- Record number and title in the header.
- Current status and next-action message.
- Project/site/supplier/contractor context.
- Sticky action area for permitted actions.
- History/timeline showing who acted, when, what changed, and why.
- Attachments with preview/download where supported.
- Related records with direct links.
- Clear blocked-state explanation, including the exact preceding action required.

## 6. Role-specific workflow and UI requirements

### Admin

Dashboard focus: company control queue.

Must see:

- Requests waiting for Admin approval.
- Stock-issue approvals waiting for Admin.
- PO amendments requiring approval.
- Permission/configuration exceptions.
- Audit and data-integrity warnings.

Actions must show `Approve stock issue`, `Return for correction`, `Reject`, `Approve amendment`, and the reason/audit effect before confirmation.

### Site Engineer

Dashboard focus: assigned projects and requests.

Must only create requests tied to an assigned project/site.

Must see:

- Requests returned for correction.
- Work orders and tasks assigned to them.
- Site receipts and site progress requiring updates.
- Materials already requested, received, issued, rejected, or outstanding.

Use searchable project/site and engineer selectors, but never expose projects outside the user’s access scope.

### Project Manager

Dashboard focus: project decisions and execution.

Must see:

- Requests awaiting Manager approval.
- Work orders awaiting approval, assignment, verification, or close-out.
- Project budget versus commitments, actuals, and remaining balance.
- Site progress and overdue work.

Must be able to approve, return for correction with a required reason, reject, assign staff/contractors, verify work, and close site work where permitted.

### Procurement Officer

Dashboard focus: sourcing and follow-up.

Must see:

- Manager-approved requests awaiting quotation.
- Requests with remaining quantities after partial stock issue.
- POs awaiting dispatch/progress.
- Late deliveries and supplier claims.
- Requests eligible for warehouse issue.

Procurement obtains supplier quotations and sends quoted POs to Finance. Procurement may request warehouse stock issue only after the required Manager and Admin approvals. The UI must clearly distinguish:

- `Awaiting Manager approval`
- `Awaiting Admin approval for stock issue`
- `Ready to request warehouse issue`
- `Awaiting Finance review for quoted PO`

### Storekeeper

Dashboard focus: warehouse execution.

Must see at the top:

- Warehouse receipts awaiting recording.
- Stock issue requests awaiting fulfilment.
- Rejected/damaged goods and supplier claims.
- Low-stock alerts.
- Returns and site custody actions.

Stock issue detail must show requested, already issued, outstanding, available, and valuation quantities. Finance approval must not appear as a blocker for stock issue. Stock changes only after the Storekeeper confirms the physical issue.

### Finance Officer

Dashboard focus: review and preparation.

Must see:

- Quoted POs sent for Finance review.
- Supplier invoices and duplicate-number warnings.
- Three-way match status: ordered, received, invoiced, paid.
- Budget commitments and actuals.
- Expense claims, staff advances, petty cash, bank reconciliation, and exceptions.
- Stock issue actuals already posted to project budgets, without an unnecessary approval task.

Finance Officer can prepare/review records according to existing permission rules, but approval/posting must remain with the Finance Manager or authorized Admin.

### Finance Manager

Dashboard focus: authorization and financial control.

Must see:

- Every item awaiting their approval at the top.
- Amount, currency, project, budget line, available balance, variance, and evidence before approval.
- Changed PO values and budget impact in a human-readable comparison.
- Invoices, payments, journals, expense claims, advances, petty cash, and reconciliation exceptions.

Finance Manager has the Finance Officer’s operational visibility plus approval powers. Every action must show actor and timestamp.

### Finance Viewer

Dashboard focus: oversight only.

Must see reports, audit history, budget usage, invoices, payments, and exceptions. Do not show action buttons for approval, posting, reversal, configuration, or deletion.

## 7. Core workflows to represent visually

### Material request to purchase or stock issue

`Engineer creates project request → Project Manager approves or returns → Procurement obtains quote OR requests stock issue → Admin approves stock issue when applicable → Storekeeper issues stock OR Procurement creates PO → Procurement sends quoted PO to Finance → Finance reviews → PO/GRN/invoice/payment matching.`

Stock issue branch:

`Manager approval → Admin stock-issue approval → Procurement requests issue → Storekeeper issues physical stock → movement valuation posted → project budget actual updated → audit and notifications.`

Do not add Finance approval to this stock-issue branch.

### PO/GRN/invoice/payment

Show cumulative line-level values:

- Ordered quantity/value.
- Received accepted quantity/value.
- Rejected/damaged quantity.
- Invoiced quantity/value.
- Paid quantity/value.
- Remaining quantity/value.

Prevent duplicate supplier invoice numbers per supplier and prevent over-receipt, over-invoice, and overpayment.

### Supplier exception

`GRN rejection/damage → supplier claim → owner and due date → replacement/return/credit note/write-off/concession → replacement receipt or commercial resolution → invoice matching updated.`

Claims must never appear resolved merely because a replacement PO or delivery was created. Require the actual replacement receipt or approved disposition.

### Work orders

`Draft → Submitted → Approved → Assigned → In Progress → Completed → Verified → Closed`.

Support Rejected, Cancelled, and On Hold. A project may contain many sites; a work order may contain many site packages, goals, tasks, contractors, material requests, invoices, and site-specific costs.

The UI must show:

- Overall completion percentage.
- Site completion percentage.
- Goal/task progress.
- Planned versus actual cost.
- Materials issued and consumed.
- Overdue sites/tasks.
- Verification and close-out checklist.

## 8. Module-by-module implementation requirements

### Dashboard

- Role-specific action queue first.
- Each queue count links to filtered records.
- Add next-action text to queue items.
- Show project budget, commitments, actuals, and remaining balance where relevant.
- Keep mobile layout within the viewport; move secondary insights into collapsible sections.

### Procurement Requests

- Add next-action message beside every status.
- Make status/action terminology consistent.
- Show Manager/Admin/Finance/Storekeeper ownership clearly.
- Keep stock availability visible before requesting issue.
- Provide direct links from queue cards to the exact request.

### Purchase Orders

- Compact PO cards with supplier, project, total, approval state, delivery state, amendment state, and next action.
- Amendment view must show original, proposed, delta, budget effect, reason, requester, reviewer, and history without raw JSON.
- Make price changes at PO creation explicit as supplier-quoted prices.

### GRNs and Deliveries

- Clearly distinguish warehouse receipt, direct-to-site receipt, replacement receipt, and rejected/damaged receipt.
- Show remaining receivable quantities.
- Provide PDF for individual GRN and register export for all GRNs.
- Link each delivery alert to the exact PO/GRN.

### Inventory

- Show current quantity, available quantity, valuation, warehouse/site location, and last movement.
- Make issue, return, transfer, receipt, and adjustment actions distinct.
- Storekeeper cannot delete stock records; use controlled reversal/adjustment with audit.
- Export movement and valuation reports using active filters.

### Finance

- Use dedicated queues for invoices, payments, budgets, expense claims, advances, petty cash, reconciliation, and journals.
- Display `Awaiting Finance Officer`, `Awaiting Finance Manager`, `Posted`, `Paid`, `Reconciled`, and `Exception` clearly.
- Show budget impact before approval and actual expenditure after stock issue, invoice posting, expense approval, or advance retirement.
- Never make Finance approval appear required for warehouse stock issue.

### Notifications and Messages

- Compact list preview: actor, record, two-line summary, time, unread state.
- Open to see full message, reason, record link, and action button.
- Avoid repeating the word “Messages” inside a conversation view; show project/request/work-order identity instead.
- Group related notifications where appropriate, but preserve each audit-relevant event.

### Projects, Sites, Team, and Staffing

- Project detail must expose Sites, Progress, Goals, Work Orders, Budget, Materials, and Team as clear tabs or sections.
- Support many sites per project.
- Use searchable multi-select with selected chips, bulk select, role filters, and capacity warnings.
- Show assignment dates, allocation percentage, project role, primary contact, and inactive/expired assignments.

### Reports and Exports

- PDF and Excel buttons must use the current filters and show the report title, filter context, generated date, and company/project.
- Required reports: GRNs, inventory movements, inventory valuation, project material cost, budget versus actual, procurement aging, supplier claims, work-order progress, work-order cost, payables aging, payments, and audit history.

## 9. Responsive requirements

At widths below 768px:

- Convert wide tables to stacked cards or scrollable tables with the record identity pinned.
- Keep search and filter controls compact and full width.
- Use one-column forms.
- Put primary actions in a sticky bottom action bar where safe.
- Keep status and next-action message visible without opening a menu.
- Use collapsible sections for line items, audit history, and attachments.
- Avoid horizontal overflow from cards, charts, or modal forms.

## 10. Offline boundaries

Offline may support:

- Draft material requests.
- Draft work orders/tasks.
- Draft site progress notes.
- Draft receipt preparation where the existing offline design supports it.

Offline must not finalize:

- Approvals.
- Stock issue confirmation.
- Invoice posting.
- Payment approval/posting.
- Journal posting.
- Reversals or budget decisions.

Show offline status, queued drafts, sync progress, conflict details, and retry actions.

## 11. Acceptance criteria

Lovable’s work is acceptable only when:

1. Every role sees a focused dashboard and action queue.
2. Every request/PO/GRN/invoice/payment/work-order card has a clear status and next-action message.
3. Admin approval, Storekeeper issue, and Finance review are never confused in the UI.
4. The stock issue branch visibly excludes Finance approval but displays the resulting project budget actual.
5. Direct-to-site receipts do not require unnecessary warehouse receipt.
6. All approval, issue, receipt, invoice, payment, amendment, and work-order actions show actor, time, and reason where applicable.
7. All selects listed above are searchable.
8. No raw JSON is shown to normal users.
9. Mobile browser layouts do not overlap or require unusable horizontal scrolling.
10. Loading, empty, error, blocked, permission, and success states are understandable.
11. Existing API routes and workflow behavior remain intact.
12. `npm run typecheck`, production build, Django checks, role-permission tests, and browser workflows pass.

## 12. Suggested Lovable instruction

> Improve the existing ConstructSaaS React web interface according to this handoff. Do not rewrite the application or invent duplicate backend workflows. Preserve the Django REST API, existing routes, roles, permissions, audit logs, financial controls, inventory valuation, and offline boundaries. First audit the existing screens against this specification, then implement the UI improvements module by module. Keep every action role-aware and show a concise next-action message beside each status. Test Admin, Site Engineer, Project Manager, Procurement Officer, Storekeeper, Finance Officer, Finance Manager, and Finance Viewer on desktop and phone-sized layouts. Use the existing API for all business operations and report any backend gaps instead of bypassing them in frontend code.
