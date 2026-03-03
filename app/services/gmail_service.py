from __future__ import annotations

import threading
import ssl
import httplib2
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from app.database import get_db
from app.tools.email import (
    classify_email,
    CLASSIFICATION_VERSION,
    get_thread_detail as tool_get_thread_detail,
    _extract_plain_text,
    send_email as tool_send_email,
    reply_email as tool_reply_email,
    analyze_email_style,
    generate_reply_draft,
)
from app.tools.email.extract_todos import extract_todos_from_thread as tool_extract_todos_from_thread
from app.tools.email.forward import forward_email as tool_forward_email
from app.utils.oauth_utils import load_google_credentials


def _build_gmail_service(creds):
    """Build Gmail API service with SSL error handling for Windows."""
    try:
        # Try standard build first
        return build("gmail", "v1", credentials=creds)
    except (ssl.SSLError, Exception) as e:
        print(f"[INFO] Standard Gmail API build failed, trying with custom HTTP: {e}", flush=True)
        try:
            # Create custom HTTP client with relaxed SSL (for Windows issues)
            http = httplib2.Http()
            http = creds.authorize(http)
            return build("gmail", "v1", http=http)
        except Exception as e2:
            print(f"[ERROR] Gmail API build failed with custom HTTP: {e2}", flush=True)
            # Fallback to standard build (will fail, but with proper error)
            return build("gmail", "v1", credentials=creds)


def extract_facts_from_email(user_id: str, email_data: Dict[str, Any]) -> None:
    """
    Extract facts from email content WITHOUT storing the full email body.
    
    This runs in background and only stores extracted facts (preferences, context, etc.)
    Privacy-friendly: Full email content is never stored in memory system.
    
    Args:
        user_id: User identifier
        email_data: Email data with 'subject', 'body', 'from', 'to' fields
    """
    def _background_extract():
        try:
            thread_id = email_data.get('thread_id', 'unknown')
            source_ref = f"email:{thread_id}"
            
            # OPTIMIZATION: Check if this thread was already processed
            # Skip expensive LLM call if facts already exist for this thread
            from app.memory.models import get_memory_facts_collection
            facts_col = get_memory_facts_collection()
            
            if facts_col is not None:
                # Check if facts already exist for this thread
                existing_facts_for_thread = facts_col.find_one({
                    "user_id": user_id,
                    "source_ref": source_ref,
                    "is_active": True
                })
                
                if existing_facts_for_thread:
                    # Thread already processed - skip LLM call
                    print(f"[SKIP] Thread {thread_id} already processed, skipping fact extraction", flush=True)
                    # Still do relationship and project tracking (cheap operations)
                    skip_fact_extraction = True
                else:
                    skip_fact_extraction = False
            else:
                skip_fact_extraction = False
            
            # Extract facts from ALL email categories
            # (User preference: no filtering, extract from everything)
            from app.memory.memory_gate import get_memory_gate
            
            # Build context text for fact extraction (NOT stored, only used for extraction)
            subject = email_data.get('subject', '')
            body = email_data.get('body', '')[:2000]  # Limit to 2000 chars for cost control
            sender = email_data.get('from', '')
            
            # Create extraction context (analyze content without storing it)
            extraction_text = f"Subject: {subject}\n\nFrom: {sender}\n\nContent: {body}"
            
            # Extract facts using memory gate (skip if already processed)
            if not skip_fact_extraction:
                gate = get_memory_gate()
                candidate_facts = gate.extract_candidate_facts(
                    text=extraction_text,
                    user_id=user_id,
                    source_ref=source_ref,
                )
            else:
                candidate_facts = []
            
            if candidate_facts:
                # Get existing facts for deduplication
                # facts_col already defined above
                if facts_col is not None:
                    existing_facts = list(facts_col.find({
                        "user_id": user_id,
                        "is_active": True
                    }))
                    
                    # Deduplicate
                    unique_facts = gate.deduplicate_facts(candidate_facts, existing_facts)
                    
                    if unique_facts:
                        # Store unique facts in MongoDB and track fact IDs
                        stored_count = gate.store_facts(user_id, unique_facts)
                        stored_fact_ids = []
                        
                        if stored_count > 0:
                            # Get fact IDs that were just stored (by source_ref)
                            if facts_col is not None:
                                stored_facts = list(facts_col.find({
                                    "user_id": user_id,
                                    "source_ref": source_ref,
                                    "is_active": True
                                }, {"_id": 1}).sort("created_at", -1).limit(stored_count))
                                stored_fact_ids = [fact["_id"] for fact in stored_facts]
                            
                            # Embed facts to Pinecone for semantic search
                            from app.memory.vector_store import get_vector_store
                            vector_store = get_vector_store()
                            
                            vectors = []
                            for i, fact in enumerate(unique_facts):
                                fact_id = stored_fact_ids[i] if i < len(stored_fact_ids) else f"fact_{user_id}_{hash(fact.text)}"
                                vectors.append({
                                    "id": fact_id,
                                    "text": fact.text,
                                    "metadata": {
                                        "fact_type": fact.fact_type.value,
                                        "confidence": fact.confidence,
                                        "source": "email"
                                    }
                                })
                            
                            if vectors:
                                vector_store.upsert_vectors(
                                    user_id=user_id,
                                    vectors=vectors,
                                    vector_type="fact"
                                )
                            
                            print(f"📧 Extracted and embedded {stored_count} facts from email (user: {user_id})", flush=True)
                            
                            # Link facts to relationships (will be done after facts are stored, see below)
            
            # ===== RELATIONSHIP TRACKING =====
            # Use RelationshipsService for clean separation of concerns
            try:
                from app.services.relationships_service import get_relationships_service
                
                relationships_service = get_relationships_service()
                result = relationships_service.process_email(user_id, email_data)
                
                recipient_emails = result.get("tracked_emails", [])
                email_sent_by_user = result.get("email_sent_by_user", False)
                
            except Exception as e:
                print(f"[WARNING] Relationship tracking failed: {e}", flush=True)
                recipient_emails = []
                email_sent_by_user = False
            
            # ===== TASK LINKING TO RELATIONSHIPS =====
            # Link tasks from this thread to relationships
            try:
                from app.memory.models import get_tasks_collection
                from app.services.relationships_service import get_relationships_service
                
                relationships_service = get_relationships_service()
                
                if thread_id:
                    # Find tasks created from this thread
                    tasks_col = get_tasks_collection()
                    if tasks_col is not None:
                        thread_tasks = list(tasks_col.find({
                            "user_id": user_id,
                            "source": "email",
                            "source_ref": thread_id
                        }, {"_id": 1}))
                        
                        task_ids = [task["_id"] for task in thread_tasks]
                        
                        if task_ids:
                            # Link tasks to recipients (if email was sent) or sender (if relationship exists)
                            if email_sent_by_user and recipient_emails:
                                # Email was sent - link tasks to recipients
                                for recipient_email in recipient_emails:
                                    relationships_service.link_tasks(user_id, recipient_email, task_ids)
                                    print(f"[RELATIONSHIP] Linked {len(task_ids)} tasks to relationship with {recipient_email}", flush=True)
                            elif not email_sent_by_user and recipient_emails:
                                # Email was received - link tasks to sender if relationship exists
                                # recipient_emails will contain sender if relationship was updated
                                sender_email = recipient_emails[0]
                                relationships_service.link_tasks(user_id, sender_email, task_ids)
                                print(f"[RELATIONSHIP] Linked {len(task_ids)} tasks to existing relationship with {sender_email}", flush=True)
            except Exception as e:
                print(f"[WARNING] Task linking to relationships failed: {e}", flush=True)
            
            # ===== FACT LINKING TO RELATIONSHIPS =====
            # Link facts from this thread to relationships
            try:
                from app.services.relationships_service import get_relationships_service
                
                relationships_service = get_relationships_service()
                
                if thread_id and facts_col is not None:
                    # Find facts created from this thread
                    source_ref = f"email:{thread_id}"
                    thread_facts = list(facts_col.find({
                        "user_id": user_id,
                        "source_ref": source_ref,
                        "is_active": True
                    }, {"_id": 1}))
                    
                    fact_ids = [fact["_id"] for fact in thread_facts]
                    
                    if fact_ids:
                        # Link facts to recipients (if email was sent) or sender (if relationship exists)
                        if email_sent_by_user and recipient_emails:
                            # Email was sent - link facts to recipients
                            for recipient_email in recipient_emails:
                                relationships_service.link_facts(user_id, recipient_email, fact_ids)
                                print(f"[RELATIONSHIP] Linked {len(fact_ids)} facts to relationship with {recipient_email}", flush=True)
                        elif not email_sent_by_user and recipient_emails:
                            # Email was received - link facts to sender if relationship exists
                            # recipient_emails will contain sender if relationship was updated
                            sender_email = recipient_emails[0]
                            relationships_service.link_facts(user_id, sender_email, fact_ids)
                            print(f"[RELATIONSHIP] Linked {len(fact_ids)} facts to existing relationship with {sender_email}", flush=True)
            except Exception as e:
                print(f"[WARNING] Fact linking to relationships failed: {e}", flush=True)
            
            # ===== PROJECT LINKING =====
            # Check if thread relates to existing project, or create new one
            try:
                from app.memory.models import get_projects_collection
                from uuid import uuid4
                
                projects_col = get_projects_collection()
                thread_id = email_data.get('thread_id')
                subject = email_data.get('subject', '')
                
                if projects_col is not None and thread_id:
                    # Check if thread already linked to project
                    existing_project = projects_col.find_one({
                        "user_id": user_id,
                        "related_threads": thread_id
                    })
                    
                    if not existing_project:
                        # Check if subject suggests a project (contains keywords)
                        project_keywords = ["project", "launch", "initiative", "campaign", "feature", "release", "sprint", "milestone"]
                        subject_lower = subject.lower()
                        
                        if any(keyword in subject_lower for keyword in project_keywords):
                            # Create or update project
                            project_name = subject[:100]  # Use subject as project name
                            
                            result = projects_col.update_one(
                                {
                                    "user_id": user_id,
                                    "name": project_name
                                },
                                {
                                    "$addToSet": {"related_threads": thread_id},
                                    "$set": {
                                        "last_activity": datetime.utcnow(),
                                        "updated_at": datetime.utcnow()
                                    },
                                    "$setOnInsert": {
                                        "_id": str(uuid4()),
                                        "user_id": user_id,
                                        "name": project_name,
                                        "status": "active",
                                        "created_at": datetime.utcnow()
                                    }
                                },
                                upsert=True
                            )
                            
                            # Log project creation/update
                            if result.upserted_id:
                                print(f"[PROJECT] Created new project '{project_name}' and linked thread {thread_id}", flush=True)
                            else:
                                print(f"[PROJECT] Updated existing project '{project_name}' and linked thread {thread_id}", flush=True)
                            
                            # Also link recipient(s) to project if we have relationships (from sent emails)
                            try:
                                from app.services.relationships_service import get_relationships_service
                                
                                relationships_service = get_relationships_service()
                                
                                if recipient_emails:
                                    # Link all recipients to the project
                                    for recipient_email in recipient_emails:
                                        relationships_service.link_project(user_id, recipient_email, project_name)
                                        print(f"[PROJECT] Linked recipient {recipient_email} to project '{project_name}'", flush=True)
                            except Exception as e:
                                print(f"[WARNING] Failed to link recipient to project: {e}", flush=True)
                        else:
                            # Log why project wasn't created
                            print(f"[PROJECT] Subject '{subject[:60]}' does not contain project keywords", flush=True)
                    else:
                        print(f"[PROJECT] Thread {thread_id} already linked to project '{existing_project.get('name', 'unnamed')}'", flush=True)
            except Exception as e:
                print(f"[WARNING] Project linking failed: {e}", flush=True)
                import traceback
                traceback.print_exc()
                            
        except Exception as e:
            print(f"[WARNING] Email fact extraction failed: {e}", flush=True)
    
    # Run in background thread (non-blocking)
    threading.Thread(target=_background_extract, daemon=True).start()


def get_thread_detail(user_id: str, thread_id: str) -> Dict[str, Any]:
    """
    Return full plain-text content and headers for the selected email/thread.
    Thin wrapper around the existing gmail_detail tool.
    """
    import json

    raw = tool_get_thread_detail(user_id=user_id, thread_id=thread_id)
    try:
        return json.loads(raw)
    except Exception:
        return {"success": False, "error": "Invalid detail output"}


def extract_todos_from_thread(user_id: str, thread_id: str) -> Dict[str, Any]:
    """
    Extract TODO items from a Gmail thread and store them in MongoDB (email_todos).
    Thin wrapper around app.tools.email.extract_todos.extract_todos_from_thread (which returns JSON string).
    """
    import json

    raw = tool_extract_todos_from_thread(user_id=user_id, thread_id=thread_id)
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        if isinstance(data, dict):
            return data
        return {"success": False, "error": "Invalid todos output"}
    except Exception:
        return {"success": False, "error": "Invalid todos output"}


def list_email_todos(user_id: str, limit: int = 100) -> Dict[str, Any]:
    """
    List tasks extracted from emails.
    Now reads from unified tasks collection (source="email").
    Falls back to email_todos collection for backward compatibility.
    """
    from datetime import datetime
    from app.memory.models import get_tasks_collection

    def _dt_to_iso(v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    items: List[Dict[str, Any]] = []
    
    try:
        # First, try to read from unified tasks collection
        tasks_col = get_tasks_collection()
        if tasks_col is not None:
            cursor = (
                tasks_col.find({
                    "user_id": user_id,
                    "source": "email"
                })
                .sort("created_at", -1)
                .limit(max(1, min(int(limit or 100), 500)))
            )
            
            for task in cursor:
                items.append({
                    "id": task.get("_id"),
                    "text": task.get("title", ""),
                    "due": _dt_to_iso(task.get("due_date")) if task.get("due_date") else None,
                    "assignee": "me",  # Default for email tasks
                    "confidence": 0.7 if task.get("priority") == "high" else 0.6 if task.get("priority") == "medium" else 0.5,
                    "thread_id": task.get("source_ref", ""),
                    "subject": "",  # Not stored in tasks, would need to join with emails
                    "from": "",  # Not stored in tasks
                    "date": "",  # Not stored in tasks
                    "extracted_at": _dt_to_iso(task.get("created_at")),
                    "status": task.get("status", "pending"),
                    "priority": task.get("priority", "medium"),
                })
            
            if items:
                return {"success": True, "items": items}
        
        # Fallback to email_todos collection for backward compatibility
        db = get_db()
        if not db.is_connected or db.db is None:
            return {"success": False, "error": "MongoDB not connected"}

        col = db.db.get_collection("email_todos")
        cursor = (
            col.find({"user_id": user_id})
            .sort("extracted_at", -1)
            .limit(max(1, min(int(limit or 100), 500)))
        )
        docs = list(cursor)

        for doc in docs:
            thread_id = doc.get("thread_id")
            subject = doc.get("subject", "(No subject)")
            sender = doc.get("from", "")
            date = doc.get("date", "")
            extracted_at = _dt_to_iso(doc.get("extracted_at"))
            todos = doc.get("todos") or []
            if not isinstance(todos, list):
                todos = []
            for idx, t in enumerate(todos):
                if isinstance(t, str):
                    text = t
                    due = None
                    assignee = "me"
                    confidence = 0.5
                elif isinstance(t, dict):
                    text = (t.get("text") or "").strip()
                    due = t.get("due")
                    assignee = t.get("assignee", "me")
                    confidence = t.get("confidence", 0.6)
                else:
                    continue
                if not text:
                    continue
                items.append(
                    {
                        "id": f"{thread_id}:{idx}",
                        "text": text,
                        "due": due,
                        "assignee": assignee,
                        "confidence": confidence,
                        "thread_id": thread_id,
                        "subject": subject,
                        "from": sender,
                        "date": date,
                        "extracted_at": extracted_at,
                    }
                )

        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reply_to_thread(
    user_id: str,
    thread_id: str,
    to: str,
    body: str,
    subj_prefix: str = "Re:",
) -> Dict[str, Any]:
    """Send a reply inside a Gmail thread with a provided body."""
    try:
        msg = tool_reply_email(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            body=body,
            subj_prefix=subj_prefix,
        )
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def forward_thread(
    user_id: str,
    thread_id: str,
    to: str,
    body: str = "",
    subj_prefix: str = "Fwd:",
) -> Dict[str, Any]:
    """Forward a Gmail thread to another recipient."""
    try:
        msg = tool_forward_email(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            body=body,
            subj_prefix=subj_prefix,
        )
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def archive_thread(user_id: str, thread_id: str) -> Dict[str, Any]:
    """Archive a Gmail thread by removing it from the INBOX."""
    try:
        creds = load_google_credentials(user_id)
        service = _build_gmail_service(creds)

        # If a messageId was provided, resolve to threadId
        try:
            meta = service.users().messages().get(userId="me", id=thread_id, format="minimal").execute()
            real_thread_id = meta.get("threadId", thread_id)
        except HttpError as e:
            if e.resp.status in (400, 404):
                real_thread_id = thread_id
            else:
                raise

        service.users().threads().modify(
            userId="me",
            id=real_thread_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
        return {"success": True, "thread_id": real_thread_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def mark_thread_handled(user_id: str, thread_id: str) -> Dict[str, Any]:
    """Apply a 'Handled' label to a thread and mark it as read."""
    try:
        creds = load_google_credentials(user_id)
        service = _build_gmail_service(creds)

        # Ensure label exists (create if missing)
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        handled_label = next((l for l in labels if l.get("name") == "Handled"), None)
        if not handled_label:
            handled_label = service.users().labels().create(
                userId="me",
                body={
                    "name": "Handled",
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                    "type": "user",
                },
            ).execute()
        handled_label_id = handled_label["id"]

        # If a messageId was provided, resolve to threadId
        try:
            meta = service.users().messages().get(userId="me", id=thread_id, format="minimal").execute()
            real_thread_id = meta.get("threadId", thread_id)
        except HttpError as e:
            if e.resp.status in (400, 404):
                real_thread_id = thread_id
            else:
                raise

        service.users().threads().modify(
            userId="me",
            id=real_thread_id,
            body={"addLabelIds": [handled_label_id], "removeLabelIds": ["UNREAD"]},
        ).execute()
        return {"success": True, "thread_id": real_thread_id, "label": "Handled"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_threads(user_id: str, label: str = "INBOX", max_results: int = 50) -> Dict[str, Any]:
    """List Gmail threads for a given label."""
    try:
        creds = load_google_credentials(user_id)
        service = _build_gmail_service(creds)
        resp = service.users().threads().list(
            userId="me",
            labelIds=[label] if label else None,
            maxResults=max_results,
        ).execute()
        threads = resp.get("threads", []) or []
        items: List[Dict[str, Any]] = []
        for idx, t in enumerate(threads, start=1):
            th = service.users().threads().get(userId="me", id=t["id"], format="metadata").execute()
            first = th.get("messages", [{}])[0]
            headers = {h["name"]: h["value"] for h in first.get("payload", {}).get("headers", [])}
            items.append(
                {
                    "idx": idx,
                    "threadId": th.get("id"),
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", "(No subject)"),
                    "snippet": first.get("snippet", "")[:200],
                    "label": label or "",
                }
            )
            if len(items) >= max_results:
                break
        return {"success": True, "threads": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_threads(user_id: str, query: str, max_results: int = 20) -> Dict[str, Any]:
    """
    Search Gmail messages and return unique threads for a query.
    Checks MongoDB cache first, only fetches missing emails from Gmail API.
    """
    try:
        db = get_db()
        emails_col = None
        cached_results: List[Dict[str, Any]] = []
        cached_thread_ids = set()
        
        # STEP 1: Try to get matching emails from MongoDB cache first (FAST)
        if db.is_connected and db.db is not None:
            try:
                emails_col = db.db.get_collection("emails")
                
                # Extract search terms from query for cache lookup
                # For simple queries like "from:john", try to match in cache
                # For complex queries, we'll still need Gmail API but can enrich with cache data
                query_lower = query.lower()
                
                # Try to find cached emails that might match the search
                # This is a best-effort - Gmail search is complex, so we'll still use API
                # but we can enrich results with cached data when available
                cache_candidates = list(
                    emails_col.find(
                        {"user_id": user_id},
                        {
                            "thread_id": 1,
                            "from": 1,
                            "subject": 1,
                            "snippet": 1,
                            "category": 1,
                        },
                    )
                    .sort("classified_at", -1)
                    .limit(max_results * 3)  # Get more to filter
                )
                
                # Simple text matching in cache (for basic searches)
                for cached in cache_candidates:
                    if len(cached_results) >= max_results:
                        break
                    thread_id = cached.get("thread_id")
                    if not thread_id or thread_id in cached_thread_ids:
                        continue
                    
                    # Simple keyword matching - if query appears in subject/from
                    subject = (cached.get("subject") or "").lower()
                    from_email = (cached.get("from") or "").lower()
                    snippet = (cached.get("snippet") or "").lower()
                    
                    # Extract search keywords (remove Gmail operators)
                    search_terms = query_lower.replace("from:", "").replace("subject:", "").replace("in:", "")
                    search_terms = [t.strip() for t in search_terms.split() if t.strip() and len(t) > 2]
                    
                    matches = False
                    if any(term in subject or term in from_email or term in snippet for term in search_terms):
                        matches = True
                    elif "from:" in query_lower:
                        # Exact from: match
                        from_query = query_lower.split("from:")[-1].split()[0]
                        if from_query in from_email:
                            matches = True
                    
                    if matches:
                        cached_thread_ids.add(thread_id)
                        cached_results.append({
                            "threadId": thread_id,
                            "from": cached.get("from", ""),
                            "subject": cached.get("subject", "(No subject)"),
                            "snippet": cached.get("snippet", "")[:200],
                            "cached": True,  # Flag to indicate this came from cache
                        })
            except Exception as e:
                print(f"[WARNING] Cache lookup failed: {e}", flush=True)
        
        # STEP 2: If we have enough results from cache, return early (FAST PATH)
        if len(cached_results) >= max_results:
            return {"success": True, "threads": cached_results[:max_results], "source": "cache"}
        
        # STEP 3: Fetch from Gmail API to get more results or fill gaps
        creds = load_google_credentials(user_id)
        service = _build_gmail_service(creds)
        resp = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results * 2,
        ).execute()
        msgs = resp.get("messages", []) or []
        
        # STEP 4: Process Gmail API results, skip if already in cache
        seen = set(cached_thread_ids)  # Don't duplicate cached results
        results = list(cached_results)  # Start with cached results
        
        def fetch_message_metadata(msg_id: str) -> Optional[Dict[str, Any]]:
            """Fetch message metadata from Gmail API."""
            try:
                meta = service.users().messages().get(
                    userId="me", id=msg_id, format="metadata", metadataHeaders=["Subject", "From"]
                ).execute()
                return meta
            except Exception as e:
                print(f"[WARNING] Failed to fetch message {msg_id}: {e}", flush=True)
                return None
        
        # Fetch metadata in parallel for uncached emails
        message_ids_to_fetch = [msg["id"] for msg in msgs if msg["id"] not in seen]
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_msg_id = {
                executor.submit(fetch_message_metadata, msg_id): msg_id
                for msg_id in message_ids_to_fetch[:max_results * 2]
            }
            
            for future in as_completed(future_to_msg_id):
                if len(results) >= max_results:
                    break
                try:
                    meta = future.result()
                    if meta is None:
                        continue
                    
                    tid = meta.get("threadId")
                    if tid in seen:
                        continue
                    seen.add(tid)
                    
                    # Check if we have this in cache for enrichment
                    cached_data = None
                    if emails_col is not None:
                        cached_data = emails_col.find_one(
                            {"user_id": user_id, "thread_id": tid},
                            {"from": 1, "subject": 1, "snippet": 1}
                        )
                    
                    headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
                    
                    # Use cached data if available, otherwise use API data
                    result = {
                        "threadId": tid,
                        "from": cached_data.get("from") if cached_data else headers.get("From", ""),
                        "subject": cached_data.get("subject") if cached_data else headers.get("Subject", "(No subject)"),
                        "snippet": cached_data.get("snippet")[:200] if cached_data and cached_data.get("snippet") else meta.get("snippet", "")[:200],
                        "cached": cached_data is not None,
                    }
                    results.append(result)
                except Exception as e:
                    print(f"[WARNING] Failed to process search result: {e}", flush=True)
                    continue
        
        return {"success": True, "threads": results[:max_results], "source": "mixed" if cached_results else "gmail"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def classify_single_email(
    user_id: str,
    thread_id: Optional[str],
    email_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Classify a single email using the Smart Inbox Triage system.

    If thread_id is provided but email_data is not, the email is fetched from Gmail.
    """
    from app.database import get_db  # local import to avoid cycles

    email_data = email_data or {}

    try:
        # If thread_id provided, fetch email details
        if thread_id and not email_data:
            creds = load_google_credentials(user_id)
            service = _build_gmail_service(creds)

            # Get thread details
            thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
            first_msg = thread.get("messages", [{}])[0]
            headers = {h["name"]: h["value"] for h in first_msg.get("payload", {}).get("headers", [])}

            body = _extract_plain_text(first_msg.get("payload", {}))

            email_data = {
                "threadId": thread_id,
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "snippet": first_msg.get("snippet", "")[:200],
                "body": body[:1000],
            }

        if not email_data:
            return {"success": False, "error": "Missing email data or thread_id"}

        # Classify email
        classification = classify_email(email_data, user_id)
        
        # Add category to email_data for future reference
        email_data['category'] = classification['category']
        
        # NOTE: Fact extraction is now handled separately by background workers after login
        # This prevents fact extraction from happening during triaged inbox classification

        # Store classification in database if thread_id exists
        if thread_id:
            try:
                db = get_db()
                emails_col = db.db.get_collection("emails") if (db.is_connected and db.db is not None) else None
                if emails_col is not None:
                    # Store body temporarily for task processing
                    body_full = email_data.get("body", "")
                    
                    emails_col.update_one(
                        {"user_id": user_id, "thread_id": thread_id, "source": "gmail"},
                        {
                            "$set": {
                                "user_id": user_id,
                                "thread_id": thread_id,
                                "from": email_data.get("from", ""),
                                "subject": email_data.get("subject", ""),
                                "snippet": email_data.get("snippet", "")[:200],
                                "category": classification["category"],
                                "scores": classification["scores"],
                                "classified_at": datetime.utcnow().isoformat(),
                                "classification_version": CLASSIFICATION_VERSION,
                                "source": "gmail",
                                "body_temp": body_full,  # Store full body temporarily for task extraction
                                "processed_for_tasks": False,  # Mark as needing task processing
                            }
                        },
                        upsert=True,
                    )
            except Exception as e:
                print(f"[WARNING] Failed to store classification: {e}", flush=True)

        return {
            "success": True,
            "classification": classification,
            "email": email_data,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def triaged_inbox(
    user_id: str,
    max_results: int = 50,
    category_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get triaged inbox with emails categorized by priority (v3.0 - 10 categories).
    Returns cached v3.0 classifications immediately for instant UI response.
    
    PERFORMANCE OPTIMIZATIONS:
    - Only loads v3.0 classified emails (ignores old versions)
    - Returns cached data in <50ms (no Gmail API call)
    - Background worker only triggers if needed
    - MongoDB index: {user_id: 1, classification_version: 1, classified_at: -1}
    """
    emails_col = None
    stored_classifications: Dict[str, Dict[str, Any]] = {}
    stored_emails_metadata: Dict[str, Dict[str, Any]] = {}
    total_classified_count = 0

    # ⚡ FAST PATH: Load v3.0 classified emails from database (instant response)
    try:
        db = get_db()
        if db.is_connected and db.db is not None:
            emails_col = db.db.get_collection("emails")
            
            # Count total v3.0 classified emails for this user
            total_classified_count = emails_col.count_documents({
                "user_id": user_id,
                "classification_version": CLASSIFICATION_VERSION
            })
            
            # OPTIMIZATION: Only fetch v3.0 classifications (ignore old versions)
            # Fetch more than requested to have buffer for filtering by category
            limit_count = min(max_results * 3, 500)  # 3x buffer for category filtering
            
            stored = list(
                emails_col.find(
                    {
                        "user_id": user_id,
                        "classification_version": CLASSIFICATION_VERSION,  # ⚡ Only v3.0
                    },
                    {
                        "thread_id": 1,
                        "category": 1,
                        "scores": 1,
                        "from": 1,
                        "subject": 1,
                        "snippet": 1,
                        "classified_at": 1,
                    },
                )
                .sort("classified_at", -1)  # Most recent first
                .limit(limit_count)
            )

            # Process emails (in-memory, very fast)
            for s in stored:
                thread_id = s.get("thread_id")
                stored_classifications[thread_id] = {
                    "category": s.get("category", "normal"),
                    "scores": s.get("scores", {}),
                }
                stored_emails_metadata[thread_id] = {
                    "from": s.get("from", ""),
                    "subject": s.get("subject", "(No subject)"),
                    "snippet": s.get("snippet", "")[:200],
                    "classified_at": s.get("classified_at", ""),
                }
                
            print(f"[INFO] Triaged inbox: loaded {len(stored)} v3.0 classified emails for {user_id}", flush=True)
    except Exception as e:
        print(f"[WARNING] Failed to load stored classifications: {e}", flush=True)

    # Build response from cached data (instant)
    classified_emails: List[Dict[str, Any]] = []
    for thread_id, classification in stored_classifications.items():
        email_meta = stored_emails_metadata.get(thread_id, {})
        classified_emails.append(
            {
                "threadId": thread_id,
                "from": email_meta.get("from", ""),
                "subject": email_meta.get("subject", "(No subject)"),
                "snippet": email_meta.get("snippet", ""),
                "category": classification["category"],
                "scores": classification["scores"],
                "classified_at": email_meta.get("classified_at", ""),
            }
        )

    # REMOVED: fetch_and_classify_new() function - it caused SSL conflicts with classify_background
    # Now we only return cached emails from the database. The frontend calls classify_background
    # separately to fetch new emails in a controlled, sequential manner.
    
    # Note: For real-time updates, implement WebSocket/SSE to push new classifications

    # Apply category filter if specified
    if category_filter:
        classified_emails = [e for e in classified_emails if e.get("category") == category_filter]

    # Ensure we don't exceed max_results
    classified_emails = classified_emails[:max_results]

    # Group by category (v3.0 - 10 categories)
    categories: Dict[str, List[Dict[str, Any]]] = {
        "urgent": [],
        "action_items": [],
        "waiting_for_reply": [],
        "clients": [],
        "invoices": [],
        "normal": [],
        "notifications": [],
        "newsletters": [],
        "promotional": [],
        "transactional": [],
        "social": [],
    }
    for email in classified_emails:
        cat = email.get("category", "normal")
        if cat in categories:
            categories[cat].append(email)
        else:
            # Handle any unknown categories (fallback to normal)
            categories["normal"].append(email)

    # Return with performance metadata for frontend
    return {
        "success": True,
        "categories": categories,
        "total": len(classified_emails),
        "total_classified": total_classified_count,  # Total v3.0 classified emails
        "classification_version": CLASSIFICATION_VERSION,
        "cached": True,  # Always returns from cache (instant)
        "background_worker_triggered": total_classified_count < 100,  # If true, more emails being fetched
        "category_counts": {cat: len(emails) for cat, emails in categories.items()},  # Quick overview
    }


def classify_background(user_id: str, max_emails: int = 20) -> Dict[str, Any]:
    """
    Trigger background classification for unclassified emails.
    
    WINDOWS-OPTIMIZED: Batched Sequential Processing
    - Loads emails in batches of 10 (recent first)
    - Processes COMPLETELY sequentially (1 email at a time per batch)
    - 1 second pause between batches
    - Minimizes SSL errors on Windows
    - Prioritizes recent emails
    
    Returns immediately after starting the worker thread.
    """
    from app.database import get_db  # local import to avoid cycles

    def _worker() -> None:
        try:
            creds = load_google_credentials(user_id)
            service = _build_gmail_service(creds)

            # Get unclassified emails from inbox
            # Fetch more than requested to account for threads and duplicates
            # Increased from 3x to 5x for better coverage and fact extraction
            fetch_limit = min(max_emails * 5, 500)  # Fetch 5x but cap at 500 (default: 100 emails)
            
            print(f"[INFO] Fetching up to {fetch_limit} recent emails from Gmail for classification", flush=True)
            
            resp = service.users().messages().list(
                userId="me",
                q="in:inbox -from:me",
                maxResults=fetch_limit,
            ).execute()

            messages = resp.get("messages", []) or []
            seen_threads = set()
            seen_threads_lock = threading.Lock()

            # Get already classified thread IDs
            emails_col = None
            classified_threads = set()
            try:
                bg_db = get_db()
                if bg_db.is_connected and bg_db.db is not None:
                    emails_col = bg_db.db.get_collection("emails")
                    classified = list(
                        emails_col.find(
                            {"user_id": user_id},
                            {"thread_id": 1},
                        )
                    )
                    classified_threads = {c.get("thread_id") for c in classified}
            except Exception:
                pass

            # OPTIMIZATION: Parallelize fetching and classification
            def fetch_and_classify_message(msg_id: str) -> Optional[Dict[str, Any]]:
                """Fetch and classify a single message. Returns classification data or None."""
                try:
                    # First get metadata to check thread
                    meta = service.users().messages().get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From"],
                    ).execute()

                    thread_id = meta.get("threadId")
                    # Thread-safe check and add
                    with seen_threads_lock:
                        if thread_id in seen_threads or thread_id in classified_threads:
                            # Skip already classified or duplicate threads
                            return None
                        seen_threads.add(thread_id)

                    # Fetch full message
                    full_msg = service.users().messages().get(
                        userId="me",
                        id=msg_id,
                        format="full",
                    ).execute()

                    headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
                    body = _extract_plain_text(full_msg.get("payload", {}))

                    email_data = {
                        "threadId": thread_id,
                        "from": headers.get("From", ""),
                        "subject": headers.get("Subject", "(No subject)"),
                        "snippet": full_msg.get("snippet", "")[:200],
                        "body": body[:1000],
                    }

                    classification = classify_email(email_data, user_id)
                    
                    # NOTE: Fact extraction is now handled separately by background workers after login
                    # This prevents fact extraction from happening during triaged inbox classification

                    # Store in database
                    if emails_col is not None:
                        emails_col.update_one(
                            {"user_id": user_id, "thread_id": thread_id, "source": "gmail"},
                            {
                                "$set": {
                                    "user_id": user_id,
                                    "thread_id": thread_id,
                                    "message_id": msg_id,  # Store message ID for reference
                                    "from": headers.get("From", ""),
                                    "source": "gmail",  # Add source field
                                    "subject": headers.get("Subject", "(No subject)"),
                                    "snippet": full_msg.get("snippet", "")[:200],
                                    "date": headers.get("Date", ""),
                                    "category": classification["category"],
                                    "scores": classification["scores"],
                                    "classified_at": datetime.utcnow().isoformat(),
                                    "classification_version": CLASSIFICATION_VERSION,
                                    "body_temp": body,  # Store full body temporarily for task extraction
                                    "processed_for_tasks": False,  # Mark as needing task processing
                                    "labels": full_msg.get("labelIds", []),  # Store labels
                                }
                            },
                            upsert=True,
                        )

                    return {"thread_id": thread_id, "classification": classification}
                except Exception as e:
                    print(f"[WARNING] Background classification failed for {msg_id}: {e}", flush=True)
                    return None
            
            # NEW: Process messages in BATCHES (10 at a time, completely sequential)
            # WINDOWS FIX: Small batches + sequential processing = fewer SSL errors
            count = 0
            failed_count = 0
            skipped_count = 0  # Track already-classified threads
            # Process ALL fetched messages (not just first 40), stopping when we've classified enough
            message_ids = [msg["id"] for msg in messages]  # Process all messages to find unclassified ones
            
            BATCH_SIZE = 10  # Process 10 emails per batch (smaller = more reliable on Windows)
            total_batches = (len(message_ids) + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"[INFO] Processing {len(message_ids)} messages in {total_batches} batches of {BATCH_SIZE} (sequential)", flush=True)
            
            # Process each batch SEQUENTIALLY (not all at once)
            for batch_num in range(total_batches):
                if count >= max_emails:
                    break
                
                # Get current batch
                start_idx = batch_num * BATCH_SIZE
                end_idx = min((batch_num + 1) * BATCH_SIZE, len(message_ids))
                batch_message_ids = message_ids[start_idx:end_idx]
                
                print(f"[INFO] Batch {batch_num + 1}/{total_batches}: Processing {len(batch_message_ids)} emails", flush=True)
                
                # WINDOWS SSL FIX: Process completely sequentially (1 worker = no parallelism)
                # Even 2 parallel workers cause SSL errors on Windows
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future_to_msg_id = {
                        executor.submit(fetch_and_classify_message, msg_id): msg_id
                        for msg_id in batch_message_ids
                    }
                
                    for future in as_completed(future_to_msg_id):
                        if count >= max_emails:
                            break
                        try:
                            result = future.result()
                            if result is not None:
                                count += 1
                                if count % 5 == 0:  # Progress update every 5 emails
                                    print(f"[INFO] Progress: {count} classified, {skipped_count} skipped, {failed_count} failed", flush=True)
                            else:
                                # None = already classified or duplicate (skipped, not failed)
                                skipped_count += 1
                        except Exception as e:
                            msg_id = future_to_msg_id[future]
                            failed_count += 1
                            print(f"[WARNING] Failed to process message {msg_id}: {e}", flush=True)
                            continue

                # Longer delay between batches to let SSL connections fully settle (Windows fix)
                import time
                time.sleep(1.0)  # 1 second pause between batches

            total_processed = count + skipped_count + failed_count
            success_rate = (count / total_processed * 100) if total_processed > 0 else 0
            print(f"[SUCCESS] Background classification completed: {count} new, {skipped_count} skipped (already classified), {failed_count} failed ({success_rate:.1f}% success rate)", flush=True)
        except Exception as e:
            print(f"[ERROR] Background classification error: {e}", flush=True)

    threading.Thread(target=_worker, daemon=True).start()
    return {"success": True, "message": "Background classification started"}


def send_new_email(user_id: str, to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send a new email (compose)."""
    try:
        msg = tool_send_email(user_id=user_id, to=to, subject=subject, body=body)
        # send_email can return an error string instead of raising an exception
        if isinstance(msg, str) and msg.startswith("Error:"):
            return {"success": False, "error": msg}
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def rewrite_email_text(
    user_id: str,
    text: str,
    tone: str = "polite and professional",
    include_signature: bool = False,
    signature_text: str = "",
    generate_subject: bool = True,
) -> Dict[str, Any]:
    """
    Rewrite a user-provided text more politely/clearly, optionally using user's style
    and appending a signature. Also optionally generate a concise subject line.
    """
    import json
    from openai import OpenAI
    from app.config import Config

    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=Config.OPENAI_API_KEY) if Config.OPENAI_API_KEY else None
        if not client:
            return {"success": False, "error": "OpenAI API key not configured"}
        # Try to leverage user's style profile if available
        try:
            style_json = analyze_email_style(user_id=user_id, max_samples=5)
        except Exception:
            style_json = "{}"

        # Ask model to return strict JSON for easy parsing
        instructions = [
            f"Rewrite the following email body in a concise, {tone} tone.",
            "Keep the meaning, fix grammar, and avoid over-formality.",
            "Use proper email paragraphing with a blank line between paragraphs.",
        ]
        if include_signature and signature_text:
            instructions.append(
                "Append the following closing signature at the end, separated by one blank line, "
                "replacing any existing signature:"
            )
        else:
            instructions.append("Do not add a closing signature.")
        if generate_subject:
            instructions.append("Propose a concise subject (3-8 words).")
        else:
            instructions.append("Do not propose a subject.")
        instructions.append(
            "Return a JSON object ONLY with keys: subject (string, may be empty) and body (string). "
            "No markdown, no extra commentary."
        )

        # Build the prompt with signature if needed
        signature_section = ""
        if include_signature and signature_text:
            signature_section = f"\n\nSignature to append:\n{signature_text}\n"
        
        user_prompt = "\n".join(instructions) + f"\n\nUser style profile (JSON, optional):\n{style_json}{signature_section}\nEmail body to rewrite:\n{text}"

        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL or "gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert email editor. You ONLY return JSON as instructed.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content or ""
        
        # Clean up markdown code fences if present
        import re
        clean = raw.strip().strip("`")
        clean = re.sub(r"^```json\s*|\s*```$", "", clean, flags=re.IGNORECASE | re.MULTILINE).strip()
        
        try:
            data = json.loads(clean)
            # Ensure we have both subject and body keys
            if not isinstance(data, dict):
                data = {"subject": "", "body": clean}
            if "body" not in data:
                data["body"] = clean
            if "subject" not in data:
                data["subject"] = ""
        except Exception:
            # If the model didn't respect JSON, wrap the raw response
            data = {"subject": "", "body": clean if clean else raw}
        return {"success": True, "result": data}
    except Exception as e:
        from app.utils.logging_utils import get_logger
        logger = get_logger(__name__)
        logger.error(f"Error in rewrite_email_text: {e}", exc_info=True)
        return {"success": False, "error": str(e)}



