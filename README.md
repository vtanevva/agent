# Mental Health AI Assistant

A sophisticated AI-powered mental health chatbot with emotion detection, memory management, and integration with external services like Gmail and Instagram.

## 🌟 Features

- **AI-Powered Conversations**: GPT-4 powered chat with personalized responses
- **Emotion Detection**: Real-time emotion analysis using BERT
- **Suicide Prevention**: Automatic detection of concerning content with crisis resources
- **Memory Management**: Long-term conversation memory using Pinecone embeddings
- **Gmail Integration**: Send, read, and reply to emails
- **Instagram DM Support**: Manage Instagram direct messages
- **Voice Chat**: Speech-to-text and text-to-speech capabilities
- **Session Management**: Persistent conversation history
- **RAG (Retrieval-Augmented Generation)**: Context-aware responses using psychological knowledge base

## 🏗️ Architecture

```
mental/
├── app/                    # Core application logic
│   ├── agent_core/        # AI agent framework
│   ├── tools/             # External service integrations
│   ├── chatbot.py         # Main chat logic
│   ├── emotion_detection.py # Emotion analysis
│   ├── embeddings.py      # Vector embeddings
│   └── memory.py          # Memory management
├── my-chatbot/            # React frontend
├── server.py              # Flask API server
└── Dockerfile             # Container configuration
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB (optional, for production)
- Pinecone account (optional, for memory features)

### Environment Variables

Create a `.env` file:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key
FLASK_SECRET_KEY=your_secret_key

# Database (optional for development)
MONGO_URI=mongodb://localhost:27017/mentalassistant
MONGO_DB_NAME=mentalassistant

# Pinecone (optional)
PINECONE_API_KEY=your_pinecone_key
PINECONE_INDEX_NAME=mental-chat

# Google OAuth (optional)
GOOGLE_SECRET_FILE=google_client_secret.json

# Instagram OAuth (optional)
IG_APP_ID=your_instagram_app_id
IG_APP_SECRET=your_instagram_secret
```

### Installation

1. **Clone and setup Python environment:**
```bash
git clone <repository>
cd mental
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Setup frontend:**
```bash
cd my-chatbot
npm install
npm run build
cd ..
```

3. **Run the application:**
```bash
python server.py
```

The app will be available at `http://localhost:10000`

### Docker Deployment

```bash
docker build -t mental-health-ai .
docker run -p 10000:10000 --env-file .env mental-health-ai
```

## 🔧 Configuration

### Development Mode
- Runs without MongoDB (offline mode)
- Uses local file storage for tokens
- Debug logging enabled

### Production Mode
- Requires MongoDB connection
- Secure session management
- Error monitoring and logging

## 🛡️ Security Features

- **OAuth 2.0**: Secure authentication with Google and Instagram
- **Token Encryption**: Secure storage of OAuth tokens
- **Input Validation**: Sanitized user inputs
- **Rate Limiting**: API request throttling
- **CORS Protection**: Cross-origin request security

## 🧠 AI Capabilities

### Emotion Detection
- Uses BERT-based emotion classification
- Detects 6 emotions: joy, sadness, anger, fear, surprise, neutral
- Suicide risk assessment with crisis resources

### Memory System
- **Short-term**: Session-based conversation memory
- **Long-term**: Fact extraction and storage using embeddings
- **Contextual**: RAG-based responses using psychological knowledge

### Tool Integration
- **Gmail**: Send emails, read inbox, reply to threads
- **Instagram**: List and send direct messages
- **Calendar**: Event management (planned)

## 📊 Monitoring & Logging

- Structured logging with different levels
- Error tracking and reporting
- Performance metrics
- User interaction analytics

## 🔄 API Endpoints

- `POST /api/chat` - Main chat endpoint
- `GET /api/sessions` - List user sessions
- `GET /api/sessions/<session_id>` - Get session history
- `GET /google/auth` - Google OAuth initiation
- `GET /google/callback` - Google OAuth callback
- `GET /instagram/auth` - Instagram OAuth initiation
- `GET /instagram/callback` - Instagram OAuth callback

## 🧪 Testing

```bash
# Run backend tests
python -m pytest tests/

# Run frontend tests
cd my-chatbot
npm test
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Important Notes

- **Mental Health Disclaimer**: This is not a replacement for professional mental health care
- **Crisis Resources**: Always provide crisis hotline information for users in distress
- **Privacy**: User data is encrypted and stored securely
- **Compliance**: Follow local data protection regulations (GDPR, HIPAA, etc.)

## 🆘 Crisis Resources

- **International**: https://findahelpline.com/
- **Netherlands**: 113 Zelfmoordpreventie - 0800-0113
- **US**: National Suicide Prevention Lifeline - 988
- **UK**: Samaritans - 116 123

## 📞 Support

For technical support or questions about the application, please open an issue on GitHub.