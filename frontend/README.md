# ConstructSaaS Frontend

Professional React web frontend for the existing ConstructSaaS Django REST API and Channels backend.

## Stack

- React 18, TypeScript, Vite
- React Router
- Tailwind CSS with Salesforce-inspired compact SaaS design tokens
- TanStack Query and TanStack Table
- React Hook Form, Zod, Recharts, Lucide
- Native WebSockets for notifications, dashboard updates, and project chat
- Vitest/Testing Library and Playwright scaffolding

## Setup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev -- --port 5173
```

Set `.env` to your Django backend:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8023
VITE_WS_BASE_URL=ws://127.0.0.1:8023
```

## Backend Expectations

Run Django with ASGI/Daphne so WebSockets work:

```bash
.venv\Scripts\python.exe -m daphne -b 127.0.0.1 -p 8023 construction_saas.asgi:application
```

The frontend uses JWT for API requests and keeps existing Django session/template pages untouched.

## Verification

```bash
npm run typecheck
npm run lint
npm run test
npm run build
npm run test:e2e
```

This machine currently does not expose `node` or `npm` on `PATH`, so those commands require Node.js 20+ to be installed or added to `PATH`.
