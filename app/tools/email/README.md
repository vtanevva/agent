# Email Tools

Email tools provide a clean interface for agents to interact with Gmail.

## Architecture

```
Agent (gmail_agent.py)
    ↓
Tool (app/tools/email/*.py)
    ↓
Service (app/services/gmail_service.py)
    ↓
Gmail API
```

## Tools

### `list_recent_emails`
Lists the user's most recent received emails.

**Usage:**
```python
from app.tools.email import list_recent_emails

emails = list_recent_emails(user_id="user123", max_results=20)
# Returns JSON array of email threads
```

### `get_thread_detail`
Gets full content and headers for an email thread.

**Usage:**
```python
from app.tools.email import get_thread_detail

detail = get_thread_detail(user_id="user123", thread_id="abc123")
# Returns JSON with full thread content
```

### `reply_email`
Sends a reply inside an existing Gmail thread.

**Usage:**
```python
from app.tools.email import reply_email

result = reply_email(
    user_id="user123",
    thread_id="abc123",
    to="recipient@example.com",
    body="Reply message here",
    subj_prefix="Re:"
)
```

### `send_email`
Sends a new email (compose).

**Usage:**
```python
from app.tools.email import send_email

result = send_email(
    user_id="user123",
    to="recipient@example.com",
    subject="Hello",
    body="Email body here"
)
```

### `analyze_email_style`
Analyzes user's email writing style from their sent emails.

**Usage:**
```python
from app.tools.email import analyze_email_style

style_json = analyze_email_style(user_id="user123", max_samples=10)
# Returns JSON string with style analysis
```

### `generate_reply_draft`
Generates a reply draft matching user's writing style.

**Usage:**
```python
from app.tools.email import generate_reply_draft

draft = generate_reply_draft(
    user_id="user123",
    original_email="Original email content",
    context="Additional context"
)
```

### `classify_email`
Classifies emails into categories (urgent, waiting_for_reply, etc.).

**Usage:**
```python
from app.tools.email import classify_email, CLASSIFICATION_VERSION

classification = classify_email(
    email_data={
        "subject": "Meeting tomorrow",
        "body": "Can we meet?",
        "from": "colleague@example.com"
    },
    user_id="user123"
)
# Returns: {"category": "action_items", "scores": {...}}
```

## File Structure

```
app/tools/email/
├── __init__.py          # Exports all tools
├── list.py              # List emails (gmail_list.py)
├── detail.py            # Get thread details (gmail_detail.py)
├── reply.py             # Reply to emails (gmail_reply.py)
├── send.py              # Send new emails (gmail_mail.py)
├── style.py             # Style analysis (gmail_style.py)
├── classifier.py        # Email classification (email_classifier.py)
└── README.md            # This file
```

## Migration Notes

**Old imports:**
```python
from app.tools.gmail_list import list_recent_emails
from app.tools.gmail_detail import get_thread_detail
from app.tools.gmail_reply import reply_email
from app.tools.gmail_mail import send_email
from app.tools.gmail_style import analyze_email_style
from app.tools.email_classifier import classify_email
```

**New imports:**
```python
from app.tools.email import (
    list_recent_emails,
    get_thread_detail,
    reply_email,
    send_email,
    analyze_email_style,
    classify_email,
)
```

## Benefits

- ✅ **Organized structure** - All email tools in one place
- ✅ **Consistent naming** - Clear, descriptive file names
- ✅ **Easy imports** - Single import statement for all tools
- ✅ **Better maintainability** - Clear separation of concerns

