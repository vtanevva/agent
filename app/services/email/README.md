# Email Service Architecture

This directory implements a unified email service that supports both Gmail and Outlook providers.

## Structure

```
app/services/email/
├── __init__.py              # Exports
├── base_provider.py          # Abstract base class for email providers
├── gmail_provider.py         # Gmail implementation
├── outlook_provider.py        # Outlook implementation
├── unified_service.py        # Unified service that routes to providers
└── common.py                 # Shared utilities (contact lookup, normalization, storage)
```

## Key Features

1. **Provider Pattern**: Each provider (Gmail, Outlook) implements the `EmailProvider` interface
2. **Unified Service**: Single interface for tools/agents to use, automatically routes to correct provider
3. **Source Tracking**: All emails stored in `emails` collection include `source` field ("gmail" or "outlook")
4. **Shared Utilities**: Common functions in `common.py` avoid code duplication

## Usage

### From Tools

```python
from app.services.email.unified_service import list_recent_emails, send_email

# List emails (uses default provider)
result = list_recent_emails(user_id="user123", max_results=5)

# List from specific provider
result = list_recent_emails(user_id="user123", max_results=5, provider="outlook")

# List from all providers (unified inbox)
result = list_recent_emails(user_id="user123", max_results=5, unified=True)
```

### Provider Detection

The unified service automatically detects the provider:
1. If `provider` parameter is specified, uses that
2. If not specified, checks stored email metadata for `source` field
3. Falls back to user's default provider setting
4. Default is "gmail" if no setting exists

## Database Schema

Emails are stored in the `emails` collection with the following structure:

```python
{
    "user_id": "user123",
    "thread_id": "thread_abc",
    "source": "gmail",  # or "outlook"
    "from": "Name <email@example.com>",
    "subject": "Email subject",
    "snippet": "Preview text...",
    "category": "important",
    "scores": {...},
    "classified_at": "2024-01-01T00:00:00",
    "classification_version": "3.0",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}
```

**Important**: The compound key is `(user_id, thread_id, source)` - same thread can exist in both providers.

## Adding a New Provider

1. Create `new_provider.py` that extends `EmailProvider`
2. Implement all abstract methods
3. Add provider to `unified_service.py`:
   - Add to `_get_provider()` function
   - Add to `_get_all_providers()` function
   - Add connection check to `check_user_email_connections()`

## Notes

- Gmail uses `threadId` (conversation grouping)
- Outlook uses `conversationId` (similar concept)
- The `common.normalize_email_format()` function converts both to common format with `threadId` field
- Outlook `conversationId` is mapped to `threadId` in normalized format



