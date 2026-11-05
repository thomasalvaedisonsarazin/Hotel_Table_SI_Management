# CLAUDE.md - Project Rules

> Rules Claude follows in every conversation.

---

## This Product: DineOps SI

Live table management for restaurants. Hotels come later.

- All table changes go through `backend/app/services/table_engine.py`, whether they come from staff taps, the camera ingest API or the simulator.
- Simulated data must stay labelled. The simulator only runs on restaurants with `is_demo` set.
- Computer vision isn't built yet. A vision worker should only call `POST /api/v1/ingest/observations`.
- Endpoints that use the database are plain `def`, not `async def`, because the SQLAlchemy session is synchronous and would otherwise block the event loop. This replaces the async example below.
- Run one backend process: the live-update hub, alert loop and rate limiter are in memory.
- Permissions live in `backend/app/auth/access.py`. Check roles on the server. Hiding a screen is not protection.
- Alerts queue in `AlertDelivery` and send from a separate loop in `backend/app/services/notifications.py`. Demo restaurants must never send real messages.
- The Android app is `frontend/android`, a Capacitor shell that opens the live site. Native code lives in `com.dineopssi.app`. Alerts arrive as data-only Firebase messages (`backend/app/services/push.py`), never `notification` messages, because only then does the app control the ring.
- Android fixes a notification channel's sound when it's created. To change the ring, change `CHANNEL_ID` in `AlarmNotifications.java`.

---

## Tech Stack

- **Backend:** FastAPI + Python 3.11+
- **Frontend:** React + TypeScript + Vite
- **Database:** PostgreSQL + SQLAlchemy
- **Auth:** JWT + Google OAuth (Google login not built yet)
- **UI:** Tailwind + Framer Motion

---

## Project Structure

```
project/
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, database.py
│   │   ├── models/, schemas/, routers/, services/, auth/
│   ├── alembic/
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/, pages/, hooks/, services/, context/, types/
├── skills/           # 5 skill files
├── agents/           # Agent definitions
└── .claude/commands/ # /generate-prp, /execute-prp
```

---

## Code Standards

### Python
```python
# Type hints required
def get_user(db: Session, user_id: int) -> User:
    pass

# Async endpoints
@router.get("/users/{id}")
async def get_user(id: int, db: Session = Depends(get_db)):
    pass
```

### TypeScript
```typescript
// Interfaces required - NO any types
interface User { id: number; email: string; }

const fetchUser = async (id: number): Promise<User> => { ... };
```

---

## Forbidden

- `print()` → use `logging`
- Plain passwords → use bcrypt
- Hardcoded secrets → use env vars
- `any` type in TypeScript
- `console.log` in production
- Inline styles → use UI framework

---

## Workflow

```
1. Edit INITIAL.md (define product)
2. /generate-prp INITIAL.md
3. /execute-prp PRPs/[name]-prp.md
```

---

## Skills

| Task | Skill |
|------|-------|
| API + Auth | `skills/BACKEND.md` |
| React + UI | `skills/FRONTEND.md` |
| Models | `skills/DATABASE.md` |
| Tests | `skills/TESTING.md` |
| Docker | `skills/DEPLOYMENT.md` |

---

## Agents

| Agent | Role |
|-------|------|
| DATABASE-AGENT | Models + migrations |
| BACKEND-AGENT | API + auth |
| FRONTEND-AGENT | UI + pages |
| DEVOPS-AGENT | Docker + CI/CD |

---

## Validation

```bash
cd backend && ruff check app tests && mypy app && pytest --cov=app --cov-fail-under=80
cd frontend && npm run lint && npm run type-check && npm test
docker compose build
```

---

## Environment Variables

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/db
SECRET_KEY=at-least-32-characters
ALLOWED_ORIGINS=http://localhost:5173
```
