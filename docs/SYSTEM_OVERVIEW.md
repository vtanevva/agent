# Aivis - AI Productivity Assistant System Overview

## System Purpose
- AI-powered personal productivity assistant that helps users manage email, calendar, contacts, and general tasks
- Provides context-aware responses through a memory system that learns from user interactions
- Multi-channel support (Web, Mobile App via Expo, Email)
- Memory system supports WhatsApp channel type (integration ready but not implemented)

## Core Features

### AI Chat & Orchestration
- **Intelligent routing**: Orchestrator agent routes requests to domain-specific agents (email, calendar, contacts, general chat)
- **Intent detection**: Uses LLM-based and keyword-based detection to identify user intent (calendar, email, contacts, general)
- **Context-aware responses**: Integrates user memory, preferences, and document knowledge into responses

### Email Management (Gmail/Outlook)
- **Multi-provider support**: Google Gmail and Microsoft Outlook integration via OAuth2
- **Email operations**: List, send, reply, forward emails; view thread details
- **Contact resolution**: Resolves nicknames/names to email addresses from contact database
- **Style analysis**: Analyzes user's email writing style to generate contextually appropriate replies
- **Email classification**: Categorizes emails (work, personal, travel, etc.) automatically

### Calendar Management
- **Multi-calendar support**: Google Calendar and Microsoft Outlook integration
- **Event operations**: Create, view, update, delete calendar events
- **Natural language parsing**: Understands natural language date/time expressions
- **Conflict detection**: Identifies scheduling conflicts when creating events

### Contact Management
- **Automatic contact sync**: Extracts contacts from sent emails and groups by person/company
- **Smart categorization**: Auto-categorizes contacts (travel, food, events, housing) based on email domain
- **Nickname generation**: Creates readable nicknames like "John - Acme Corp"
- **Contact groups**: Organizes contacts into groups for easy filtering
- **Relationship tracking**: Extracts and stores relationship context from conversations

### User Awareness Memory System
- **Fact extraction**: Automatically extracts stable facts about users (preferences, identity, work info, relationships)
- **Memory gate**: Curates and validates facts - only stores long-term stable information, filters out transient emotions
- **Vector storage**: Uses Pinecone for semantic search of user facts and documents
- **Document RAG**: Upload and index documents (PDF, DOCX, TXT) for context retrieval
- **Thread summarization**: Automatically summarizes long conversation threads for long-term memory
- **Context retrieval**: Retrieves relevant facts, summaries, and document chunks for each conversation
- **User isolation**: Secure per-user data isolation using Pinecone namespaces

## Architecture

### Application Stack
- **Backend**: Flask (Python) REST API with blueprint-based routing
- **Frontend**: React Native/Expo web app with React Navigation
- **Database**: MongoDB for structured data (conversations, contacts, facts, documents)
- **Vector Database**: Pinecone for semantic search and embeddings
- **LLM**: OpenAI GPT-4 (configurable model: gpt-4o-mini by default)
- **Embeddings**: OpenAI text-embedding-ada-002

### Agent Architecture
- **Orchestrator**: Main routing agent that distributes requests to domain agents
- **AivisCore Agent**: Handles general productivity tasks, chat, and advice
- **Gmail Agent**: Specialized email operations handler
- **Calendar Agent**: Calendar event management handler
- **Contacts Agent**: Contact management operations handler

### Data Flow
1. **Request → API Routes** (Flask blueprints)
2. **API → Orchestrator** (intent detection and routing)
3. **Orchestrator → Domain Agent** (specialized handler)
4. **Agent → Services** (LLM, Memory, Gmail, Calendar services)
5. **Services → External APIs** (OpenAI, Gmail API, Calendar API, MongoDB, Pinecone)

### Memory System Components
- **Ingestion Service**: Processes messages and documents, extracts facts
- **Memory Gate**: Curates and validates facts before storage
- **Retrieval Service**: Retrieves relevant context (facts, summaries, documents) for prompts
- **Vector Store**: Manages Pinecone embeddings and semantic search
- **Prompt Builder**: Constructs context-aware prompts with retrieved memories

## Integration & OAuth

### OAuth2 Integration
- **Google OAuth**: Gmail, Google Calendar access with refresh token management
- **Microsoft OAuth**: Outlook email and calendar access
- **Secure credential storage**: Encrypted storage of OAuth tokens per user
- **Token refresh**: Automatic token refresh handling

### External Services
- **Gmail API**: Email reading, sending, threading
- **Calendar API**: Google Calendar and Microsoft Graph API
- **OpenAI API**: Chat completions and embeddings
- **Pinecone**: Vector similarity search
- **MongoDB**: Document storage and retrieval

## Security & Performance

### Security Features
- **User isolation**: All data is isolated per user_id (Pinecone namespaces, MongoDB queries)
- **OAuth security**: Secure token storage and refresh handling
- **Rate limiting**: Configurable rate limits for cost control (default: 10 requests/minute)
- **Input validation**: Comprehensive validation for all API inputs
- **Soft deletes**: Facts can be deactivated without permanent deletion

### Performance Optimizations
- **Token control**: Limits on facts (10), summaries (5), document chunks (8), recent messages (20)
- **Background processing**: Async fact extraction and thread summarization
- **Caching**: Session memory caching for frequently accessed data
- **Lazy initialization**: Services initialized on first use to prevent startup delays

## Configuration & Deployment

### Environment Configuration
- **Development/Production modes**: Environment-specific behavior and validation
- **Feature flags**: Configurable features (memory, RAG, AutoGen)
- **Service configuration**: Centralized config management with validation
- **Logging**: Structured logging with configurable levels

### Deployment
- **Docker support**: Dockerfile included for containerized deployment
- **Railway ready**: Railway.toml configuration for Railway deployment
- **Health checks**: `/health` endpoint for monitoring
- **Static file serving**: Serves Expo web build for frontend

## Background Jobs & Automation

### Background Processing
- **Fact extraction**: Automatic extraction from messages and emails
- **Thread summarization**: Periodic summarization of long threads (every 5 messages)
- **Document indexing**: Async document processing and chunking
- **Email classification**: Background classification of emails on user login
- **Contact sync**: Background contact extraction from email history

### Automation Features
- **Email watching**: Gmail push notifications for real-time email processing
- **Initial setup**: Automatic backfill of facts, contacts, and email classification on first login
- **Relationship extraction**: Automatic relationship detection from conversations

