# Development and Local Release Checks

## Backend

```powershell
.\.venv312\Scripts\python.exe manage.py check
.\.venv312\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv312\Scripts\python.exe manage.py test apps.api.tests apps.finance.tests
```

## Frontend

```powershell
cd frontend
npm run typecheck
npm run lint
npm test -- --run
npm run build
cd ..
```

## Refactor rule

Run the relevant module tests after each extraction, then run the complete
backend and frontend checks before merging the slice. Browser verification is
required for workflows involving approvals, stock, invoices, payments, or
exports.

## Definition of done for a module

- Business rules are in services/selectors rather than views or JSX.
- Permissions are tested for every supported role.
- Status transitions and side effects have regression coverage.
- Empty, loading, error, and action-required states are visible.
- Exports use the same filters and data as the screen.
- No new circular imports or duplicated business queries are introduced.
