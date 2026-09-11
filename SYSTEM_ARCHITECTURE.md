# System Architecture — Aivis (mental)

Two independent Flask services, a shared SQLite database, and a unified
ingestion pipeline that Gmail, Slack, and chat messages all flow through.

---

## 🏗️ Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL CLIENTS                                   │
│         Expo web/mobile app (frontend/), Gmail Pub/Sub, Slack Events API     │
└─────────────────────────────┬───────────────────────────────────────────────┘
                               │ HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  CORE SERVICE — backend/core_app.py  (:5000)                 │
│   Run: `python server.py core`  ·  Prod: start.sh → gunicorn core_app:app    │
│   SQLite (backend/storage/aivis.db) + webhooks + REST for the Expo app       │
│                                                                              │
│  Ingestion            Gmail actions           Tasks/Action items            │
│  ─────────            ─────────────           ─────────────────            │
│  POST /slack/events    POST /api/gmail/reply    GET  /api/tasks             │
│  POST /ingest/slack    POST /api/gmail/send      POST /api/tasks/<id>/complete│
│  POST /gmail/events    POST /api/gmail/forward   GET  /api/action-items     │
│  POST /ingest/gmail    POST /api/gmail/draft-*   POST /api/action-items/archive│
│  POST /webhooks/       POST /api/gmail/thread-detail  /done               │
│       gmail/pubsub     GET  /api/gmail/labels                              │
│                        POST /api/gmail/watch/start|stop                    │
│                                                                              │
│  Chat (proxies to AI service)     Google OAuth / Calendar                   │
│  ─────────────────────────────    ───────────────────────                  │
│  POST /api/chat                   GET  /google/auth/<username>             │
│  POST /api/session_chat           GET  /google/oauth2callback              │
│  POST /api/sessions-log           POST /api/google-profile                 │
│  POST /api/transcribe (Whisper)   POST /api/email-connections              │
│                                    POST /api/calendar/events|create         │
│                                                                              │
│  Slack interactive · misc                                                   │
│  ──────────────────────────                                                 │
│  POST /slack/interactive     GET /memory/context      GET /metrics/summary │
│  GET  /api/messages/recent   GET /api/search           POST /api/profile-link/slack│
│  GET  /debug/*, /debug/sql/*, /debug/classify* (dev only)                  │
└──────────────┬───────────────────────────────────────────┬──────────────────┘
               │ ingest/*, /webhooks/*  →  event pipeline   │ chat_api →
               ▼                                            │ AI service (HTTP)
┌───────────────────────────────────────────┐               │
│  EVENT PIPELINE (shared, source-agnostic)  │               │
│  application/orchestrators/event_orchestrator.py            │
│    → services/unified_processor.py         │               │
│    process_normalized_message():           │               │
│      1. dedup (insert_message_if_new)      │               │
│      2. client/project resolution          │               │
│         (client_routing, project_resolution)│              │
│      3. classification (classification_service)│           │
│      4. importance scoring + scheduling    │               │
│         signal analysis                    │               │
│      5. project context update             │               │
│         (project_context_updater,          │               │
│          project_update_extractor)         │               │
│      6. follow-up detection + creation     │               │
│         (follow_up_detector/_manager)      │               │
│      7. local task creation/linking        │               │
│         (task_service → tasks table)       │               │
│      8. reply policy + reply text          │               │
│         (inbound_reply_service)            │               │
│      9. Gmail-only: draft creation         │               │
│         (reply_service.maybe_create_gmail_draft)│           │
│     10. metrics event (metrics_tracker →   │               │
│         metrics_events table)              │               │
└───────────────────────────────────────────┘               │
                                                              ▼
                                          ┌─────────────────────────────────────┐
                                          │  AI SERVICE — backend/ai_app.py (:5055)│
                                          │  Run: `python server.py ai`            │
                                          │  Prod: start-ai.sh → gunicorn          │
                                          │        backend.ai_app:app              │
                                          │                                       │
                                          │  POST /v1/chat  (X-AI-Service-Secret)  │
                                          │    → ai_chat_orchestrator.Orchestrator │
                                          │                                       │
                                          │  detect_intent(message):               │
                                          │    keyword match (email/slack/general) │
                                          │    + LLM tie-break when ambiguous      │
                                          │                                       │
                                          │  ┌─────────────┬─────────────┬───────┐│
                                          │  │ AivisCore   │ GmailAgent  │ Slack ││
                                          │  │ Agent       │             │ Agent ││
                                          │  │ (general    │ (sub-intent │(always││
                                          │  │  chat, draft│  regex →    │ delega││
                                          │  │  reply/     │  list/send/ │ -tes to││
                                          │  │  polish     │  draft_reply│ core  ││
                                          │  │  modes)     │  /detail)   │ ingest)││
                                          │  └─────────────┴─────────────┴───────┘│
                                          └───────────────────┬───────────────────┘
                                                              │ core_backend_client.py
                                                              │ (ingest_gmail, ingest_slack,
                                                              │  fetch_recent_messages)
                                                              ▼
                                          back to CORE SERVICE :5000 (loops into the
                                          same event pipeline above, or reads SQLite
                                          via /api/messages/recent)
```

**The two services call each other over plain HTTP, not shared memory:**
- Core → AI: `chat_api.py` → `application/orchestrators/chat_orchestrator.py` →
  `services/ai_chat_client.py` → `POST {AI_SERVICE_URL}/v1/chat` (default
  `http://127.0.0.1:5055`).
- AI → Core: `GmailAgent` / `SlackAgent` → `application/services/core_backend_client.py`
  → `POST {CORE_BACKEND_URL}/ingest/gmail|slack`, `GET /api/messages/recent`
  (default `http://localhost:5000`).

This means a Gmail/Slack message sent from the chat UI is normalized and run
through the *same* `unified_processor` pipeline as a real inbound webhook —
there's exactly one ingestion path, not one for chat and one for webhooks.

---

## 📊 Example: Complete Request Flow

### Scenario: User sends "schedule a meeting with John tomorrow at 3pm" in chat

```
1. HTTP REQUEST
   POST /api/chat  (core service, :5000)
   { "user_id": "vanesa@...", "message": "...", "session_id": "..." }

2. chat_api.py → application/orchestrators/chat_orchestrator.handle_chat_turn()
   a. Best-effort: run the message through the shared event pipeline
      (event_orchestrator.handle_normalized_event) so project mentions in
      chat are tracked the same way as Gmail/Slack — errors here never
      block the reply.
   b. Store the user message in SQLite (application/services/thread_service.py)
   c. Try quick-action shortcuts before calling the LLM:
      - application/services/calendar_meeting_action.try_create_meeting_from_chat()
        → detects "schedule/meeting" language, creates a Google Calendar
          event directly (services/google_calendar_client.py), returns a
          canned confirmation reply. If matched, skip steps d–e.
      - application/services/chat_task_action.try_create_task_from_chat()
        → same idea for "remind me to / add a task" phrasing.
   d. If no shortcut matched: services/ai_chat_client.complete_chat() —
      HTTP POST to the AI service (:5055) /v1/chat.
   e. Store the assistant reply in SQLite.

3. AI SERVICE (:5055) — only reached if no calendar/task shortcut matched
   ai_chat_orchestrator.Orchestrator.handle_chat()
     detect_intent() → keyword scan; both "email" and "slack" keyword sets
     empty here → "general"
     → AivisCoreAgent.handle_chat() → LLMService.chat_completion_text()
       (OpenAI, model from OPENAI_MODEL env, default gpt-4o-mini)

4. RESPONSE
   AI service → { "success": true, "intent": "general", "reply": "..." }
   Core service → client: { "success": true, "intent": "...", "reply": "..." }
```

### Scenario: Inbound Gmail message (Pub/Sub push)

```
1. Google Pub/Sub → POST /webhooks/gmail/pubsub (webhooks.py)
   or Gmail watch poll → POST /gmail/events / /ingest/gmail (gmail.py)

2. gmail.py: parses the raw payload (services/gmail_text.py), builds a
   normalized event dict, resolves the owning app user from
   profile_link table (storage/sqlite_db.get_user_id_for_gmail_address)

3. event_orchestrator.handle_normalized_event()
   → services/unified_processor.process_normalized_message()
     dedup → client/project resolution → classification → importance +
     scheduling analysis → project context update → follow-up detection →
     task linking → reply policy/reply text → (Gmail) draft creation →
     metrics event

4. If reply policy says a draft should exist: reply_service.maybe_create_gmail_draft()
   creates a Gmail draft via the Gmail API for the user to review/send.

5. New action items/tasks surface in the Expo app via GET /api/action-items
   and GET /api/tasks.
```

---

## 🗄️ Data Layer — SQLite (MongoDB removed)

All persistent state lives in one SQLite file, `backend/storage/aivis.db`,
created from `backend/storage/schema.sql` and accessed through
`backend/storage/sqlite_db.py` (~1,800 lines of query helpers — no ORM).
`backend/database.py` is a stub kept only so old imports of `get_db()` /
`DatabaseManager` don't break; it does nothing and is not on any live path.

Tables:

| Table | Purpose |
|---|---|
| `clients` | Top-level owner/namespace, scoped by `data_owner_key` |
| `projects` | Projects under a client (status, priority, deadline) |
| `project_context` | Free-text project memory (summary, blockers, next steps, contacts) |
| `calendar_events` | Google Calendar events, optionally linked to a client/project |
| `messages` | Every ingested Gmail/Slack/chat message, deduped by `(source, source_id)` |
| `events` | Append-only pipeline event log (one row per processing step) |
| `tasks` | Locally created tasks (`grafik_task_id` is a legacy column name, not an external integration — `backend/integrations/grafik/` is currently empty) |
| `follow_ups` | Detected "awaiting response" / "promised action" items |
| `metrics_events` | One row per pipeline run, for `/metrics/summary` |
| `gmail_watch_state` | Per-mailbox Gmail Pub/Sub watch baseline (`historyId`) |
| `thread_replies` | Threads already replied to, to hide from the task list |
| `profile_link` | Maps an Expo app login to its Gmail address / Slack identity |

A separate, **optional** vector-memory module exists under
`backend/application/services/memory/` (Pinecone-backed). It is only used
when `AIVIS_CHAT_RAG=1` is set for `AivisCoreAgent`; by default chat runs
without it and there is no Mongo/Pinecone dependency at all.

---

## 🧩 Services Layer (backend/services/*)

These are the building blocks `unified_processor.py` composes, in the order
it calls them:

| Module | Role |
|---|---|
| `client_routing.py` | Ensures a `clients` row exists for the ingest source |
| `project_resolution.py` | Matches message text to an existing project or falls back to "General" |
| `classification_service.py` | LLM-based classification + enrichment of the message |
| `importance_scoring.py` | Scores message importance from classification + project continuity |
| `scheduling_awareness.py` | Detects scheduling/time-pressure signals in the text |
| `continuity_context.py` | Builds "what's already known about this client/project" context |
| `project_context_updater.py`, `project_update_extractor.py` | Extract and persist project memory updates |
| `follow_up_detector.py`, `follow_up_manager.py` | Detect and create `follow_ups` rows |
| `task_service.py` | Builds task title/description, creates/links `tasks` rows |
| `inbound_reply_service.py` | Reply policy (should/how to reply) + reply text generation |
| `reply_writer.py`, `reply_policy.py` | Lower-level reply drafting/policy helpers |
| `reply_service.py` (application/services) | Creates the actual Gmail draft when policy says so |
| `marketing_email_signals.py` | Suppresses newsletters/marketing mail as non-actionable |
| `metrics_tracker.py` | Builds the `metrics_events` row for each pipeline run |
| `gmail_text.py`, `slack_text.py` | Provider-specific payload parsing/cleaning |
| `google_calendar_client.py` | Thin wrapper over the Google Calendar API |
| `data_owner_key.py` | Resolves the multi-tenant partition key for a request |
| `chat_project_hint.py` | Best-effort project-name hint extraction from chat text |
| `client_routing.py` / `user_search.py` / `follow_up_*` etc. | Support the same pipeline from different entry points |

---

## 🤖 AI Service internals (backend/application/*)

- **Orchestrator** — `application/orchestrators/ai_chat_orchestrator.py`:
  `detect_intent()` keyword-matches "email"/"slack" vocab; if both or
  neither match, an LLM call disambiguates. Routes to one of three agents.
- **AivisCoreAgent** (`agents/aivis_core_agent.py`) — general chat. Builds a
  system prompt (optionally RAG-augmented via `memory_service`), supports two
  special modes driven by chat metadata: *reply-draft* (write an outgoing
  message body) and *draft-polish* (rewrite an existing draft per
  instruction). Calls `LLMService` directly.
- **GmailAgent** (`agents/gmail_agent.py`) — regex/keyword sub-intent
  detection (`draft_reply`, `list`, `send`, `reply`, `detail`). `list` reads
  from Core via `fetch_recent_messages()`; everything else that isn't a pure
  LLM draft delegates back to Core's `/ingest/gmail` so it runs through the
  full `unified_processor` pipeline.
- **SlackAgent** (`agents/slack_agent.py`) — always delegates to Core's
  `/ingest/slack`; has no local logic of its own.
- **LLMService** (`integrations/llm/llm_client.py`) — thin OpenAI wrapper:
  `chat_completion()`, `chat_completion_text()`, `generate_embedding(s)`.
  Model/temperature/max-tokens come from `OPENAI_MODEL` / `OPENAI_TEMPERATURE`
  / `OPENAI_MAX_TOKENS` env vars (defaults: `gpt-4o-mini`, 0.3, 768).

---

## 🎯 Key Design Principles

1. **One ingestion path** — Gmail, Slack, and chat-originated project
   mentions all funnel through `unified_processor.process_normalized_message()`,
   so classification/follow-up/task logic isn't duplicated per source.
2. **Two independently deployable services** — Core (SQLite + webhooks + REST)
   and AI (LLM orchestration) talk only over HTTP, with plain env-var URLs
   (`AI_SERVICE_URL`, `CORE_BACKEND_URL`) and an optional shared-secret header.
   Either can be scaled, restarted, or redeployed independently.
3. **SQLite as the single source of truth** — no Mongo, no required vector
   DB; multi-tenancy is a `data_owner_key` column, not separate databases.
4. **Fail-open observability** — every pipeline run ends in a
   `metrics_events` row and an `events` log row, wrapped so a logging failure
   never breaks the actual response.
5. **Unified logging** — `utils/logger.get_logger()` gives consistent
   `%(asctime)s | %(levelname)s | %(message)s` formatting across both
   services.

---

## Frontend (frontend/src/)

Expo (React Native + web) app. Key directories:
- `pages/` — screens: `ChatPage`, `QuickChatPage`, `VoiceChat`, `GmailAgentPage`,
  `TasksPage`, `ProjectsPage`, `ContactsPage` (+ `ContactDetailPage`,
  `ContactsWithRelationshipsPage`), `SchedulerPage`, `WeeklySchedulePage`,
  `SettingsPage`, `LoginPage`, `HomePage`, `MenuPage`, `WaitlistPage`.
- `api/` — thin fetch wrappers: `actionItems.js`, `sqliteTasks.js`,
  `sqliteProjects.js`, `scheduleData.js`, `userSearch.js`.
- `components/`, `hooks/`, `styles/`, `utils/`, `config/`.

Note: contacts pages exist in the frontend, but there is currently no
`/api/contacts/*` backend blueprint backing them — check `frontend/src/api/`
for what they actually call before assuming parity with the UI.

---

## Known gaps / things to verify before relying on this doc

- `backend/integrations/grafik/` is an empty package (no files besides
  `__pycache__`). The "Grafik" name only survives as a column
  (`tasks.grafik_task_id`) — there is no external Grafik integration today.
- The optional Pinecone-backed memory module
  (`backend/application/services/memory/`) is gated behind `AIVIS_CHAT_RAG`
  and not exercised by default; treat it as experimental.
- This document was regenerated on 2026-09-11 by reading the current code
  (`core_app.py`, `ai_app.py`, orchestrators, agents, `unified_processor.py`,
  `schema.sql`). Re-verify against the code if it's been a while — nothing
  here is auto-synced.
