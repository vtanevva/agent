# Aivis - AI Personal Assistant

An AI-powered personal assistant with email (Gmail) management, calendar integration,
contact management, and a memory system that learns from conversations, Gmail, and Slack.

The app is two independent Flask services plus an Expo (React Native + web) frontend:

- **Core backend** (`backend/core_app.py`, port `5000`) — SQLite storage, Gmail/Slack
  webhooks, Google OAuth + Calendar, tasks/action items, and the REST API the frontend talks to.
- **AI service** (`backend/ai_app.py`, port `5055`) — the chat orchestrator and LLM agents.
  The core backend proxies `/api/chat` to this service over HTTP.
- **Frontend** (`frontend/`) — an Expo app (works on web, iOS, and Android) that talks to
  the core backend.

See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) for the full request/data flow.

> Note: MongoDB and a standalone document-RAG pipeline referenced in older docs have been
> removed / are not wired up by default. Persistence is SQLite (`backend/storage/aivis.db`).

## Prerequisites

- Python 3.10+
- Node.js 20+ and npm
- An OpenAI API key (only hard requirement to chat)
- Optional, for specific integrations: a Google Cloud OAuth client (Gmail/Calendar), a
  Microsoft Azure AD app (Outlook Calendar), and a Pinecone account (only if you enable RAG)

## Setup

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd mental
cp env.example .env
# Edit .env — at minimum, set OPENAI_API_KEY
```

See [Environment Variables](#environment-variables) below for what each variable does.

### 2. Backend

```bash
python -m venv .venv
# Windows (PowerShell/cmd):
.venv\Scripts\activate
# Windows (Git Bash):
source .venv/Scripts/activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Run the two backend services in separate terminals from the repo root:

```bash
# Terminal 1 — AI service (orchestrator + LLM), http://127.0.0.1:5055
python server.py ai

# Terminal 2 — core API (SQLite, webhooks, REST), http://localhost:5000
python server.py core
```

The first run creates `backend/storage/aivis.db` automatically from
`backend/storage/schema.sql` — no manual migration step is needed.

(Equivalent direct invocations: `python backend/ai_app.py` from the repo root, and
`cd backend && python core_app.py`.)

### 3. Frontend

```bash
cd frontend
npm install
npm run web      # opens the Expo web app, talks to http://localhost:5000
# or: npm start   # Expo dev tools — press w/i/a for web/iOS/Android
```

On web, the frontend auto-detects the core backend at `http://<current-host>:5000`, so no
extra config is needed for local dev. To point it somewhere else (a device on your LAN, a
deployed backend, etc.), set `EXPO_PUBLIC_API_BASE_URL` (and optionally
`EXPO_PUBLIC_CORE_BACKEND_URL`) in `frontend/.env` — see
[frontend/src/config/api.js](frontend/src/config/api.js).

### 4. Verify it's running

```bash
curl http://localhost:5000/health
curl http://127.0.0.1:5055/health
```

Then open the frontend (the web build opens automatically, or scan the QR code with Expo Go
for a device) and send a chat message.

## Environment Variables

Full reference lives in [env.example](env.example) and [backend/config.py](backend/config.py).
Only `OPENAI_API_KEY` is required to start chatting; everything else unlocks an optional
integration.

| Variable | Required for | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Chat | Required |
| `SQLITE_PATH` | Core backend | Defaults to `storage/aivis.db` (relative to `backend/`) |
| `AI_SERVICE_URL`, `CORE_BACKEND_URL` | Core ↔ AI service | Defaults match `python server.py` ports |
| `GOOGLE_SECRET_FILE`, `OAUTH_REDIRECT_URI` | Gmail / Calendar | Needs an OAuth client JSON from Google Cloud Console, saved to the path in `GOOGLE_SECRET_FILE` (default `google_client_secret.json` in the repo root) |
| `GMAIL_PUBSUB_TOPIC`, `GMAIL_PUBSUB_WEBHOOK_SECRET` | Gmail push notifications | Only needed for real-time Gmail webhooks |
| `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | Outlook Calendar | Optional |
| `IG_APP_ID`, `IG_APP_SECRET` | Instagram messaging | Optional |
| `SLACK_BOT_TOKEN`, `SLACK_WEBHOOK_SECRET` | Slack ingestion | Optional |
| `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `PINECONE_ENV` | RAG | Only used when `ENABLE_RAG=true` |
| `ENABLE_MEMORY`, `ENABLE_RAG`, `ENABLE_AUTOGEN` | Feature flags | See `backend/config.py` |

## API Endpoints

The core backend (`:5000`) exposes the REST API the frontend uses. Highlights:

### Chat
- `POST /api/chat` - Chat endpoint (proxies to the AI service)
- `POST /api/session_chat`, `POST /api/transcribe` - session chat, voice transcription

### Gmail
- `GET /api/gmail/threads`, `GET /api/gmail/thread-detail` - list/read threads
- `POST /api/gmail/send`, `POST /api/gmail/reply`, `POST /api/gmail/forward` - send mail
- `POST /api/gmail/draft-*` - draft creation/management
- `POST /api/gmail/watch/start|stop` - Gmail push notifications

### Calendar & OAuth
- `GET /google/auth/<username>`, `GET /google/oauth2callback` - Google OAuth flow
- `GET /api/calendar/events`, `POST /api/calendar/create` - Calendar events

### Tasks & Action Items
- `GET /api/tasks`, `POST /api/tasks/<id>/complete`
- `GET /api/action-items`, `POST /api/action-items/<id>/archive|done`

### Misc
- `GET /health` - health check (both services)
- `GET /memory/context` - debug: current memory/context bundle for a user
- `GET /metrics/summary` - ingestion/classification metrics

See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) for the complete endpoint map and the
ingestion pipeline each message flows through.

## Project Structure

```
mental/
├── server.py                  # Dev launcher: `python server.py core|ai`
├── start.sh / start-ai.sh     # Production entrypoints (gunicorn)
├── requirements.txt           # Python dependencies (repo root, canonical)
├── env.example                # Copy to .env and fill in
├── SYSTEM_ARCHITECTURE.md     # Full architecture + endpoint map
├── backend/
│   ├── core_app.py            # Core Flask API (SQLite, webhooks, REST) — :5000
│   ├── ai_app.py               # AI chat Flask service (orchestrator) — :5055
│   ├── config.py               # Centralized env-based configuration
│   ├── api/routes/             # Flask blueprints (gmail, calendar, tasks, chat, webhooks, ...)
│   ├── application/
│   │   ├── orchestrators/      # event_orchestrator, ai_chat_orchestrator
│   │   ├── agents/              # AivisCore, Gmail, Slack agents
│   │   └── services/memory/     # facts/context/RAG (Pinecone-backed, optional)
│   ├── services/                # Business logic (classification, replies, follow-ups, ...)
│   ├── storage/                 # sqlite_db.py, schema.sql, aivis.db
│   ├── workers/                 # background jobs (ingestion, follow-ups)
│   ├── integrations/            # LLM + external service clients
│   └── utils/
├── frontend/                    # Expo app (web + iOS + Android)
│   └── src/
│       ├── pages/                # Chat, Tasks, Contacts, Calendar, Settings, ...
│       ├── components/
│       ├── api/                  # HTTP clients for the core backend
│       └── config/api.js         # Backend URL auto-detection
└── tests/                       # pytest suite
```

## Testing

```bash
pytest tests/ -v
```

## Security Notes

- `.env` is gitignored — never commit real API keys or OAuth secrets.
- Google/Microsoft OAuth tokens are cached locally (`backend/token*.json`,
  `backend/credentials.json`) and are also gitignored.
- `FLASK_SECRET_KEY` must be set to a real secret before deploying to production
  (`backend/config.py` refuses to start in production with the default dev key).

## Deployment

The repo ships a `Dockerfile` and `start.sh` for Railway: the container builds the Expo web
app into `web-build/`, then `start.sh` runs both the AI service (background, `AI_CHAT_PORT`)
and the core backend (foreground, `$PORT`) under gunicorn in a single container. See
`Dockerfile`, `start.sh`, and `railway.toml`.

## Troubleshooting

**`ModuleNotFoundError` when running `core_app.py` directly** — run it via
`python server.py core` from the repo root, or `cd backend && python core_app.py` (it needs
`backend/` on `sys.path`).

**SQLite schema mismatch error on startup** — the schema changed since your local
`aivis.db` was created. Either delete `backend/storage/aivis.db` (dev data is disposable) and
restart, or write a migration.

**Frontend can't reach the backend** — on web it auto-targets
`http://<window.hostname>:5000`; on a physical device set `EXPO_PUBLIC_USE_LOCAL=true` and
your machine's LAN IP, or set `EXPO_PUBLIC_API_BASE_URL` explicitly. See
`frontend/src/config/api.js`.

**Gmail/Calendar features fail with an OAuth error** — you need a Google Cloud OAuth client
saved as `google_client_secret.json` (or point `GOOGLE_SECRET_FILE` at it), and
`OAUTH_REDIRECT_URI` must match a redirect URI registered on that OAuth client.

**"Missing required environment variables: OPENAI_API_KEY"** — set it in `.env`; both
services load `.env` via `python-dotenv` on startup.
