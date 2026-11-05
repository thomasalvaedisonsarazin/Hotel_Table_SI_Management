# PRP: DineOps SI

> Implementation blueprint generated from INITIAL.md

| Field | Value |
|-------|-------|
| **Product** | DineOps SI |
| **Type** | SaaS |
| **Version** | 1.0 |
| **Created** | 2026-11-05 |
| **Complexity** | Medium for this phase; High once computer vision is added |

## Architecture

```
future vision worker ─┐
simulator (demo only) ├─► table engine ─► PostgreSQL
staff taps ───────────┘        │
                               └─► WebSocket hub ─► live floor board
```

All three inputs go through one state machine (`backend/app/services/table_engine.py`), so adding computer vision later needs no change to the board, alerts, waitlist or analytics.

## Table states

```
free ──guests seen for seat_confirm──► occupied
occupied ──no guests for vacate_confirm──► needs_cleaning
needs_cleaning ──staff present for clean_confirm, or tap──► free
needs_cleaning ──guests sit down──► occupied (cleaning assumed)
```

## Models

User, RefreshToken, Restaurant, DiningTable, TableSession, Alert, WaitlistEntry

## Phases

1. Foundation: models, migration, config, Docker, CI, Vite setup
2. Modules: auth, restaurants and floor setup, live floor and alerts, waitlist, analytics
3. Quality: pytest with 80%+ coverage, Vitest, security review, browser click-through

## Validation gates

| Gate | Commands |
|------|----------|
| 1 | `alembic upgrade head`, `npm install`, `docker compose config` |
| 2 | `ruff check backend/`, `mypy backend/app`, `npm run lint`, `npm run type-check` |
| 3 | `pytest --cov=app --cov-fail-under=80`, `npm test` |
| Final | `docker compose up -d`, `curl localhost:8000/health` |
