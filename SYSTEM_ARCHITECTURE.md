# System Architecture Diagram - Productivity Assistant

## 🏗️ Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL CLIENTS                                   │
│                  (Browser, Mobile App, API Clients)                          │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ HTTP Requests
                              │ (POST /api/chat, /api/gmail/*, etc.)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLASK APPLICATION                                    │
│                        (backend/core_app.py)                                   │
│                         Port: 5000 (or $PORT)                                │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                      API LAYER (Blueprints)                         │    │
│  ├────────────────────────────────────────────────────────────────────┤    │
│  │                                                                      │    │
│  │  📬 /api/chat                POST    General chat endpoint          │    │
│  │     └─> routes/chat_api.py → HTTP POST /v1/chat (backend/ai_app.py) │    │
│  │         separate process :5055, env AI_SERVICE_URL                    │    │
│  │                                                                      │    │
│  │  📧 /api/gmail/*             13 endpoints                           │    │
│  │     ├─> /list                List emails                            │    │
│  │     ├─> /send                Send email                             │    │
│  │     ├─> /reply               Reply to email                         │    │
│  │     ├─> /thread              Get thread details                     │    │
│  │     ├─> /search              Search emails                          │    │
│  │     ├─> /classify            Classify email                         │    │
│  │     ├─> /triage              Triaged inbox                          │    │
│  │     ├─> /style               Analyze writing style                  │    │
│  │     ├─> /generate-reply      Generate reply draft                   │    │
│  │     ├─> /rewrite             Rewrite email                          │    │
│  │     ├─> /archive             Archive thread                         │    │
│  │     ├─> /mark-handled        Mark as handled                        │    │
│  │     └─> /classify-bg         Background classification              │    │
│  │     └─> gmail_routes.py                                             │    │
│  │                                                                      │    │
│  │  👤 /api/contacts/*          Contact management                     │    │
│  │     └─> contacts_routes.py                                          │    │
│  │                                                                      │    │
│  │  🔐 /google/*                OAuth endpoints                         │    │
│  │     ├─> /auth/<user_id>      Start OAuth flow                       │    │
│  │     ├─> /oauth2callback      OAuth callback                         │    │
│  │     ├─> /refresh/<user_id>   Refresh token                          │    │
│  │     └─> /status/<user_id>    Check auth status                      │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               │ Validate & Extract
                               │ (user_id, message, session_id, etc.)
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR                                        │
│            (backend/application/orchestrators/ai_chat_orchestrator.py)        │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      INTENT DETECTION                                 │  │
│  │                                                                        │  │
│  │  User Message:  "Schedule meeting tomorrow at 3pm"                    │  │
│  │                               │                                        │  │
│  │                   detect_intent(message)                              │  │
│  │                               │                                        │  │
│  │          ┌────────────────────┼─────────────────────────                  │  │
│  │          │                    │                    │                  │  │
│  │     "calendar"           "email"            "general"                 │  │
│  │    (keywords: schedule, (keywords: email,   (default)                │  │
│  │     meeting, event)      inbox, reply)                               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                               │                                              │
│                    Route to Domain Agent                                     │
│                               ▼                                              │
│  ┌────────────┬────────────────┬─────────────┬──────────────┐             │
│  │            │                │             │              │             │
│  │ AivisCore  │   Calendar     │   Gmail     │  Contacts    │             │
│  │   Agent    │    Agent       │   Agent     │   Agent      │             │
│  │            │                │             │              │             │
│  └────────────┴────────────────┴─────────────┴──────────────┘             │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               │ Agent Handles Request
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT LAYER                                          │
│              (backend/application/agents/*.py)                               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  🤖 AIVIS CORE AGENT                                                │    │
│  │     (General Productivity & Chat)                                   │    │
│  │                                                                      │    │
│  │     • General conversation                                           │    │
│  │     • Task planning & organization                                   │    │
│  │     • Text rewriting & summarization                                 │    │
│  │     • Memory retrieval (facts, context)                              │    │
│  │     • Productivity advice                                            │    │
│  │                                                                      │    │
│  │     Uses: LLMService + MemoryService                                 │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  📅 CALENDAR AGENT                                                   │    │
│  │     (Scheduling & Events)                                            │    │
│  │                                                                      │    │
│  │     • Natural language date/time parsing                             │    │
│  │       "tomorrow at 3pm" → 2025-12-29T15:00:00                        │    │
│  │     • Create calendar events                                         │    │
│  │     • List upcoming events                                           │    │
│  │     • Manage schedules                                               │    │
│  │                                                                      │    │
│  │     Uses: LLMService + calendar_manager tools                        │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  📧 GMAIL AGENT                                                      │    │
│  │     (Email Management)                                               │    │
│  │                                                                      │    │
│  │     • List & search emails                                           │    │
│  │     • Read & classify emails                                         │    │
│  │       (important, action_needed, informational, spam)                │    │
│  │     • Send & reply to emails                                         │    │
│  │     • Writing style analysis                                         │    │
│  │     • Draft generation in user's style                               │    │
│  │     • Email rewriting & polish                                       │    │
│  │                                                                      │    │
│  │     Uses: LLMService + GmailService + Gmail tools                    │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  👤 CONTACTS AGENT                                                   │    │
│  │     (Contact Management)                                             │    │
│  │                                                                      │    │
│  │     • Sync contacts from Gmail Sent                                  │    │
│  │     • List & search contacts                                         │    │
│  │     • Contact grouping (by person/company/category)                  │    │
│  │     • Update contact info (name, nickname, groups)                   │    │
│  │     • Contact detail & interaction history                           │    │
│  │     • Past conversation retrieval                                    │    │
│  │                                                                      │    │
│  │     Uses: ContactsService + LLMService                               │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               │ Call Services
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SERVICES LAYER                                       │
│         (backend/application/services/*, backend/services/*)                 │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  🧠 LLMService (llm_service.py)                                   │      │
│  │     OpenAI API wrapper                                            │      │
│  │                                                                    │      │
│  │     • chat_completion() - Chat with GPT models                    │      │
│  │     • chat_completion_text() - Get text response                  │      │
│  │     • generate_embedding() - Create embeddings                    │      │
│  │     • generate_embeddings_batch() - Batch embeddings              │      │
│  │                                                                    │      │
│  │     Model: gpt-4o-mini (configurable)                             │      │
│  │     Temperature: 0.3 | Max tokens: 768                            │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                               │                                              │
│                               ▼                                              │
│                         OpenAI API                                           │
│                   (chat.completions, embeddings)                             │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  💾 MemoryService (memory_service.py)                             │      │
│  │     Conversation & Facts Storage                                  │      │
│  │                                                                    │      │
│  │     MongoDB Operations:                                           │      │
│  │     • save_message() - Store chat messages                        │      │
│  │     • get_session_memory() - Retrieve conversation history        │      │
│  │                                                                    │      │
│  │     Pinecone Operations (Optional):                               │      │
│  │     • save_fact() - Store user facts as vectors                   │      │
│  │     • retrieve_facts() - Semantic search facts                    │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                               │                                              │
│                     ┌─────────┴─────────┐                                   │
│                     ▼                   ▼                                    │
│               MongoDB              Pinecone                                  │
│          (conversations,            (vector facts)                           │
│           contacts, tokens)                                                  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  📧 GmailService (gmail_service.py)                               │      │
│  │     Gmail API Operations                                          │      │
│  │                                                                    │      │
│  │     • get_thread_detail() - Get email thread                      │      │
│  │     • reply_to_thread() - Send reply                              │      │
│  │     • list_threads() - List emails                                │      │
│  │     • search_threads() - Search emails                            │      │
│  │     • classify_single_email() - Classify importance               │      │
│  │     • analyze_email_style() - Analyze writing style               │      │
│  │     • generate_reply_draft() - Draft in user's style              │      │
│  │     • rewrite_email_text() - Rewrite & polish                     │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                               │                                              │
│                               ▼                                              │
│                          Gmail API                                           │
│                    (messages, threads, send)                                 │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  👤 ContactsService (contacts_service.py)                         │      │
│  │     Contact Management                                            │      │
│  │                                                                    │      │
│  │     • sync_contacts() - Import from Gmail                         │      │
│  │     • list_contacts() - List all contacts                         │      │
│  │     • get_contact_detail() - Get contact info                     │      │
│  │     • update_contact() - Update contact                           │      │
│  │     • list_contact_groups() - List groups                         │      │
│  │     • get_contact_conversations() - Chat history                  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                               │                                              │
│                     ┌─────────┴─────────┐                                   │
│                     ▼                   ▼                                    │
│               MongoDB              Gmail API                                 │
│            (contacts DB)          (sent messages)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               │ OAuth & API Clients
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      UTILITY LAYER                                           │
│                    (backend/utils/*)                                           │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  🔧 google_api_helpers.py                                         │      │
│  │                                                                    │      │
│  │     • get_gmail_service(user_id)                                  │      │
│  │       └─> Loads OAuth → Builds Gmail API client                  │      │
│  │                                                                    │      │
│  │     • get_calendar_service(user_id)                               │      │
│  │       └─> Loads OAuth → Builds Calendar API client               │      │
│  │                                                                    │      │
│  │     • get_instagram_auth(user_id)                                 │      │
│  │       └─> Returns Instagram access token                          │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  📊 logging_utils.py                                              │      │
│  │                                                                    │      │
│  │     • get_logger(__name__) - Module-specific logger               │      │
│  │     • configure_logging() - Setup log format & level              │      │
│  │     • Colored output in dev, structured in prod                   │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  🔐 oauth_utils.py                                                │      │
│  │                                                                    │      │
│  │     • load_google_credentials(user_id)                            │      │
│  │     • save_google_credentials(user_id, creds)                     │      │
│  │     • require_google_auth() - Decorator for protected routes      │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DATABASE LAYER                                          │
│                    (backend/storage/sqlite_db.py)                            │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  MongoDB Collection Getters                                       │      │
│  │                                                                    │      │
│  │     • get_conversations_collection()                              │      │
│  │     • get_contacts_collection()                                   │      │
│  │     • get_tokens_collection() (OAuth)                             │      │
│  │     • get_calendar_events_collection()                            │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SYSTEMS                                     │
│                                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│  │  OpenAI    │  │  MongoDB   │  │  Google    │  │  Pinecone  │          │
│  │    API     │  │            │  │   APIs     │  │            │          │
│  ├────────────┤  ├────────────┤  ├────────────┤  ├────────────┤          │
│  │• GPT-4o    │  │• Convs     │  │• Gmail     │  │• Vector    │          │
│  │• Embedding │  │• Contacts  │  │• Calendar  │  │  Facts     │          │
│  │            │  │• Tokens    │  │• OAuth2    │  │            │          │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Example: Complete Request Flow

### Scenario: User asks to schedule a meeting

```
1. HTTP REQUEST
   POST /api/chat
   {
     "user_id": "user123",
     "message": "Schedule a meeting with John tomorrow at 3pm",
     "session_id": "session456"
   }

2. API LAYER (routes/chat_api.py)
   • Validates request
   • Extracts: user_id, message, session_id
   • Calls: orchestrator.handle_chat()

3. ORCHESTRATOR (orchestrator.py)
   • detect_intent("Schedule a meeting...")
   • Keywords detected: "schedule", "meeting"
   • Intent: "calendar"
   • Routes to: CalendarAgent

4. CALENDAR AGENT (calendar_agent.py)
   • handle_chat(user_id, message)
   • Calls: detect_calendar_requests(message)
   • Extracts: "meeting with John tomorrow at 3pm"
   • Parses: parse_datetime_from_text()
     └─> start: 2025-12-29T15:00:00
     └─> end: 2025-12-29T16:00:00

5. CALENDAR TOOLS (calendar_manager.py)
   • create_calendar_event(
       user_id="user123",
       summary="Meeting with John",
       start_time="2025-12-29T15:00:00",
       end_time="2025-12-29T16:00:00"
     )

6. GOOGLE API HELPER (google_api_helpers.py)
   • get_calendar_service(user_id)
   • Loads OAuth credentials from MongoDB
   • Builds Google Calendar API client

7. GOOGLE CALENDAR API
   • Creates event on user's calendar
   • Returns: event ID + confirmation

8. RESPONSE CHAIN (back up)
   Calendar Agent
     └─> "✅ I've scheduled 'Meeting with John' for December 29 at 3:00 PM"
   Orchestrator
     └─> Returns: { "reply": "✅ ...", "intent": "calendar" }
   API Layer
     └─> HTTP 200: { "reply": "✅ ..." }
   Client
     └─> Displays success message

Total latency: ~2-3 seconds
```

---

## 🔄 Data Flow Patterns

### Pattern 1: Chat with Memory
```
User Message
    ↓
Orchestrator → Intent: "general"
    ↓
AivisCoreAgent
    ↓
┌─────────────────┐
│ 1. Get Memory   │ ← MemoryService → MongoDB
│ 2. Build Context│   (last 20 messages)
│ 3. Call LLM     │ ← LLMService → OpenAI
│ 4. Save Reply   │ ← MemoryService → MongoDB
│ 5. Save Facts   │ ← MemoryService → Pinecone
└─────────────────┘
    ↓
Response
```

### Pattern 2: Email with Style Analysis
```
User: "Generate reply to thread XYZ"
    ↓
Orchestrator → Intent: "email"
    ↓
GmailAgent
    ↓
┌──────────────────────┐
│ 1. Get thread detail │ ← GmailService → Gmail API
│ 2. Analyze style     │ ← gmail_style tools
│    • Fetch 10 sent   │   (analyze user's writing)
│    • Extract patterns│
│ 3. Generate draft    │ ← LLMService → OpenAI
│    with user's style │
└──────────────────────┘
    ↓
Response: Draft email in user's style
```

### Pattern 3: Contact Sync
```
User: "Sync my contacts"
    ↓
Orchestrator → Intent: "general" → ContactsAgent
    ↓
ContactsAgent.sync()
    ↓
ContactsService
    ↓
┌────────────────────────┐
│ 1. Fetch Gmail Sent    │ ← Gmail API (1000 messages)
│ 2. Extract recipients  │
│ 3. Parse names/emails  │
│ 4. Group by person     │   (John@work.com, John@home.com)
│ 5. Group by company    │   (Company A employees)
│ 6. Categorize          │   (travel, food, events)
│ 7. Generate nicknames  │   ("John - Acme Corp")
│ 8. Upsert to MongoDB   │ ← MongoDB
└────────────────────────┘
    ↓
Response: Synced 247 contacts
```

---

## 🎯 Key Design Principles

1. **Separation of Concerns**
   - API: Routing & validation
   - Orchestrator: Intent detection
   - Agents: Business logic
   - Services: External APIs
   - Utils: Pure helpers

2. **Dependency Injection**
   - Services injected into agents
   - Testable and modular

3. **Single Responsibility**
   - Each component has one clear purpose
   - Easy to understand and maintain

4. **Centralized Configuration**
   - All settings in `config.py`
   - Environment-specific behavior

5. **Unified Logging**
   - Consistent format across modules
   - Easy debugging and monitoring

---

## ✨ Architecture Benefits

✅ **Scalable** - Easy to add new agents/services
✅ **Maintainable** - Clear structure and separation
✅ **Testable** - Dependency injection enables unit tests
✅ **Observable** - Unified logging throughout
✅ **Flexible** - Services can be swapped/mocked
✅ **Production-Ready** - Proper error handling & validation

