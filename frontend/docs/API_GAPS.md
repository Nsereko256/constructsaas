# API Gaps And Assumptions

The new React frontend is built against the existing Django REST Framework and Channels backend without changing backend models, migrations, permissions, or workflow rules.

## Confirmed Existing API

- JWT auth exists at `POST /api/token/` and `POST /api/token/refresh/`.
- Core DRF resources exist for dashboard, users, categories, materials, projects, suppliers, stock movements, purchase requests, purchase orders, notifications, chat rooms, and chat messages.
- WebSocket routes exist for `/ws/notifications/`, `/ws/dashboard/`, and `/ws/chat/<project_id>/`.
- JWT WebSocket authentication is supported by passing the current access token as `?token=...`; the middleware still keeps Django session authentication available.

## Missing Or Reserved Backend Features

- RFQs and quotation comparison do not yet have backend models or endpoints. The frontend includes a reserved RFQ page but does not fake data.
- Forgot password does not yet have a backend endpoint. The frontend page explains that admin reset is required for now.
- There is no OpenAPI schema endpoint configured yet. Add `drf-spectacular` or DRF schema generation later if mobile/frontend contract docs are needed.
- File attachments, delivery documents, and report exports are not exposed by the current API.

## Workflow Assumptions Used

- Procurement requesting stock issue only changes PR status and notifies warehouse. Actual stock-out movements are still created by storekeeper/admin through warehouse fulfillment.
- Warehouse PO receipt creates stock movement `IN` records only for warehouse-destination POs.
- Direct-to-site POs require procurement dispatch confirmation before site engineer/admin receipt. Direct-to-site receipt does not affect warehouse stock.
