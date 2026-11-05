# DineOps SI

Live table management for restaurants: table status, staff alerts by app, SMS and WhatsApp, waitlist and staffing analytics.

Built from the MicroSaaS template (`skills/`, `agents/`, `.claude/commands/`). The product definition is in `INITIAL.md` and the blueprint is in `PRPs/dineops-si-prp.md`.

## What works today

- Accounts and restaurants, with each owner's data kept separate
- Staff logins with owner, manager and staff roles
- Waiter and cleaning alerts by SMS and WhatsApp through Twilio
- Drag-and-drop floor plan
- Live board: free, occupied or needs cleaning, with timers
- Waiter and cleaning alerts with configurable thresholds
- Waitlist with next-free-table estimates from the restaurant's own history
- Analytics: footfall, peak hours, turn time, response times and suggested waiters
- Three ways to update a table: staff taps, the camera ingest API and the demo simulator

## What isn't built yet

- **Computer vision.** Nothing reads video yet. The ingest API below is where it plugs in, and detection accuracy is untested because no footage is available yet.
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
  -H "X-API-Key: dos_your_key" \
  -H "Content-Type: application/json" \
  -d '{"observations": [{"table_id": 1, "guest_count": 3, "staff_present": false}]}'
```

The worker only has to count guests and staff at each table. The server applies the confirmation times and raises alerts. Times come from the server clock when a request arrives, so buffered or delayed observations aren't supported yet.

## Staff roles

| | Owner | Manager | Staff |
|---|---|---|---|
| Live floor, alerts, waitlist | Yes | Yes | Yes |
| Analytics, floor setup, settings | Yes | Yes | No |
| Add and manage staff | Yes | Yes | No |
| Add and manage managers | Yes | No | No |
| Camera key, delete restaurant | Yes | No | No |

A manager creates each staff login and gets a temporary password to pass on. Staff must choose their own password before they can do anything else.

## SMS and WhatsApp alerts

Until a provider is connected, `NOTIFICATION_PROVIDER=log` only records messages, and the Staff page says so. To send real messages:

1. Create a [Twilio](https://www.twilio.com) account.
2. Add these to `.env`, then run `docker compose up -d`:

```env
NOTIFICATION_PROVIDER=twilio
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_SMS_FROM=+15551234567
TWILIO_WHATSAPP_FROM=+15557654321
TWILIO_WHATSAPP_CONTENT_SID=
```

3. On the Staff page, add yourself with your own email and phone, turn on a channel, and use **Send a test alert**.

Leave out a sender to turn that channel off. Check these before relying on it:

- **WhatsApp:** Twilio's sandbox is fine for testing, but each phone must join it first. In production, a business messaging first must use a template approved by WhatsApp. Create one with three variables (restaurant, table, issue) and set `TWILIO_WHATSAPP_CONTENT_SID`.
- **SMS in India:** sending to Indian numbers requires DLT registration of your business and message template.
- **Cost:** each alert costs one message per person per channel. Use on-shift status and **Most messages per day** in Settings to control this.
- **Consent:** only message people who have agreed. Changing someone's number clears their consent.

Who gets a message: active staff who are on shift, have a phone number and consent, and have that channel and alert type turned on. A message is dropped if the problem is fixed first or it's over 10 minutes old. Temporary failures retry up to 3 times.

## Limits to know before production

- Run **one backend process**. Live updates, the alert loop and login rate limiting all live in memory. Running several workers needs Redis first.
- The alert loop scans every restaurant on every tick. That's fine for early customers, but it needs to change at scale.
- Tokens are stored in `localStorage`, following the template. Keep third-party scripts off the app and set a strict Content Security Policy.
- Serve over HTTPS and restrict `ALLOWED_ORIGINS`.
- Before using real cameras, get legal advice on notices and consent for filming guests and staff. Don't store video or use face recognition.

## Android app

Staff phones get a loud alert with its own ringtone. It plays on the alarm volume and repeats until someone taps it, presses **Acknowledge**, or five minutes pass. When one person responds, the other phones stop ringing. Alerts are free per message.

GitHub builds the app. Find it under **Actions > Android app > latest run > Artifacts**, and send the APK inside to staff phones.

### Setup

1. **Put the server online** (below). Phones can't reach a computer running at `localhost`.
2. **Create a free Firebase project** at https://console.firebase.google.com.
   - Add an Android app with the package name `com.dineopssi.app`, and download `google-services.json`.
   - Under **Project settings > Service accounts**, generate a new private key. This file is a secret.
3. **Tell the server about Firebase.** On the server, add to `.env`:
   - `FIREBASE_SERVICE_ACCOUNT_B64`: the output of `base64 -w0 your-key-file.json`
   - `PUBLIC_APP_URL`: your address, like `https://app.example.com`
4. **Create the signing key** on your own computer, once. Keep the output safe: without it, phones can't take updates.
   ```bash
   backend/.venv/Scripts/python deploy/make_android_key.py "C:/DineOps-keys"
   ```
5. **Add these under GitHub > Settings > Secrets and variables > Actions**, then rerun the Android app workflow:
   | Type | Name | Value |
   |---|---|---|
   | Variable | `APP_URL` | Your address, like `https://app.example.com` |
   | Secret | `GOOGLE_SERVICES_JSON_B64` | `google-services.json`, base64 encoded on one line |
   | Secret | `ANDROID_KEYSTORE_B64` | Contents of `dineops-android-key.b64.txt` |
   | Secret | `ANDROID_KEYSTORE_PASSWORD` | Contents of `dineops-android-key-password.txt` |

### On each phone

1. Install the APK and allow installs from that source when Android asks.
2. Sign in, open **Live floor**, and allow notifications.
3. Under **My alerts**, follow any warning shown, then press **Test the ring**.
4. If the phone is Xiaomi, Vivo, Oppo, Realme or similar, also set the app's battery use to Unrestricted and turn on Autostart. These phones can otherwise block alerts while the app is closed.

## Putting it on a server

This needs a VPS, meaning a server where you can run Docker. Shared web hosting can't run it. You also need a domain or subdomain whose DNS `A` record points at the server's IP address.

```bash
git clone https://github.com/thomasalvaedisonsarazin/Hotel_Table_SI_Management.git dineops
cd dineops
cp .env.example .env   # Then fill it in. Set a strong DB_PASSWORD and SECRET_KEY, and DOMAIN.
                       # Set ALLOWED_ORIGINS to https://your-domain
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Only ports 22, 80 and 443 need to be open. HTTPS certificates are handled automatically. The database lives in a Docker volume, so set up regular backups before real restaurants rely on it.

