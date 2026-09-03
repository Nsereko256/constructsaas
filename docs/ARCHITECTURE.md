# ConstructSaaS Architecture Guide

This document defines the code organization used while preparing the application
for launch. It is intentionally focused on maintainability and local release
readiness; hosting and deployment are outside its scope.

## System boundaries

The Django/DRF backend owns authentication, authorization, business rules,
transactions, audit records, notifications, and exports. The React frontend
owns presentation, form interaction, navigation, and client-side caching. The
frontend must never be treated as the security boundary.

The major backend domains are:

- `accounts`: users, roles, sessions, and access context.
- `projects`: projects, sites, goals, staffing, and project scope.
- `materials`: the material catalogue and material requests.
- `warehouse`: stock, receipts, issues, transfers, returns, and locations.
- `procurement`: purchase requests, quotations, purchase orders, and amendments.
- `suppliers`: suppliers, contractors, claims, and supplier evidence.
- `finance`: budgets, invoices, payments, expenses, reconciliation, and reports.
- `workorders`: work orders, site packages, tasks, progress, and verification.
- `notifications`: notification creation, delivery, and read state.
- `dashboard`: permission-aware operational summaries.

## Backend layering rule

New backend code should follow this direction:

```text
URL -> API view -> serializer/permission -> service -> model
                                  \-> selector -> model (reads)
```

- Views coordinate HTTP concerns only.
- Serializers validate and shape input/output.
- Permissions answer whether an action is allowed.
- Services perform state-changing workflows inside transactions.
- Selectors contain reusable read queries and annotations.
- Models contain data constraints and small domain invariants.
- Export modules consume selectors; they do not duplicate business queries.

Existing behavior will be moved gradually. Do not rewrite a whole module or
change an endpoint merely to satisfy this layout.

## Frontend layering rule

Pages should compose module components and call typed API services. Shared UI
belongs under `frontend/src/components/ui`; cross-module controls belong under
`frontend/src/components/common`; domain-specific code belongs under the
corresponding module folder.

```text
route -> page -> module component -> hook/API service -> shared client
```

Role-based rendering improves usability only. Every mutation must still be
protected by backend permissions.

## Workflow ownership

Each status transition must have one owning service. A component may request a
transition, but it must not calculate or silently mutate workflow state. The
service is responsible for validation, audit logging, notifications, and
transaction boundaries.

## Cross-cutting rules

- Use stable status constants instead of repeated string literals.
- Use timezone-aware dates and centralized currency formatting.
- Use database transactions for stock and financial mutations.
- Keep audit records immutable.
- Use structured API errors that the frontend can display consistently.
- Keep PDF and Excel exports on the same selector/filter path as the screen.
- Add a regression test before moving a working workflow into a new layer.

## Refactoring sequence

1. Establish conventions and baseline checks.
2. Extract read selectors and write services without changing endpoints.
3. Split permissions and serializers by domain.
4. Move frontend API/types/components by module.
5. Add workflow and browser regression coverage.
6. Remove compatibility wrappers only after all imports are migrated.
