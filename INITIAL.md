# INITIAL.md - TableSense

> Live table management for restaurants: table status, service alerts, waitlist and staffing analytics.

---

## PRODUCT

**Name:** TableSense (working name, not yet checked for trademark or domain availability)

**Description:** Shows every table's status in real time (free, occupied, needs cleaning), alerts staff when guests have waited too long for a waiter or a table is waiting to be cleaned, helps the host see which table frees up next, and gives managers peak-hour and staffing analytics. For restaurant owners and floor managers.

**Type:** SaaS

**Scope now:** Restaurants only. Hotels come later.

**Reference:** Instagram reel by `risexventuress` describing AI table management on existing CCTV (caption only; the video did not load).

---

## TECH STACK

| Layer | Choice |
|-------|--------|
| Backend | FastAPI + Python |
| Frontend | React + TypeScript + Vite |
| Database | PostgreSQL |
| Auth | JWT (Google OAuth deferred until credentials exist) |
| UI | Tailwind + Framer Motion |
| Realtime | WebSockets |
| Payments | None |

---

## KEY DESIGN DECISION: NO CCTV FOOTAGE YET

Real footage is not available, so computer vision is **out of scope for this build**. Instead:

- A documented **ingest API** accepts per-table observations (`guest_count`, `staff_present`). A future vision worker only has to call this API.
- A **simulator** produces observations through the same engine, only for clearly labelled demo restaurants.
- **Staff can tap** to seat, serve, vacate and clean, so the product works with no camera at all.

Simulated data must never be presented as real.

---

## MODULES

### Module 1: Authentication (Built-in)

**Models:** User, RefreshToken

**Endpoints:** POST /auth/register, /auth/login, /auth/refresh, /auth/logout; GET /auth/me

**Pages:** /login, /register, /profile

### Module 2: Restaurants and Floor Setup

**Models:** Restaurant, DiningTable

**Endpoints:** CRUD for restaurants and tables, POST /restaurants/demo, POST /restaurants/{id}/api-key

**Pages:** /dashboard, /r/:id/setup, /r/:id/settings

### Module 3: Live Floor and Alerts

**Models:** TableSession, Alert

**Endpoints:** GET /restaurants/{id}/floor, POST table actions, alert list and acknowledge, POST /ingest/observations, WS /ws/restaurants/{id}, POST simulator toggle

**Pages:** /r/:id/floor, /r/:id/alerts

### Module 4: Waitlist

**Models:** WaitlistEntry

**Endpoints:** list, add, seat, leave. Next-free-table estimates come from each restaurant's own turn-time history.

**Pages:** panel on /r/:id/floor

### Module 5: Analytics

**Endpoints:** GET /restaurants/{id}/analytics?days=

**Pages:** /r/:id/analytics (peak-hour heatmap, turn time, response times, suggested waiters per shift)

---

## MVP SCOPE

Must Have:
- [ ] User registration and login
- [ ] Restaurants with a drag-and-drop floor plan
- [ ] Live board: free, occupied, needs cleaning, with seated timers
- [ ] Waiter alert (default 5 minutes) and cleaning alert
- [ ] Waitlist with next-free-table estimates
- [ ] Analytics: peak hours, footfall, staffing suggestion
- [ ] Ingest API, simulator and labelled demo restaurant

Later:
- Vision worker (needs footage), camera zone setup, staff accounts and roles, push or WhatsApp alerts, Google OAuth, billing, hotels

---

## ACCEPTANCE CRITERIA

- [ ] Users can register and log in, and cannot see other users' restaurants
- [ ] A passer-by does not mark a table occupied; a brief detection dropout does not end a session
- [ ] A waiter alert fires once after the threshold and resolves when staff attend
- [ ] A cleaning alert fires once and resolves when the table is cleaned
- [ ] The board updates live without a page refresh
- [ ] Demo data is labelled as simulated everywhere it appears
- [ ] 80%+ backend test coverage
- [ ] Docker builds successfully

---

## RUN

```bash
/generate-prp INITIAL.md
/execute-prp PRPs/tablesense-prp.md
```
