# ConstructSaaS codebase map

## Application layers

- `apps/` - Django business domains and REST APIs.
  - `accounts/` - companies, users, and active-session ownership.
  - `api/` - shared API routes, authentication, permissions, serializers, and workflow actions.
  - `finance/`, `procurement/`, `warehouse/`, `materials/`, `projects/`, `suppliers/` - business domains.
  - `notifications/` - in-app, web-push, and real-time notification delivery.
  - `web/` - Django delivery of the built web application.
- `construction_saas/` - project configuration, URL routing, ASGI, and WebSocket authentication.
- `frontend/` - React browser application.
  - `src/api/` - typed API clients.
  - `src/auth/` - sign-in and session lifecycle.
  - `src/components/` - reusable interface elements.
  - `src/pages/` - route-level screens.
  - `src/pwa/` - offline cache and draft support.
- `mobile/` - React Native application and Android build configuration.
- `docs/` - product, API, release, and architecture documentation.

## Generated files

Do not commit or retain generated logs, TypeScript build information, Python bytecode, temporary PDF checks, or package caches. They are ignored by `.gitignore` and can be regenerated.

Keep these local assets unless intentionally resetting the environment:

- `db.sqlite3` - current demo data.
- `.demo-backups/` - recoverable demo database backup.
- `mobile/.gradle-local/` and `mobile/android/app/build/` - Android build cache and release output.
- `frontend/node_modules/` and `mobile/node_modules/` - installed dependencies.

## Local run targets

- Web app and API: port `8032`.
- Browser bundle: `frontend/` builds into `apps/web/static/web/`.
- Mobile app: `mobile/`.
