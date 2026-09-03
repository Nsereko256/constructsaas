# ConstructSaaS — Full System Plan
> Construction Inventory, Procurement & Communication Platform  
> Built for Uganda's Construction Industry

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [User Roles & Permissions](#2-user-roles--permissions)
3. [Module 1 — Materials & Inventory](#3-module-1--materials--inventory)
4. [Module 2 — Stock Movements & Warehouse](#4-module-2--stock-movements--warehouse)
5. [Module 3 — Projects](#5-module-3--projects)
6. [Module 4 — Suppliers](#6-module-4--suppliers)
7. [Module 5 — Procurement (PR → PO Workflow)](#7-module-5--procurement-pr--po-workflow)
8. [Module 6 — Messaging & Team Chat](#8-module-6--messaging--team-chat)
9. [Module 7 — Notifications](#9-module-7--notifications)
10. [Module 8 — Dashboard](#10-module-8--dashboard)
11. [Module 9 — Reports & Exports](#11-module-9--reports--exports)
12. [Module 10 — Analytics](#12-module-10--analytics)
13. [Complete Workflows End to End](#13-complete-workflows-end-to-end)
14. [Database Design](#14-database-design)
15. [System Architecture](#15-system-architecture)
16. [Real-Time Features (WebSockets)](#16-real-time-features-websockets)
17. [Security & Access Control](#17-security--access-control)
18. [SaaS & Multi-Company Structure](#18-saas--multi-company-structure)
19. [Tech Stack](#19-tech-stack)
20. [URL Structure](#20-url-structure)

---

## 1. System Overview

ConstructSaaS is a web-based construction management platform that gives Ugandan construction companies one place to manage their entire operation — from the moment materials are requested on site to the moment they are received, stocked, and reported on.

### What Problem It Solves

| Before ConstructSaaS | After ConstructSaaS |
|---|---|
| Stock levels tracked on WhatsApp | Live stock levels visible to everyone at all times |
| Purchase requests lost in group chats | Structured PR workflow with approval chain and audit trail |
| Nobody knows how much cement is left | Automatic low-stock alerts the moment minimums are hit |
| Project material costs are a mystery | Per-project material usage and cost tracked automatically |
| Team communication scattered across apps | Built-in project chat linked to each project |
| Reports done manually in Excel at month end | Live reports available anytime, exportable as PDF or Excel |
| Multiple companies share no isolation | Each company has completely private, isolated data |

### The 10 Modules

| # | Module | Core Job |
|---|---|---|
| 1 | Materials & Inventory | Track every construction material with live stock calculation |
| 2 | Stock Movements & Warehouse | Record every IN and OUT with full audit trail |
| 3 | Projects | Manage construction sites, budgets, and material usage |
| 4 | Suppliers | Supplier directory with ratings and contact management |
| 5 | Procurement | Full PR → Approval → PO → Received workflow |
| 6 | Messaging & Team Chat | Per-project team chat via WebSockets |
| 7 | Notifications | Live alerts for every important event |
| 8 | Dashboard | Real-time KPI overview for the whole company |
| 9 | Reports & Exports | Inventory, project usage, and procurement reports |
| 10 | Analytics | Charts and trends for stock and project activity |

---

## 2. User Roles & Permissions

Every user belongs to exactly one company and has exactly one role. The role is enforced server-side — it is not just a visual change, it is a hard block at the application level.

### The 5 Roles

#### Role 1 — Site Engineer
**Who they are:** Field-based engineer working on the construction site.

**Their daily job in the app:**
- Submit purchase requests when materials are running low or needed
- View stock levels for materials linked to their project
- Track the status of their own purchase requests
- Participate in project team chat

**What they cannot do:**
- Approve or reject any purchase request
- Create or manage purchase orders
- Add, edit, or delete materials
- See procurement financials or supplier details
- Access reports or audit logs

---

#### Role 2 — Storekeeper
**Who they are:** The person physically managing the materials store.

**Their daily job in the app:**
- Record every stock movement — IN when deliveries arrive, OUT when materials go to site
- See live stock levels for all materials
- Make manual stock adjustments when needed (with reason)
- Receive delivered goods linked to a Purchase Order
- See low-stock alerts and escalate to procurement

**What they cannot do:**
- Approve purchase requests
- Create purchase orders
- Manage suppliers
- Access financial reports

---

#### Role 3 — Project Manager
**Who they are:** The person overseeing one or more construction projects.

**Their daily job in the app:**
- Review and approve or reject purchase requests from site engineers
- Monitor material usage and costs per project
- Track project status and budget vs actual spend
- Participate in project team chat
- See dashboard overview of all active projects

**What they cannot do:**
- Create purchase orders
- Record stock movements
- Manage the supplier list
- Access company-level admin settings

---

#### Role 4 — Procurement Officer
**Who they are:** The person responsible for purchasing materials from suppliers.

**Their daily job in the app:**
- Create purchase orders from approved purchase requests
- Manage the supplier directory
- Track all open purchase orders and their delivery status
- Mark purchase orders as received (triggers automatic stock update)
- Generate procurement reports

**What they cannot do:**
- Approve or reject purchase requests (that is the Project Manager's job)
- Record manual stock movements
- Manage company users
- Access audit logs

---

#### Role 5 — Admin
**Who they are:** The company owner or operations manager.

**Their daily job in the app:**
- Full access to every module and every action
- Invite and manage team members, assign roles
- View the complete audit log of every action ever taken
- Manage company settings and subscription plan
- Override any action if needed

**What they cannot do:**
- See another company's data (company isolation is absolute, even for admins)

---

### Permissions Matrix

| Action | Site Engineer | Storekeeper | Project Manager | Procurement Officer | Admin |
|---|:---:|:---:|:---:|:---:|:---:|
| View materials & stock | ✓ | ✓ | ✓ | ✓ | ✓ |
| Add / edit materials | — | ✓ | — | — | ✓ |
| Record stock IN / OUT | — | ✓ | — | — | ✓ |
| Manual stock adjustment | — | ✓ | — | — | ✓ |
| Submit purchase request | ✓ | — | — | — | ✓ |
| Approve purchase request | — | — | ✓ | — | ✓ |
| Reject purchase request | — | — | ✓ | — | ✓ |
| Create purchase order | — | — | — | ✓ | ✓ |
| Receive purchase order | — | ✓ | — | ✓ | ✓ |
| Manage suppliers | — | — | — | ✓ | ✓ |
| Create & edit projects | — | — | ✓ | — | ✓ |
| View project details | ✓ | ✓ | ✓ | ✓ | ✓ |
| Send chat messages | ✓ | ✓ | ✓ | ✓ | ✓ |
| View reports | — | — | ✓ | ✓ | ✓ |
| Export PDF / Excel | — | — | ✓ | ✓ | ✓ |
| Manage team members | — | — | — | — | ✓ |
| View audit log | — | — | — | — | ✓ |
| Company settings | — | — | — | — | ✓ |

---

## 3. Module 1 — Materials & Inventory

### What It Does

Tracks every construction material the company uses. Stock levels are always calculated live from movement records — never stored as a fixed number. This ensures the stock level is always accurate and every change has a traceable history.

### Material Record

Each material stores:

| Field | Description | Example |
|---|---|---|
| Name | The material's full name | Hima Cement (50kg) |
| Code | Internal reference code | CEM-001 |
| Category | Grouping (Cement, Steel, etc.) | Cement & Concrete |
| Unit | How it is measured | Bag, Ton, KG, Litre, Piece, Metre, SQM, CBM |
| Unit Price | Cost per unit in UGX | 32,000 |
| Min Stock Level | Alert threshold | 50 |
| Current Stock | Calculated live from movements | 143 |
| Stock Value | Current stock × unit price | UGX 4,576,000 |
| Status | Active or inactive | Active |

### How Stock Is Calculated

```
Current Stock = (Total IN + Total Adjustment IN)
              − (Total OUT + Total Adjustment OUT)
```

This calculation runs fresh every time the stock level is displayed. The number is never stored — it is always derived from the full history of movements.

**Why this matters:**
- You can never have a wrong number
- You can see the stock on any date in the past
- Every discrepancy is traceable to a specific movement
- Auditors and managers can verify every figure

### Low Stock Detection

Every material has a minimum stock level. When current stock falls at or below that level:

1. The material is highlighted red on the materials list
2. A low stock alert fires to storekeepers, project managers, and admins
3. The dashboard low stock counter increments
4. Celery checks all materials every hour automatically

### Pre-Loaded Uganda Materials

New companies start with these materials pre-loaded:

| Material | Unit | Unit Price (UGX) | Min Level |
|---|---|---|---|
| Hima Cement (50kg) | Bag | 32,000 | 50 bags |
| Tororo Cement (50kg) | Bag | 30,000 | 50 bags |
| Iron Bars Y12 | Ton | 3,200,000 | 2 tons |
| Iron Bars Y16 | Ton | 3,400,000 | 2 tons |
| Murram | CBM | 45,000 | 10 cbm |
| Hardcore | CBM | 55,000 | 10 cbm |
| River Sand | CBM | 70,000 | 5 cbm |
| Timber 2x4 | Piece | 8,000 | 20 pieces |
| Iron Sheets (28g) | Piece | 45,000 | 10 sheets |
| Ceramic Tiles 30×30 | SQM | 35,000 | 20 sqm |

### Material Categories

| Category | Examples |
|---|---|
| Cement & Concrete | All cement types, concrete mix |
| Steel & Metal | Iron bars, binding wire, bolts |
| Aggregates | Murram, hardcore, river sand, ballast |
| Timber & Wood | Timber planks, plywood, hardboard |
| Roofing | Iron sheets, ridge caps, gutters |
| Finishes | Tiles, paint, plaster, floor screeds |
| Plumbing | Pipes, fittings, valves |
| Electrical | Cables, conduit, switch boxes |

### What Users Can Do

- **Add material** — name, code, category, unit, price, minimum level
- **Edit material** — update any field, changes take effect immediately
- **Deactivate material** — soft delete; history is preserved, just hidden from active lists
- **Search & filter** — by name, code, category, or low stock status
- **View detail** — full movement history, current stock, stock value

---

## 4. Module 2 — Stock Movements & Warehouse

### What It Does

Records every single change to inventory. This is the most used module in the system — storekeepers interact with it multiple times every day.

### Movement Types

| Type | Code | When to Use |
|---|---|---|
| Stock In | `IN` | Materials received from a supplier |
| Stock Out | `OUT` | Materials issued to a project site |
| Adjustment In | `ADJUST_IN` | Correcting stock upward — e.g. items found in stocktake |
| Adjustment Out | `ADJUST_OUT` | Correcting stock downward — e.g. damaged or written-off items |

### Movement Sources

| Source | When It Applies |
|---|---|
| Supplier Delivery | Goods arrived from a supplier, usually from a delivered PO |
| Internal Transfer | Materials moved from one site to another |
| Site Return | Unused materials returned from site back to the main store |
| Manual Adjustment | Admin or Storekeeper correction with a written reason |

### What Each Movement Records

| Field | Description |
|---|---|
| Material | Which material moved |
| Movement Type | IN / OUT / ADJUST_IN / ADJUST_OUT |
| Source | Why it moved |
| Quantity | How many units |
| Unit Price | Price per unit at time of movement (UGX) |
| Total Value | Quantity × Unit Price |
| Date | When it happened |
| Project | Which project it was for (optional) |
| Notes | Any additional context |
| Recorded By | Which user recorded it |
| Linked PO | Which Purchase Order triggered this (if applicable) |

### How Goods Receipt Works

When a Purchase Order is marked as Received:

1. The system automatically creates a `StockMovement (IN)` for every item in the PO
2. Quantity is taken directly from the PO item quantities
3. Unit price is taken from the PO item prices
4. The movement is linked back to the PO for traceability
5. Stock levels update immediately
6. A low-stock check fires automatically
7. The dashboard updates live for all users

This means the storekeeper never has to manually enter received quantities from a PO. The system does it automatically when the PO is received.

### Manual Adjustments

Sometimes the physical count does not match the system count. The storekeeper can record a manual adjustment:

- **Adjustment In** — physical count is higher than system (items were found)
- **Adjustment Out** — physical count is lower than system (items are missing or damaged)

Every adjustment requires a written reason. This creates a clear audit trail and prevents silent manipulation of stock figures.

### Stock Movement List

The movement list shows all movements with filters for:
- Material
- Movement type
- Date range
- Project

---

## 5. Module 3 — Projects

### What It Does

Tracks construction projects (sites). Each project has a budget, a manager, a location, and a timeline. Material usage is tracked per project so managers know exactly what each site is consuming and what it is costing.

### Project Record

| Field | Description |
|---|---|
| Name | Project name — e.g. "Ntinda Apartments Phase 2" |
| Code | Internal reference — e.g. "NTA-002" |
| Client | The client who commissioned the project |
| Location | Physical site address |
| Budget | Approved project budget in UGX |
| Status | Planning / Active / On Hold / Completed / Cancelled |
| Manager | The Project Manager assigned to this project |
| Start Date | When construction begins |
| End Date | Expected completion date |
| Description | Any additional notes |

### Project Statuses

| Status | What It Means |
|---|---|
| Planning | Project is being set up, not yet active |
| Active | Construction is currently underway |
| On Hold | Temporarily paused |
| Completed | Construction finished |
| Cancelled | Project cancelled |

### What Projects Track Automatically

**Material Cost vs Budget:**

```
Material Cost = SUM of all StockMovements (OUT) linked to this project
                × unit price at time of movement
```

The system shows:
- Total budget
- Total material cost so far
- Remaining budget
- Cost per material category

**Purchase Request History:**
Every PR raised for a project is listed on the project detail page, including status and who raised it.

**Stock Movement History:**
Every material that moved for this project — IN or OUT — is listed chronologically.

### Project Chat

Every project automatically gets its own team chat room. Anyone with access to the project can message the team directly inside the app. Chat history is preserved indefinitely.

---

## 6. Module 4 — Suppliers

### What It Does

Maintains a directory of all suppliers the company buys materials from. Links suppliers to Purchase Orders for full procurement traceability.

### Supplier Record

| Field | Description |
|---|---|
| Name | Company name — e.g. "Roofings Uganda Ltd" |
| Contact Person | The representative you deal with |
| Phone | Primary contact number |
| Email | Email address |
| Address | Physical or postal address |
| Rating | 1–5 stars based on reliability and quality |
| Notes | Any internal notes about this supplier |
| Active | Whether this supplier is still used |

### Supplier Rating Guide

| Stars | Meaning |
|---|---|
| ⭐ | Poor — unreliable, avoid if possible |
| ⭐⭐ | Below average — use only when necessary |
| ⭐⭐⭐ | Average — acceptable |
| ⭐⭐⭐⭐ | Good — reliable, recommend using |
| ⭐⭐⭐⭐⭐ | Excellent — preferred supplier |

### How Suppliers Connect to Procurement

When a Procurement Officer creates a Purchase Order, they select the supplier from this directory. The supplier's name, contact, and address flow through to the PO automatically. The PO PDF that is generated is ready to send to the supplier directly.

---

## 7. Module 5 — Procurement (PR → PO Workflow)

### Overview

The procurement module manages the full cycle from a site engineer realising materials are needed to those materials arriving at the store and stock being updated. Every step is tracked, every approval is recorded, and every notification is automatic.

### The 4 Stages

```
Stage 1: PURCHASE REQUEST
         Submitted by Site Engineer or Storekeeper
                    ↓
Stage 2: APPROVAL
         Reviewed by Project Manager
                    ↓
Stage 3: PURCHASE ORDER
         Created by Procurement Officer
                    ↓
Stage 4: GOODS RECEIVED
         Confirmed by Storekeeper or Procurement Officer
         → Stock updates automatically
```

---

### Stage 1 — Purchase Request (PR)

**Who creates it:** Site Engineer or Storekeeper  
**When:** When materials are needed or running low on site

**What a PR contains:**

| Field | Description |
|---|---|
| Title | Brief description — e.g. "Cement for Foundation Work" |
| Project | Which project needs the materials |
| Priority | Low / Normal / High / Urgent |
| Required By | When the materials are needed on site |
| Notes | Any additional context for the approver |
| Items | One or more materials with quantity required |

**PR Statuses:**

| Status | Meaning |
|---|---|
| Pending | Submitted, waiting for manager review |
| Approved | Manager approved, ready for PO creation |
| Rejected | Manager rejected with reason |
| PO Created | Procurement Officer has created a Purchase Order |

**What happens automatically when a PR is submitted:**
- PR is saved with status `PENDING`
- Live notification sent to all Project Managers and Admins instantly (WebSocket)
- Dashboard pending count increments for all users watching
- Audit log entry created

**PR Items:**

Each PR can have multiple line items:

| Field | Description |
|---|---|
| Material | Which material is needed |
| Quantity | How much is required |
| Estimated Cost | Calculated automatically from material unit price |
| Notes | Any specific notes for this item |

---

### Stage 2 — Approval

**Who acts:** Project Manager or Admin

**What the manager sees:**
- PR reference number
- Who submitted it and when
- Which project it is for
- Priority level and required-by date
- List of all items requested with estimated costs
- Current stock level for each item requested (so they can see if it is genuinely needed)
- Total estimated cost of the request

**Actions available:**

**Approve:**
- PR status changes to `APPROVED`
- Requester notified live (WebSocket notification)
- All Procurement Officers notified live: "PR ready for PO creation"
- Dashboard updates for all users
- Audit log entry created

**Reject:**
- Manager must write a rejection reason
- PR status changes to `REJECTED`
- Requester notified live with the rejection reason
- Dashboard updates
- Audit log entry created

---

### Stage 3 — Purchase Order (PO)

**Who creates it:** Procurement Officer  
**When:** After a PR is approved

**Creating a PO from an Approved PR:**
- Procurement Officer opens the approved PR
- Clicks "Create Purchase Order"
- PR items are pre-filled into the PO automatically
- Officer selects the supplier
- Officer confirms quantities and unit prices
- Sets expected delivery date
- Saves the PO

**What a PO contains:**

| Field | Description |
|---|---|
| Reference | Auto-generated — e.g. PO-0012 |
| Linked PR | The approved PR this PO was created from |
| Supplier | Who the materials are being ordered from |
| Project | Which project the materials are for |
| Created By | Which Procurement Officer created it |
| Expected Delivery | When the supplier should deliver |
| Delivery Address | Where to deliver |
| Notes | Any instructions for the supplier |
| Items | Materials, quantities, and unit prices |
| Total Value | Calculated automatically |

**PO Statuses:**

| Status | Meaning |
|---|---|
| Draft | Being prepared, not yet confirmed |
| Pending | Confirmed but order not yet placed with supplier |
| Ordered | Order has been placed with the supplier |
| Partially Received | Some items delivered, others still outstanding |
| Fully Received | All items delivered and stock updated |
| Cancelled | Order cancelled |

**PO PDF:**
Every PO can be exported as a professional PDF document showing the company name, supplier details, all line items with prices, and total value. This PDF can be printed or emailed directly to the supplier.

---

### Stage 4 — Goods Received

**Who acts:** Storekeeper or Procurement Officer  
**When:** Supplier delivers the goods to site

**What happens when "Mark as Received" is clicked:**

1. PO status changes to `FULLY RECEIVED`
2. For every item in the PO, a `StockMovement (IN)` is created automatically:
   - Material = PO item material
   - Quantity = PO item quantity ordered
   - Unit Price = PO item unit price
   - Source = Supplier Delivery
   - Linked PO = this PO
3. Stock levels update immediately for all affected materials
4. A low-stock check fires for all materials in the company
5. Dashboard updates live for all users watching
6. Confirmation notification sent to the user who received
7. Audit log entry created

**The key point:** The storekeeper does not manually enter quantities when receiving. The system creates the stock movements automatically from the PO. One click, everything updated.

---

### Procurement Reference Numbers

| Document | Format | Example |
|---|---|---|
| Purchase Request | PR-XXXX | PR-0042 |
| Purchase Order | PO-XXXX | PO-0017 |

---

### Complete PR → PO Example

```
Monday 8:00 AM
  Site Engineer (John) notices cement is low on site.
  John opens app → New Purchase Request
  Title: "Cement for Block A Foundation"
  Project: Ntinda Apartments
  Priority: High
  Required By: Wednesday
  Items: 150 bags Hima Cement
  → Submits

Monday 8:01 AM
  Project Manager (Sarah) gets live notification on her screen.
  "New PR from John — 150 bags cement, High priority"

Monday 8:30 AM
  Sarah opens the PR. Checks current stock: 23 bags.
  Checks project budget: UGX 12M remaining. Cost: UGX 4.8M.
  Sarah clicks Approve.
  John gets notification: "PR-0042 Approved ✓"
  Procurement Officer (David) gets notification: "PR-0042 ready for PO"

Monday 9:00 AM
  David opens PR-0042. Clicks "Create Purchase Order"
  Selects supplier: Roofings Uganda (★★★★★)
  Confirms: 150 bags × UGX 32,000 = UGX 4,800,000
  Expected delivery: Wednesday
  Saves PO-0017.
  PR status updates to "PO Created"

Wednesday 10:00 AM
  Roofings Uganda truck arrives at site.
  Storekeeper (Paul) verifies: 150 bags received.
  Paul opens PO-0017, clicks "Mark as Received"

Wednesday 10:01 AM
  System automatically:
  - Creates StockMovement: 150 bags Hima Cement IN
  - Stock updates: 23 + 150 = 173 bags
  - Low stock alert clears
  - Dashboard updates for everyone
  - Audit log records: Paul received PO-0017
```

---

## 8. Module 6 — Messaging & Team Chat

### What It Does

Every project has its own dedicated team chat room. Team members send messages, share updates, and coordinate directly inside the app — linked to the project they are working on. No need for WhatsApp groups that lose context.

### How Chat Works

**One room per project:**
When a project is created, a chat room is automatically created for it. Everyone who needs to communicate about that project uses that room.

**Real-time delivery:**
Messages are delivered instantly to everyone in the room using WebSockets. There is no need to refresh the page. If a new message arrives while you are reading older messages, it appears at the bottom of the chat immediately.

**Message history:**
When a user opens a project chat, the last 30 messages load automatically. Scroll up to see older messages.

**Who can chat:**
Any user with access to the project — Site Engineers, Storekeepers, Project Managers, Procurement Officers, Admins.

**Join and leave notifications:**
When a user connects to a chat room, a system message appears: "Sarah joined the room." When they leave: "Sarah left the room." This helps the team know who is currently active.

### Chat Room Features

| Feature | Description |
|---|---|
| Real-time messages | Delivered instantly via WebSocket |
| Message history | Last 30 messages load on connect |
| Sender name & avatar | Every message shows who sent it |
| Timestamps | Every message shows the time it was sent |
| System messages | Join/leave notifications |
| Send with Enter key | Press Enter to send, Shift+Enter for new line |
| Mobile-friendly | Works on any phone browser |

### Message Record

Each message stores:

| Field | Value |
|---|---|
| Room | Which project chat room |
| Sender | Which user sent it |
| Content | The message text |
| Is System Message | Whether it is a join/leave notification |
| Timestamp | When it was sent |

### Chat in the Interface

The chat interface sits inside the project detail page. Users can:
- See the full project information on the left
- Chat with the project team on the right
- Navigate to other parts of the app and return to the same conversation

### WebSocket Chat Flow

```
User types message → Presses Enter
        ↓
Browser sends message via WebSocket to server
        ↓
Server saves message to database
        ↓
Server broadcasts message to all users in the room
        ↓
All connected browsers receive and display the message instantly
```

---

## 9. Module 7 — Notifications

### What It Does

Delivers real-time alerts to users the moment something relevant happens. No email delays, no need to refresh — notifications arrive as a popup on screen the instant the event occurs.

### Notification Types

| Type | Who Gets It | When It Fires |
|---|---|---|
| Low Stock Alert | Storekeepers, Project Managers, Admins | Any material falls at or below its minimum level |
| PR Submitted | Project Managers, Admins | Site Engineer submits a purchase request |
| PR Approved | Requester, Procurement Officers | Manager approves a purchase request |
| PR Rejected | Requester | Manager rejects a purchase request (with reason) |
| PO Created | Procurement Officer (confirmation) | A new purchase order is created |
| PO Received | Relevant team | A purchase order is marked as received |
| System | Any user | Admin broadcasts a system-wide message |

### Notification Levels

| Level | Colour | When Used |
|---|---|---|
| Info | Blue | Informational — e.g. PR submitted |
| Success | Green | Positive outcome — e.g. PR approved |
| Warning | Orange | Needs attention — e.g. low stock |
| Danger | Red | Urgent — e.g. PR rejected, critical stock |

### How Notifications Work

**Live delivery (WebSocket):**
When an event fires, the notification is pushed instantly to the relevant user's screen. A popup appears at the bottom-right corner and fades after 5 seconds. The bell icon in the top bar shows a red badge with the unread count.

**Notification bell dropdown:**
Clicking the bell icon shows the 5 most recent unread notifications. Each notification shows:
- Title
- Message
- Time ago (e.g. "3 minutes ago")
- A link to the relevant page

**Mark as read:**
- Click "Mark all read" to clear the badge
- Individual notifications marked read when clicked

**Persistence:**
Notifications are saved to the database. If a user is offline when a notification fires, it waits for them. When they log in, it appears in their notification bell.

### Low Stock Check Schedule

The system checks all materials every hour using a background task:

```
Every 60 minutes:
  For each company:
    For each active material:
      If current_stock <= min_stock_level:
        Create notification
        Push to all storekeepers, project managers, and admins
        in that company via WebSocket
```

---

## 10. Module 8 — Dashboard

### What It Does

The first thing every user sees when they log in. Shows the most important numbers for the company at a glance. All values update live in real time whenever stock, procurement, or project data changes.

### KPI Cards (Top Row)

| Card | What It Shows | Updates When |
|---|---|---|
| Total Materials | Count of active materials | Material added or deactivated |
| Active Projects | Projects with status = Active | Project status changes |
| Low Stock Alerts | Materials at or below minimum | Any stock movement |
| Pending Requests | PRs awaiting manager approval | PR submitted or decided |
| Stock In Today | Total quantity received today | Any IN movement today |
| Inventory Value | Total value of all stock at current prices | Any movement or price change |

### Charts

**Bar Chart — Material Stock Levels:**
Shows the top 10 materials by current stock quantity. Materials below their minimum are shown in red. Materials with healthy stock are shown in blue. Updates when the WebSocket sends a dashboard refresh.

**Line Chart — 7-Day Stock Movement Trend:**
Two lines: Stock IN (green) and Stock OUT (red). Shows the last 7 days. Helps managers see whether inventory is growing or depleting across the week.

### Low Stock Alerts Table

Shows all materials currently below minimum level with:
- Material name
- Current stock
- Minimum level
- Quick "Request" button that opens a pre-filled PR form

### Recent Movements Table

Shows the last 8 stock movements:
- Material
- Movement type (badge)
- Quantity
- Date

This table updates live via WebSocket when new movements are recorded.

### Real-Time Behaviour

The dashboard is connected to a live WebSocket channel for the company. When any user records a stock movement, approves a PR, or receives a PO — every other user who has the dashboard open sees the numbers change immediately. No refresh needed.

---

## 11. Module 9 — Reports & Exports

### What It Does

Provides three built-in reports that can be viewed in the browser and downloaded as formatted Excel files or PDFs. Export features are available on Basic and Pro plans only.

### Report 1 — Inventory Valuation Report

**What it shows:**
Every active material with current stock, unit price, total stock value, minimum level, and status. Low-stock items are highlighted in red.

**Summary figures:**
- Total number of materials
- Number of materials currently low on stock
- Total inventory value across all materials

**Export formats:**
- **Excel** — styled with coloured headers, low-stock rows in red, auto column widths, total row at the bottom
- **PDF** — branded with company name, print-ready layout, colour-coded

---

### Report 2 — Project Material Usage Report

**What it shows:**
All materials that went OUT linked to each project — quantity used, unit cost, total cost, and date. Filterable by project.

**Summary figures:**
- Total material cost across all projects
- Per-project breakdown

**Export formats:**
- **Excel** — filterable by project, total at the bottom

---

### Report 3 — Procurement Summary Report

**What it shows:**
All purchase orders with supplier, project, total value, status, and delivery dates.

**Summary figures:**
- Total procurement spend
- Orders by status

---

### Individual PO PDF

Every Purchase Order can be exported as a standalone professional PDF:
- Company name and details at the top
- Supplier name and contact
- PO reference number and date
- All line items with quantities and prices
- Grand total
- Notes and delivery address

This PDF is ready to print or email directly to the supplier.

---

### Plan Restrictions

| Feature | Free | Basic | Pro |
|---|:---:|:---:|:---:|
| View reports in browser | ✓ | ✓ | ✓ |
| Excel export | — | ✓ | ✓ |
| PDF export | — | ✓ | ✓ |
| Individual PO PDF | — | ✓ | ✓ |
| Advanced analytics | — | — | ✓ |

---

## 12. Module 10 — Analytics

### What It Does

Visual charts and trends that help managers understand patterns in stock usage and procurement activity. Available on Pro plan.

### Charts Available

**Chart 1 — Material Stock Levels (Bar Chart)**
Current stock for all materials. Red bars = below minimum. Blue bars = healthy. Helps storekeepers and managers instantly see which materials need attention.

**Chart 2 — 7-Day Stock Movement Trend (Line Chart)**
Stock IN vs Stock OUT over the past 7 days. Two lines. Helps managers see daily consumption rates and delivery patterns.

**Chart 3 — Project Material Usage Comparison (Bar Chart)**
Side-by-side comparison of total material spend across all active projects. Helps the company owner see which sites are consuming the most resources.

---

## 13. Complete Workflows End to End

### Workflow A — Daily Store Operations

```
7:00 AM  Storekeeper opens dashboard
         → Sees: 3 materials highlighted red (low stock)
         → Sees: 2 pending purchase requests from yesterday

7:15 AM  Cement delivery arrives from supplier
         Storekeeper opens Warehouse → Record Movement
         Material: Hima Cement
         Type: Stock IN
         Quantity: 200 bags
         Source: Supplier Delivery
         Saves

7:16 AM  Dashboard updates live for all users
         Cement stock jumps from 12 to 212
         Low stock alert for cement clears automatically
         Notification fires to all managers: "Stock received"

9:00 AM  Site foreman requests 30 bags for today's pour
         Storekeeper records: 30 bags OUT → Block A Foundation

9:30 AM  Repeat for timber: 25 pieces OUT → Block A Framework

5:00 PM  Storekeeper reviews daily movements
         Day summary: 200 bags IN, 30 bags cement + 25 pieces timber OUT
```

---

### Workflow B — Purchase Request Approval Chain

```
Site Engineer (John) — 8:00 AM
  Opens app on site. Dashboard shows cement is red (43 bags, min 50).
  New Purchase Request:
    Title: "Cement for Block B Foundation"
    Project: Ntinda Apartments Phase 2
    Priority: High
    Required By: Thursday
    Item 1: Hima Cement — 200 bags
    Item 2: River Sand — 5 cbm
  Submits.

System — 8:00 AM (automatic)
  Creates PR-0051 with status PENDING
  Sends live WebSocket notification to all Project Managers
  Increments "Pending Requests" on dashboard for all users

Project Manager (Sarah) — 8:05 AM
  Receives notification popup: "New PR from John — High priority"
  Opens PR-0051
  Reviews:
    - Cement: 43 bags in stock. Request: 200 bags. Justified ✓
    - Sand: 2 cbm in stock. Request: 5 cbm. Justified ✓
    - Estimated cost: UGX 7,750,000
    - Project budget remaining: UGX 28M. Fine ✓
  Clicks Approve.

System — 8:06 AM (automatic)
  PR-0051 status → APPROVED
  John gets notification: "PR-0051 Approved ✓"
  All Procurement Officers get notification: "PR-0051 ready for PO"
  Dashboard pending count drops from 3 to 2

Procurement Officer (David) — 8:30 AM
  Opens PR-0051. Clicks "Create Purchase Order"
  System pre-fills items from the PR
  David selects: Roofings Uganda (★★★★★)
  Confirms prices:
    200 bags cement × 32,000 = 6,400,000
    5 cbm sand × 70,000 = 350,000
    Total: UGX 6,750,000
  Expected delivery: Thursday
  Saves PO-0023.
  PR-0051 status → PO CREATED

Thursday 10:00 AM
  Roofings Uganda truck arrives.
  Storekeeper (Paul) verifies delivery:
    200 bags cement ✓
    5 cbm sand ✓
  Opens PO-0023. Clicks "Mark as Received"

System — Thursday 10:01 AM (automatic)
  Creates StockMovement: 200 bags Hima Cement IN (linked to PO-0023)
  Creates StockMovement: 5 cbm River Sand IN (linked to PO-0023)
  Cement: 43 + 200 = 243 bags ✓
  Sand: 2 + 5 = 7 cbm ✓
  Low stock alerts cleared for both materials
  Dashboard updates for all users
  PO-0023 status → FULLY RECEIVED
  Confirmation notification sent to Paul
```

---

### Workflow C — Team Chat During a Project Issue

```
Wednesday 2:00 PM — On site, Block A

Site Engineer (John) opens project chat for Ntinda Apartments:

John:     "We've run out of binding wire. Work stopped on 
           Block A columns. Need urgent delivery."

Storekeeper (Paul) sees message immediately:

Paul:     "Checking stock now... system shows 15 rolls. 
           Let me check the store physically."

Paul:     "Confirmed — only 3 rolls left. System is wrong. 
           Will log an adjustment now."

Project Manager (Sarah) joins the conversation:

Sarah:    "John — how much do you need to finish Block A?"
John:     "Minimum 50 rolls to complete all columns"
Sarah:    "David, can you raise an urgent PO directly? 
           I'll approve the PR right now."

Procurement Officer (David):
David:    "On it. Which supplier has stock today?"
Paul:     "Try Mukwano Enterprises — they delivered last week"

David:    "PO-0024 created for 60 rolls from Mukwano. 
           Delivery confirmed for 4 PM today."
Sarah:    "Thanks team. John — should resume by 5 PM."
John:     "Received. Will brief the foreman."

4:15 PM — Delivery arrives
Paul:     "60 rolls binding wire received. Stock updated. 
           Good to go John."
John:     "👍 Resuming now."
```

This entire conversation is preserved in the project chat forever, linked to the project. Anyone who joins the project later can read the full history and understand exactly what happened.

---

### Workflow D — Low Stock Alert to PR (Automated Path)

```
11:00 PM — Automated Celery task runs

  Checks all materials for Nile Construction Ltd:
  
  Cement: 47 bags — minimum 50. LOW ✗
  Iron Bars Y12: 1.8 tons — minimum 2. LOW ✗
  All other materials: OK ✓

  Creates notifications:
    → Paul (Storekeeper): "Low Stock: Cement — 47 bags (min 50)"
    → Paul (Storekeeper): "Low Stock: Iron Bars Y12 — 1.8 tons (min 2)"
    → Sarah (Project Manager): same two alerts
    → Admin: same two alerts

Next morning — 7:00 AM
  Paul opens app. Sees 2 red notification badges.
  Dashboard shows 2 low stock items highlighted red.
  
  Paul opens Cement alert → clicks "Request More"
  System opens New PR form pre-filled with:
    Material: Hima Cement
    Suggested Quantity: [empty — Paul fills in 200 bags]
  
  Paul submits PR-0052.
  Sarah approves at 7:15 AM.
  David creates PO-0025 at 7:30 AM.
```

---

## 14. Database Design

### The 12 Core Tables

#### Company
```
id          Primary key
name        Company name
slug        URL-safe identifier (unique)
plan        FREE / BASIC / PRO
is_active   Whether account is active
created_at  When registered
```

#### User
```
id            Primary key
company_id    FK → Company (isolates all data)
username      Login username
email         Email address
password      Bcrypt hashed — never stored plain
first_name    
last_name     
role          site_engineer / storekeeper / project_manager /
              procurement_officer / admin
phone         Contact number
is_active     
```

#### Material
```
id               Primary key
company_id       FK → Company
category_id      FK → Category (optional)
name             
code             Internal reference
unit             bag / ton / kg / litre / piece / metre / sqm / cbm
unit_price       UGX
min_stock_level  Alert threshold
description      
is_active        
```

#### Category
```
id          Primary key
company_id  FK → Company
name        Category name
```

#### StockMovement ⭐
```
id               Primary key
company_id       FK → Company
material_id      FK → Material
project_id       FK → Project (optional)
movement_type    IN / OUT / ADJUST_IN / ADJUST_OUT
source           SUPPLIER / INTERNAL / SITE / ADJUSTMENT
quantity         
unit_price       UGX at time of movement
date             
notes            
created_by_id    FK → User
purchase_order_id FK → PurchaseOrder (optional)
created_at       
```

#### Project
```
id           Primary key
company_id   FK → Company
name         
code         
client       
location     
description  
budget       UGX
status       planning / active / on_hold / completed / cancelled
manager_id   FK → User
start_date   
end_date     
```

#### Supplier
```
id             Primary key
company_id     FK → Company
name           
contact_person 
phone          
email          
address        
rating         1-5
notes          
is_active      
```

#### PurchaseRequest
```
id                Primary key
company_id        FK → Company
project_id        FK → Project
requested_by_id   FK → User
approved_by_id    FK → User (null until decided)
status            PENDING / APPROVED / REJECTED / PO_CREATED
priority          LOW / NORMAL / HIGH / URGENT
title             
notes             
rejection_reason  
required_by_date  
approved_at       
created_at        
```

#### PurchaseRequestItem
```
id                   Primary key
purchase_request_id  FK → PurchaseRequest
material_id          FK → Material
quantity             
notes                
```

#### PurchaseOrder
```
id                   Primary key
company_id           FK → Company
purchase_request_id  FK → PurchaseRequest (optional)
supplier_id          FK → Supplier
project_id           FK → Project
created_by_id        FK → User
status               DRAFT / PENDING / ORDERED / PARTIAL / RECEIVED / CANCELLED
expected_delivery_date
actual_delivery_date 
delivery_address     
notes                
created_at           
```

#### PurchaseOrderItem
```
id                   Primary key
purchase_order_id    FK → PurchaseOrder
material_id          FK → Material
quantity_ordered     
quantity_received    
unit_price           UGX
notes                
```

#### Notification
```
id                Primary key
company_id        FK → Company
recipient_id      FK → User
notification_type low_stock / pr_submitted / pr_approved / pr_rejected /
                  po_created / po_received / system
level             info / warning / success / danger
title             
message           
link              URL to relevant page
is_read           
created_at        
```

#### ChatRoom
```
id          Primary key
company_id  FK → Company
project_id  OneToOne → Project
created_at  
```

#### ChatMessage
```
id                  Primary key
room_id             FK → ChatRoom
sender_id           FK → User
content             
is_system_message   
created_at          
```

#### AuditLog
```
id           Primary key
company_id   FK → Company
user_id      FK → User
action       CREATE / UPDATE / DELETE / APPROVE / REJECT / LOGIN
model_name   Which model was affected
object_id    Which record was affected
description  Human-readable description of what happened
timestamp    
ip_address   
```

### The Stock Calculation Rule

```python
# Current stock is ALWAYS computed, NEVER stored
current_stock = (
    StockMovement.objects
    .filter(material=material,
            movement_type__in=['IN', 'ADJUST_IN'])
    .aggregate(total=Sum('quantity'))['total'] or 0
) - (
    StockMovement.objects
    .filter(material=material,
            movement_type__in=['OUT', 'ADJUST_OUT'])
    .aggregate(total=Sum('quantity'))['total'] or 0
)
```

---

## 15. System Architecture

### Overview

The system is a Django monolith handling HTTP, WebSockets, background tasks, notifications, and the API — all from one well-structured codebase. This is the right architecture for launch through to hundreds of companies.

```
┌─────────────────────────────────────────────────────────────┐
│              USERS (Browser / Mobile Browser)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS + WSS
┌──────────────────────────▼──────────────────────────────────┐
│                         NGINX                               │
│              Reverse Proxy & SSL Termination                │
│   • Terminates HTTPS/WSS                                    │
│   • Serves static files (CSS, JS, images)                   │
│   • Routes HTTP → Daphne                                    │
│   • Routes WebSocket → Daphne                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                        DAPHNE                               │
│               ASGI Server (HTTP + WebSocket)                │
│   • Single server handles both HTTP and WS connections      │
│   • Runs multiple workers for concurrency                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                        DJANGO                               │
│                   Application Core                          │
│                                                             │
│  HTTP requests → Views → Templates → Response               │
│  WS connections → Channels Consumers → Redis → Broadcast    │
│                                                             │
│  Apps:                                                      │
│  accounts │ materials │ projects │ procurement              │
│  suppliers │ warehouse │ notifications │ chat               │
│  dashboard │ reports │ analytics                            │
└──────┬───────────────────────────────────────┬──────────────┘
       │                                       │
┌──────▼──────────────────┐   ┌───────────────▼──────────────┐
│      POSTGRESQL         │   │            REDIS             │
│                         │   │                              │
│  All persistent data    │   │  Channel layers (WebSocket   │
│  Users, materials,      │   │  message routing)            │
│  movements, PRs, POs,   │   │  Celery task broker          │
│  chat, notifications,   │   │  (background jobs)           │
│  audit log              │   │                              │
│  Backed up nightly      │   │  In-memory — fast            │
└─────────────────────────┘   └──────────────────────────────┘
                                           │
                           ┌───────────────▼──────────────────┐
                           │          CELERY WORKERS          │
                           │                                  │
                           │  Background tasks:               │
                           │  • Hourly low-stock check        │
                           │  • Send notifications async      │
                           │  • Heavy report generation       │
                           │                                  │
                           │  Celery Beat:                    │
                           │  • Schedules periodic tasks      │
                           └──────────────────────────────────┘
```

### App Structure

```
construction_saas/
├── config/
│   ├── settings.py          Django configuration
│   ├── urls.py              Main URL routing
│   ├── asgi.py              WebSocket + HTTP entry point
│   └── celery.py            Background task config
├── apps/
│   ├── accounts/            Users, roles, company, auth, audit
│   ├── materials/           Materials, categories, stock calc
│   ├── projects/            Projects, budget tracking
│   ├── suppliers/           Supplier directory
│   ├── warehouse/           Stock movements, goods receipt
│   ├── procurement/         PRs, POs, approval workflow
│   ├── notifications/       Alerts, WebSocket consumer
│   ├── chat/                Project chat, WebSocket consumer
│   ├── dashboard/           KPIs, live dashboard consumer
│   ├── reports/             Reports and exports
│   └── analytics/           Charts and analytics
├── templates/               HTML templates (Bootstrap 5)
└── static/                  CSS, JS, WebSocket client
```

---

## 16. Real-Time Features (WebSockets)

Three WebSocket connections run simultaneously for every logged-in user.

### Channel 1 — Notifications

**Connection:** `ws://host/ws/notifications/`  
**Group:** `notify_user_{user_id}` (personal channel per user)

**What it delivers:**
- Low stock alerts
- PR submitted / approved / rejected
- PO created / received
- System announcements

**On connect:** Sends unread notification count immediately  
**From browser:** Can send `mark_read` or `mark_all_read` actions  
**From server:** Any part of the app calls `send_notification_task.delay(user_id, ...)` to push a live alert

---

### Channel 2 — Dashboard

**Connection:** `ws://host/ws/dashboard/`  
**Group:** `dashboard_company_{company_id}` (shared by all users in the company)

**What it delivers:**
- Updated KPI values (materials, projects, low stock count, pending PRs, stock in/out today, inventory value)
- Updated recent movements table

**When it fires:** Any time a stock movement is recorded, a PR is approved, or a PO is received — `DashboardConsumer.push_update(company_id)` is called and every user on the dashboard gets fresh numbers.

---

### Channel 3 — Project Chat

**Connection:** `ws://host/ws/chat/{project_id}/`  
**Group:** `chat_project_{project_id}`

**What it delivers:**
- New chat messages from any team member
- System messages (join/leave)
- Full message history (last 30) on connect

**Security:** User is verified to belong to the correct company before connection is accepted.

---

### WebSocket JavaScript Client

The `websockets.js` file runs on every page after login and manages all three connections automatically:

- **Auto-reconnect** — if connection drops, it reconnects every 3-4 seconds
- **Toast notifications** — new notifications appear as colour-coded popups
- **KPI flash** — dashboard numbers flash yellow when they update live
- **Chat send** — Enter key sends message, Shift+Enter for new line

---

## 17. Security & Access Control

### Three Layers of Protection

**Layer 1 — Authentication (Are you logged in?)**
Every URL requires login. Django's `@login_required` decorator and `LoginRequiredMixin` on every view. Unauthenticated requests are redirected to the login page.

**Layer 2 — Company Isolation (Is this your data?)**
Middleware attaches `request.company` on every request. All database queries filter by `company_id`. It is structurally impossible for a user to access another company's data.

```python
# Runs on every single request
class CompanyIsolationMiddleware:
    def __call__(self, request):
        if request.user.is_authenticated:
            request.company = request.user.company
            # Block inactive companies
            if not request.company.is_active:
                return redirect('login')
        return self.get_response(request)
```

**Layer 3 — Role Checks (Are you allowed to do this?)**
Every sensitive view has a role decorator. Blocked at the server — not just hidden in the UI.

```python
# Procurement view — only procurement officer or admin
@procurement_required
def create_purchase_order(request):
    ...

# PR approval — only project manager or admin
@manager_required
def approve_request(request, pk):
    ...
```

### Additional Security

| Measure | How |
|---|---|
| HTTPS | Let's Encrypt SSL on Nginx, auto-renewing |
| Password hashing | Django bcrypt — passwords never stored plain |
| CSRF protection | Django CSRF tokens on all forms |
| Rate limiting | Nginx: 5 login attempts per minute per IP |
| Audit logging | Every important action logged with user + timestamp |
| Session security | `SESSION_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` in production |

### Audit Log

Every significant action is recorded permanently:

| What gets logged | Example |
|---|---|
| User login | "admin logged in from 41.210.x.x" |
| Material created | "Storekeeper Paul created 'Bamboo Poles'" |
| Stock movement | "Paul recorded: 200 bags Hima Cement IN" |
| PR submitted | "John submitted PR-0051 for Project Ntinda" |
| PR approved | "Sarah approved PR-0051" |
| PR rejected | "Sarah rejected PR-0052: budget exhausted" |
| PO created | "David created PO-0023 for Roofings Uganda" |
| PO received | "Paul marked PO-0023 as received" |
| User invited | "Admin invited driver@nile.co as Storekeeper" |

Audit logs cannot be edited or deleted by anyone.

---

## 18. SaaS & Multi-Company Structure

### How Multi-Tenancy Works

Every model in the system has a `company_id` foreign key. Every database query includes a `WHERE company_id = X` filter. This happens automatically through the middleware — developers cannot forget to add it because it is enforced at the request level.

```
Company A (Nile Construction Ltd)
  └── Users: Sarah, Paul, John, David
  └── Materials: Cement, Iron Bars...
  └── Projects: Ntinda Phase 2, Jinja Road
  └── Stock Movements: [Company A's movements only]

Company B (Kampala Builders Ltd)
  └── Users: Maria, James, Peter
  └── Materials: [Completely separate list]
  └── Projects: [Completely separate projects]
  └── Stock Movements: [No overlap with Company A]
```

### Subscription Plans

| Feature | Free | Basic (UGX 150,000/mo) | Pro (UGX 400,000/mo) |
|---|:---:|:---:|:---:|
| Max users | 3 | 10 | Unlimited |
| Max projects | 2 | 10 | Unlimited |
| All core modules | ✓ | ✓ | ✓ |
| Real-time WebSockets | ✓ | ✓ | ✓ |
| Project chat | ✓ | ✓ | ✓ |
| Excel exports | — | ✓ | ✓ |
| PDF exports | — | ✓ | ✓ |
| Advanced analytics | — | — | ✓ |
| API access | — | — | ✓ |
| Priority support | — | — | ✓ |

### Company Registration Flow

```
1. Company owner visits /accounts/register/
2. Fills in: Company name + Admin account details
3. System creates:
   - Company record with FREE plan
   - Admin user linked to that company
   - Auto-generates company slug
4. Admin logs in → sees empty dashboard
5. Admin adds materials, creates projects, invites team
6. Team members receive invite link and set their passwords
```

---

## 19. Tech Stack

```
Language:          Python 3.12
Web Framework:     Django 4.2
Real-time:         Django Channels 4.0 (WebSockets)
ASGI Server:       Daphne 4.0
Web Server:        Nginx (reverse proxy + SSL)
Database:          PostgreSQL 15
Cache & Broker:    Redis 7
Background Tasks:  Celery 5.3 + Celery Beat
Frontend:          Django Templates + Bootstrap 5 + Chart.js
Forms:             django-crispy-forms + crispy-bootstrap5
Excel Exports:     openpyxl 3.1
PDF Exports:       ReportLab 4.1
REST API:          Django REST Framework 3.14
API Auth:          djangorestframework-simplejwt
Environment:       python-decouple
Error Tracking:    Sentry (free tier)
Server:            Hetzner Cloud (Ubuntu 24)
```

### What We Deliberately Did Not Add

| Technology | Reason Not Included |
|---|---|
| React / Vue | Django templates are sufficient for this complexity level at launch |
| Docker | Adds complexity with no benefit at this scale |
| Kubernetes | Wildly premature for a startup |
| GraphQL | REST is sufficient; GraphQL adds unnecessary complexity |
| Microservices | Monolith is the right architecture until you have scale problems |

---

## 20. URL Structure

### Authentication
```
/accounts/login/           Login page
/accounts/logout/          Logout
/accounts/register/        Company registration
/accounts/profile/         User profile
/accounts/team/            Manage team members
/accounts/team/invite/     Invite a new user
/accounts/audit-log/       Audit log (Admin only)
```

### Dashboard
```
/dashboard/                Main dashboard (live KPIs + charts)
```

### Materials
```
/materials/                Materials list
/materials/create/         Add new material
/materials/{id}/           Material detail + movement history
/materials/{id}/edit/      Edit material
/materials/{id}/delete/    Deactivate material
```

### Stock Movements
```
/warehouse/                Movement list
/warehouse/create/         Record new movement
/warehouse/adjust/         Manual stock adjustment
/warehouse/{id}/           Movement detail
```

### Projects
```
/projects/                 Project list
/projects/create/          Create new project
/projects/{id}/            Project detail + chat + movements
/projects/{id}/edit/       Edit project
```

### Suppliers
```
/suppliers/                Supplier list
/suppliers/create/         Add supplier
/suppliers/{id}/edit/      Edit supplier
```

### Procurement
```
/procurement/requests/                  PR list
/procurement/requests/create/           Submit PR
/procurement/requests/{id}/             PR detail
/procurement/requests/{id}/approve/     Approve PR
/procurement/requests/{id}/reject/      Reject PR
/procurement/orders/                    PO list
/procurement/orders/create/             Create PO
/procurement/orders/create/{pr_id}/     Create PO from PR
/procurement/orders/{id}/               PO detail
/procurement/orders/{id}/receive/       Mark PO as received
```

### Reports
```
/reports/                              Reports index
/reports/inventory/                    Inventory valuation
/reports/project-usage/               Project usage
/reports/procurement/                  Procurement summary
/reports/export/inventory/excel/       Download Excel
/reports/export/inventory/pdf/         Download PDF
/reports/export/project-usage/excel/   Download Excel
/reports/export/po/{id}/pdf/           Download PO PDF
```

### Analytics
```
/analytics/                            Analytics dashboard
```

### Notifications
```
/notifications/                        Notification list
```

### WebSocket Endpoints
```
ws://host/ws/notifications/            Personal notification channel
ws://host/ws/dashboard/                Company dashboard channel
ws://host/ws/chat/{project_id}/        Project team chat
```

### REST API
```
POST   /api/token/                     Get JWT access token
GET    /api/materials/                 All materials + stock
GET    /api/materials/?low_stock=1     Low stock only
GET    /api/materials/{id}/            Single material
GET    /api/projects/                  All projects
GET    /api/stock/                     Recent movements
GET    /api/stock/summary/             Stock summary
GET    /api/stock/?days=7              Last 7 days
```

---

## Summary

| | |
|---|---|
| **Modules** | 10 |
| **User Roles** | 5 |
| **Database Tables** | 15 |
| **WebSocket Channels** | 3 |
| **URL Patterns** | 40+ |
| **Lines of Code** | ~7,000 |
| **Monthly Server Cost** | ~$50 at launch |
| **Break-even** | 1 Basic customer |

### The One-Sentence Description

> ConstructSaaS is a real-time construction management platform that connects every person in a construction company — from the site engineer requesting materials to the storekeeper receiving them — through a single structured, auditable, role-controlled system that always shows the right information to the right person at the right moment.

---

*ConstructSaaS — Built for Uganda's Construction Industry — 2025*
