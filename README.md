# TableSense

Live table management for restaurants: table status, service alerts, waitlist and staffing analytics.

> **Working name.** It hasn't been checked for trademark or domain availability.

Built from the MicroSaaS template (`skills/`, `agents/`, `.claude/commands/`). The product definition is in `INITIAL.md` and the blueprint is in `PRPs/tablesense-prp.md`.

## What works today

- Accounts and restaurants, with each owner's data kept separate
- Drag-and-drop floor plan
- Live board: free, occupied or needs cleaning, with timers
- Waiter and cleaning alerts with configurable thresholds
- Waitlist with next-free-table estimates from the restaurant's own history
- Analytics: footfall, peak hours, turn time, response times and suggested waiters
- Three ways to update a table: staff taps, the camera ingest API and the demo simulator

## What isn't built yet

- **Computer vision.** Nothing reads video yet. The ingest API below is where it plugs in, and detection accuracy is untested because no footage is available yet.
- Staff logins and roles (one owner login per account for now)
- Push or WhatsApp alerts (alerts appear in the app only)
- Google login, billing and hotels

Demo restaurants use simulated activity and sample history, labelled as such on every page.

## Run with Docker

```bash
cp .env.example .env        # set DB_PASSWORD and SECRET_KEY
docker compose up --build
```

Then open http://localhost:3000 and choose **Open the demo**. API docs are at http://localhost:8000/docs.

## Run for development

Start Postgres (`docker compose up -d db` works), then:

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
# Set DATABASE_URL and SECRET_KEY in backend/.env
alembic upgrade head
uvicorn app.main:app --reload

# Frontend, in a second terminal
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## Checks

```bash
cd backend && ruff check app tests && mypy app && pytest --cov=app --cov-fail-under=80
cd frontend && npm run lint && npm run type-check && npm test && npm run build
```

Backend tests use a temporary SQLite database by default. Set `TEST_DATABASE_URL` to run them on Postgres, as CI does.

## How a table changes state

```
free ──guests seen for seat_confirm──► occupied
occupied ──no guests for vacate_confirm──► needs_cleaning
needs_cleaning ──staff present for clean_confirm, or a tap──► free
needs_cleaning ──new guests sit down──► occupied (cleaning assumed)
```

The rules are in `backend/app/services/table_engine.py`. Short gaps in detection are ignored, so a passer-by doesn't occupy a table and a few missed frames don't end a session.

## Connecting a camera worker

Create a key under **Settings → Camera connection key**, then send what each table's camera sees, every couple of seconds:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/observations \
  -H "X-API-Key: ts_your_key" \
  -H "Content-Type: application/json" \
  -d '{"observations": [{"table_id": 1, "guest_count": 3, "staff_present": false}]}'
```

The worker only has to count guests and staff at each table. The server applies the confirmation times and raises alerts. Times come from the server clock when a request arrives, so buffered or delayed observations aren't supported yet.

## Limits to know before production

- Run **one backend process**. Live updates, the alert loop and login rate limiting all live in memory. Running several workers needs Redis first.
- The alert loop scans every restaurant on every tick. That's fine for early customers, but it needs to change at scale.
- Tokens are stored in `localStorage`, following the template. Keep third-party scripts off the app and set a strict Content Security Policy.
- Serve over HTTPS and restrict `ALLOWED_ORIGINS`.
- Before using real cameras, get legal advice on notices and consent for filming guests and staff. Don't store video or use face recognition.
