# Aivis - AI Personal Assistant

A comprehensive AI-powered personal assistant with email management, calendar integration, contact management, and **User Awareness** (memory + RAG).

## Features

- 🤖 **AI Chat**: Intelligent conversational interface
- 📧 **Gmail Integration**: Email management and automation
- 📅 **Calendar**: Google Calendar and Outlook integration
- 👥 **Contacts**: Contact management and sync
- 🧠 **User Awareness**: Memory system that learns from conversations and documents
- 📄 **Document RAG**: Upload documents and ask questions about them
- 💬 **Multi-channel**: WhatsApp, Email, Web Chat

## User Awareness System

The User Awareness system enables Aivis to respond like a real assistant who knows you:

- **Remembers** your preferences, work info, and identity
- **Learns** from past conversations automatically
- **Retrieves** relevant context from uploaded documents
- **Summarizes** conversation threads for long-term memory
- **Isolates** data per user for security

### Quick Start

1. **Set up environment variables** (see `.env.example`)
2. **Upload a document**:
   ```bash
   curl -X POST http://localhost:5000/memory/upload-file \
     -F "file=@document.pdf" \
     -F "user_id=your-user-id" \
     -F "title=My Document"
   ```
3. **Chat with context**:
   - Aivis will automatically use facts, summaries, and document content
   - No manual context injection needed

### Documentation

- **User Guide**: [docs/USER_AWARENESS.md](docs/USER_AWARENESS.md)
- **Testing Runbook**: [docs/RUNBOOK_USER_AWARENESS.md](docs/RUNBOOK_USER_AWARENESS.md)
- **System Architecture**: [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)

## Installation

### Prerequisites

- Python 3.10+
- MongoDB (local or Atlas)
- Pinecone account (for User Awareness)
- OpenAI API key

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd mental
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

4. **Run two processes** (core API and AI are separate):
   ```bash
   # Terminal 1 — orchestrator + LLM (default http://127.0.0.1:5055)
   python ai_chat_server.py

   # Terminal 2 — SQLite, webhooks, HTTP API including POST /api/chat
   cd backend
   python app.py
   ```

   - Core API: `http://localhost:5000` (set `PORT` with gunicorn / `start.sh`).
   - AI service: `http://localhost:5055` (set `AI_CHAT_PORT` or use `./start-ai.sh`).
   - Point the backend at the AI service with `AI_SERVICE_URL` if it is not on the default URL.

## Environment Variables

Key variables (see `env.example` for full list):

```bash
# Required
OPENAI_API_KEY=sk-...
# Core backend → AI service (defaults shown)
AI_SERVICE_URL=http://127.0.0.1:5055
AI_SERVICE_TIMEOUT=120
# Optional shared secret (set same value on both processes)
# AI_SERVICE_SECRET=...

MONGO_URI=mongodb://localhost:27017/

# User Awareness (optional but recommended)
PINECONE_API_KEY=your-key
PINECONE_INDEX_NAME=aivis-memory
PINECONE_ENV=us-east-1

# Google (for Gmail/Calendar)
GOOGLE_SECRET_FILE=google_client_secret.json
```

## API Endpoints

### Memory System

- `POST /memory/ingest-message` - Ingest a message
- `POST /memory/upload-file` - Upload and index a document
- `GET /memory/context` - Get context bundle (debug)
- `GET /memory/facts` - List user facts
- `POST /memory/facts` - Add a fact
- `DELETE /memory/facts/<id>` - Delete a fact
- `GET /memory/threads/<id>/summary` - Get thread summary

### Chat & Email

- `POST /api/chat` - Chat endpoint
- `GET /api/gmail/threads` - List email threads
- `POST /api/gmail/send` - Send email
- `POST /api/gmail/reply` - Reply to thread

### Calendar & Contacts

- `GET /api/calendar/events` - List events
- `POST /api/calendar/events` - Create event
- `GET /api/contacts` - List contacts
- `POST /api/contacts` - Add contact

## Project Structure

```
mental/
├── app/
│   ├── memory/              # User Awareness system
│   │   ├── models.py        # Data models
│   │   ├── vector_store.py  # Pinecone interface
│   │   ├── ingestion_service.py
│   │   ├── memory_gate.py   # Fact curation
│   │   ├── retrieval_service.py
│   │   ├── prompt_builder.py
│   │   └── background_jobs.py
│   ├── api/                 # Legacy / optional Flask routes (if present)
│   │   └── ...
│   ├── services/            # Business logic
│   ├── agents/              # AI agents
│   └── tools/               # Tool implementations
├── tests/
│   └── test_memory_system.py
├── docs/
│   ├── USER_AWARENESS.md
│   └── RUNBOOK_USER_AWARENESS.md
├── ai_chat_server.py        # AI chat service (Flask; orchestrator, port 5055)
├── backend/app.py           # Core API (Flask)
└── requirements.txt
```

## Testing

### Run Unit Tests

```bash
pytest tests/test_memory_system.py -v
```

### Manual Testing

See [docs/RUNBOOK_USER_AWARENESS.md](docs/RUNBOOK_USER_AWARENESS.md) for step-by-step testing guide.

## Architecture

### User Awareness Flow

```
Message/File → Ingestion → Memory Gate → Vector Store
                                ↓
                            MongoDB
                                ↓
Query → Retrieval → Context Bundle → Prompt Builder → LLM
```

### Key Technologies

- **Backend**: Flask (Python)
- **Database**: MongoDB
- **Vector DB**: Pinecone
- **LLM**: OpenAI GPT-4
- **Embeddings**: OpenAI text-embedding-ada-002

## Security

- **User Isolation**: Pinecone namespaces per user_id
- **Fact Curation**: Only stable facts stored, not transient emotions
- **API Security**: user_id required for all memory operations
- **Soft Deletes**: Facts can be deactivated, not permanently deleted

## Performance

### Token Control

- Max 10 facts per query
- Max 5 thread summaries
- Max 8 document chunks
- Max 20 recent messages

### Background Processing

- Fact extraction: async (doesn't block)
- Thread summarization: every 5 messages
- Document indexing: async

## Troubleshooting

### Pinecone Not Connecting

```bash
# Verify API key
echo $PINECONE_API_KEY

# Check index exists in Pinecone console
```

### Facts Not Extracted

```bash
# Check logs
tail -f logs/app.log | grep "fact"

# Add fact manually
curl -X POST http://localhost:5000/memory/facts \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "text": "Test fact", "type": "other", "confidence": 0.9}'
```

### Document Upload Fails

```bash
# Install document parsers
pip install PyPDF2 python-docx

# Check upload folder
mkdir -p uploads
chmod 755 uploads
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

[Your License Here]

## Support

For issues or questions:
- Documentation: `docs/`
- Issues: GitHub Issues
- Email: [your-email]

## Roadmap

- [ ] Celery/RQ for production background jobs
- [ ] More document types (Markdown, HTML)
- [ ] Fact confidence decay over time
- [ ] User feedback loop for fact validation
- [ ] Shared/team knowledge bases
- [ ] Google Drive and Notion integration
- [ ] WhatsApp webhook integration
- [ ] Voice interface

## Acknowledgments

Built with:
- Flask
- MongoDB
- Pinecone
- OpenAI
- And many other great open-source libraries

