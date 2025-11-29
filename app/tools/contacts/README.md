# Contact Tools

Contact tools provide a clean interface for agents to interact with contacts.

## Architecture

```
Agent (contacts_agent.py)
    ↓
Tool (app/tools/contacts/*.py)
    ↓
Service (app/services/contacts_service.py)
    ↓
Database (MongoDB)
```

## Tools

### `sync_contacts`
Sync contacts from Gmail sent messages.

**Usage:**
```python
from app.tools.contacts import sync_contacts

result_json = sync_contacts(
    user_id="user123",
    max_sent=1000,
    force=False
)

result = json.loads(result_json)
```

### `list_contacts`
List user's contacts.

**Usage:**
```python
from app.tools.contacts import list_contacts

result_json = list_contacts(
    user_id="user123",
    include_archived=False
)

result = json.loads(result_json)
```

### `update_contact`
Update a contact's information.

**Usage:**
```python
from app.tools.contacts import update_contact

result_json = update_contact(
    user_id="user123",
    email="contact@example.com",
    name="John Doe",
    nickname="John",
    groups=["Work", "Important"]
)

result = json.loads(result_json)
```

### `normalize_contact_names`
Normalize contact names (fill missing names from email addresses).

**Usage:**
```python
from app.tools.contacts import normalize_contact_names

result_json = normalize_contact_names(user_id="user123")
result = json.loads(result_json)
```

### `archive_contact`
Archive or unarchive a contact.

**Usage:**
```python
from app.tools.contacts import archive_contact

result_json = archive_contact(
    user_id="user123",
    email="contact@example.com",
    archived=True
)

result = json.loads(result_json)
```

### `list_contact_groups`
List all contact groups.

**Usage:**
```python
from app.tools.contacts import list_contact_groups

result_json = list_contact_groups(user_id="user123")
result = json.loads(result_json)
```

### `get_contact_detail`
Get detailed information about a contact.

**Usage:**
```python
from app.tools.contacts import get_contact_detail

result_json = get_contact_detail(
    user_id="user123",
    email="contact@example.com"
)

result = json.loads(result_json)
```

### `get_contact_conversations`
Get email conversations with a contact.

**Usage:**
```python
from app.tools.contacts import get_contact_conversations

result_json = get_contact_conversations(
    user_id="user123",
    email="contact@example.com",
    max_results=50
)

result = json.loads(result_json)
```

## File Structure

```
app/tools/contacts/
├── __init__.py          # Exports all tools
├── sync.py              # Sync contacts from Gmail
├── list.py              # List contacts
├── update.py            # Update, normalize, archive contacts
├── groups.py            # List contact groups
├── detail.py            # Get contact details and conversations
└── README.md            # This file
```

## Migration Notes

**Old imports:**
```python
from app.services.contacts_service import (
    sync_contacts,
    list_contacts,
    update_contact,
    ...
)
```

**New imports:**
```python
from app.tools.contacts import (
    sync_contacts,
    list_contacts,
    update_contact,
    normalize_contact_names,
    archive_contact,
    list_contact_groups,
    get_contact_detail,
    get_contact_conversations,
)
```

## Benefits

- ✅ **Organized structure** - All contact tools in one place
- ✅ **Consistent with calendar/email** - Same architecture pattern
- ✅ **Easy imports** - Single import statement for all tools
- ✅ **JSON responses** - Standardized format for all tools
- ✅ **Better maintainability** - Clear separation of concerns

