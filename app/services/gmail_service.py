from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
from app.tools.email.forward import forward_email as tool_forward_email
from app.utils.oauth_utils import load_google_credentials


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
        service = build("gmail", "v1", credentials=creds)

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
        service = build("gmail", "v1", credentials=creds)

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
        service = build("gmail", "v1", credentials=creds)
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
        service = build("gmail", "v1", credentials=creds)
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
            """Fetch message metadata, check cache first."""
            try:
                # Check if we have this thread in cache
                thread_id = None
                if emails_col:
                    # Try to find thread_id by message_id or check cache
                    cached_msg = emails_col.find_one(
                        {"user_id": user_id, "thread_id": {"$exists": True}},
                        {"thread_id": 1}
                    )
                    # We'll need to fetch from API to get thread_id, but can enrich with cache
                
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
                    if emails_col:
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
            service = build("gmail", "v1", credentials=creds)

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

        # Store classification in database if thread_id exists
        if thread_id:
            try:
                db = get_db()
                emails_col = db.db.get_collection("emails") if (db.is_connected and db.db is not None) else None
                if emails_col is not None:
                    emails_col.update_one(
                        {"user_id": user_id, "thread_id": thread_id},
                        {
                            "$set": {
                                "category": classification["category"],
                                "scores": classification["scores"],
                                "classified_at": datetime.utcnow().isoformat(),
                                "classification_version": CLASSIFICATION_VERSION,
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
    Get triaged inbox with emails categorized by priority.
    Returns cached data immediately, and may classify new emails in the background.
    """
    emails_col = None
    stored_classifications: Dict[str, Dict[str, Any]] = {}
    stored_emails_metadata: Dict[str, Dict[str, Any]] = {}
    needs_reclassification: List[str] = []

    # Get stored classifications from database FIRST - return immediately
    try:
        db = get_db()
        if db.is_connected and db.db is not None:
            emails_col = db.db.get_collection("emails")
            # OPTIMIZATION: Only fetch what we need + small buffer, not 2000
            # Fetching 2000 when user wants 100 is wasteful
            limit_count = min(max(max_results + 50, 100), 1000)  # Cap at 1000 max
            stored = list(
                emails_col.find(
                    {"user_id": user_id},
                    {
                        "thread_id": 1,
                        "category": 1,
                        "scores": 1,
                        "from": 1,
                        "subject": 1,
                        "snippet": 1,
                        "classification_version": 1,
                    },
                )
                .sort("classified_at", -1)
                .limit(limit_count)
            )  # MongoDB index on (user_id, classified_at) makes this query fast

            # Process list in Python (now in memory, so very fast)
            for s in stored:
                thread_id = s.get("thread_id")
                stored_version = s.get("classification_version")

                # If version doesn't match or is missing, mark for re-classification but STILL use it for now
                if stored_version != CLASSIFICATION_VERSION:
                    needs_reclassification.append(thread_id)

                stored_classifications[thread_id] = {
                    "category": s.get("category", "normal"),
                    "scores": s.get("scores", {}),
                }
                stored_emails_metadata[thread_id] = {
                    "from": s.get("from", ""),
                    "subject": s.get("subject", "(No subject)"),
                    "snippet": s.get("snippet", "")[:200],
                }
    except Exception as e:
        print(f"[WARNING] Failed to load stored classifications: {e}", flush=True)

    # Return cached emails immediately - no Gmail API call needed here
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
            }
        )

    # If we have fewer emails than requested, fetch from Gmail in main request; otherwise, run in background only
    needs_more_emails = len(classified_emails) < max_results

    def fetch_and_classify_new() -> None:
        nonlocal classified_emails, max_results  # Allow modification of outer scope variable
        try:
            creds = load_google_credentials(user_id)
            service = build("gmail", "v1", credentials=creds)

            unclassified_threads: List[Dict[str, Any]] = []
            # Fetch recent emails from inbox
            gmail_fetch_limit = min(max(max_results, 200), 1000)
            resp = service.users().messages().list(
                userId="me",
                q="in:inbox -from:me",
                maxResults=gmail_fetch_limit,
            ).execute()

            messages = resp.get("messages", []) or []
            seen_threads = set(stored_classifications.keys())
            
            # OPTIMIZATION: Fetch metadata in parallel using ThreadPoolExecutor
            # This dramatically speeds up fetching 1000 emails (from ~2-5 minutes to ~10-30 seconds)
            def fetch_message_metadata(msg_id: str) -> Optional[Dict[str, Any]]:
                """Fetch a single message's metadata. Returns None on error."""
                try:
                    meta = service.users().messages().get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From"],
                    ).execute()
                    return meta
                except Exception as e:
                    print(f"[WARNING] Failed to fetch message {msg_id}: {e}", flush=True)
                    return None
            
            # Use ThreadPoolExecutor to fetch metadata in parallel (max 20 concurrent requests)
            # Gmail API has rate limits, so we limit concurrency to avoid quota errors
            processed_emails = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                # Submit all fetch tasks
                future_to_msg_id = {
                    executor.submit(fetch_message_metadata, msg["id"]): msg["id"] 
                    for msg in messages
                }
                
                # Process results as they complete
                for future in as_completed(future_to_msg_id):
                    msg_id = future_to_msg_id[future]
                    try:
                        meta = future.result()
                        if meta is None:
                            continue
                            
                        thread_id = meta.get("threadId")
                        if thread_id in seen_threads:
                            continue
                        seen_threads.add(thread_id)

                        headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}

                        # Store ALL emails we find; classify only if not in cache
                        if thread_id not in stored_classifications:
                            unclassified_threads.append(
                                {
                                    "thread_id": thread_id,
                                    "message_id": msg_id,
                                    "headers": headers,
                                    "snippet": meta.get("snippet", "")[:200],
                                }
                            )
                        else:
                            # Even if cached, ensure it's in database with metadata
                            processed_emails.append({
                                "thread_id": thread_id,
                                "headers": headers,
                                "snippet": meta.get("snippet", "")[:200],
                            })
                    except Exception as e:
                        print(f"[WARNING] Failed to process message {msg_id}: {e}", flush=True)
                        continue
            
            # Batch update cached emails in database (more efficient than individual updates)
            if processed_emails and emails_col is not None:
                try:
                    for email_data in processed_emails:
                        emails_col.update_one(
                            {"user_id": user_id, "thread_id": email_data["thread_id"]},
                            {
                                "$set": {
                                    "from": email_data["headers"].get("From", ""),
                                    "subject": email_data["headers"].get("Subject", "(No subject)"),
                                    "snippet": email_data["snippet"],
                                }
                            },
                            upsert=True,
                        )
                except Exception as e:
                    print(f"[WARNING] Failed to update cached emails: {e}", flush=True)

            # Classify new emails (process enough to reach max_results)
            if unclassified_threads and emails_col is not None:
                current_count = len(classified_emails)
                needed = max_results - current_count
                limit = min(max(needed, 50), 200)
                newly_classified: List[Dict[str, Any]] = []
                
                # OPTIMIZATION: Parallelize email body fetching and classification
                def fetch_and_classify_email(unclass: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    """Fetch full email body and classify it. Returns classification result or None on error."""
                    try:
                        thread_id = unclass["thread_id"]
                        full_msg = service.users().messages().get(
                            userId="me",
                            id=unclass["message_id"],
                            format="full",
                        ).execute()
                        body = _extract_plain_text(full_msg.get("payload", {}))

                        email_data = {
                            "threadId": thread_id,
                            "from": unclass["headers"].get("From", ""),
                            "subject": unclass["headers"].get("Subject", "(No subject)"),
                            "snippet": unclass["snippet"],
                            "body": body[:1000],
                        }

                        classification = classify_email(email_data, user_id)
                        
                        # Store in database with version
                        emails_col.update_one(
                            {"user_id": user_id, "thread_id": thread_id},
                            {
                                "$set": {
                                    "user_id": user_id,
                                    "thread_id": thread_id,
                                    "from": unclass["headers"].get("From", ""),
                                    "subject": unclass["headers"].get("Subject", "(No subject)"),
                                    "snippet": unclass["snippet"],
                                    "category": classification["category"],
                                    "scores": classification["scores"],
                                    "classified_at": datetime.utcnow().isoformat(),
                                    "classification_version": CLASSIFICATION_VERSION,
                                }
                            },
                            upsert=True,
                        )

                        return {
                            "threadId": thread_id,
                            "from": unclass["headers"].get("From", ""),
                            "subject": unclass["headers"].get("Subject", "(No subject)"),
                            "snippet": unclass["snippet"],
                            "category": classification["category"],
                            "scores": classification["scores"],
                        }
                    except Exception as e:
                        print(f"[WARNING] Background classification failed for {unclass.get('thread_id')}: {e}", flush=True)
                        return None
                
                # Use ThreadPoolExecutor to fetch and classify emails in parallel
                # Use fewer workers for full body fetches (they're larger and slower)
                with ThreadPoolExecutor(max_workers=10) as executor:
                    # Submit classification tasks
                    future_to_unclass = {
                        executor.submit(fetch_and_classify_email, unclass): unclass
                        for unclass in unclassified_threads[:limit]
                    }
                    
                    # Collect results as they complete
                    for future in as_completed(future_to_unclass):
                        try:
                            result = future.result()
                            if result is not None:
                                newly_classified.append(result)
                        except Exception as e:
                            unclass = future_to_unclass[future]
                            print(f"[WARNING] Failed to classify email {unclass.get('thread_id')}: {e}", flush=True)
                            continue

                # If we need more emails, add newly classified emails to the response
                if needs_more_emails and newly_classified:
                    current_count = len(classified_emails)
                    if current_count < max_results:
                        remaining_slots = max_results - current_count
                        classified_emails.extend(newly_classified[:remaining_slots])

            # Re-classify emails that need version update (in background, don't block)
            if needs_reclassification and emails_col is not None:

                def reclassify_old_emails() -> None:
                    try:
                        for thread_id in needs_reclassification[:10]:  # Limit to 10 per run
                            try:
                                # Find a message with this thread_id from Gmail
                                resp = service.users().messages().list(
                                    userId="me",
                                    q=f"rfc822msgid:{thread_id} OR thread:{thread_id}",
                                    maxResults=1,
                                ).execute()
                                messages = resp.get("messages", [])
                                if not messages:
                                    # Try alternative: search by thread
                                    try:
                                        thread = service.users().threads().get(userId="me", id=thread_id).execute()
                                        if thread.get("messages"):
                                            message_id = thread["messages"][0]["id"]
                                        else:
                                            continue
                                    except Exception:
                                        continue
                                else:
                                    message_id = messages[0]["id"]

                                full_msg = service.users().messages().get(
                                    userId="me",
                                    id=message_id,
                                    format="full",
                                ).execute()
                                body = _extract_plain_text(full_msg.get("payload", {}))
                                headers = {
                                    h["name"]: h["value"]
                                    for h in full_msg.get("payload", {}).get("headers", [])
                                }

                                email_data = {
                                    "threadId": thread_id,
                                    "from": headers.get("From", ""),
                                    "subject": headers.get("Subject", "(No subject)"),
                                    "snippet": full_msg.get("snippet", "")[:200],
                                    "body": body[:1000],
                                }

                                classification = classify_email(email_data, user_id)

                                # Update with new classification and version
                                bg_db = get_db()
                                bg_emails_col = bg_db.db.get_collection("emails") if (bg_db.is_connected and bg_db.db is not None) else None
                                if bg_emails_col is not None:
                                    bg_emails_col.update_one(
                                        {"user_id": user_id, "thread_id": thread_id},
                                        {
                                            "$set": {
                                                "category": classification["category"],
                                                "scores": classification["scores"],
                                                "classified_at": datetime.utcnow().isoformat(),
                                                "classification_version": CLASSIFICATION_VERSION,
                                            }
                                        },
                                    )
                            except Exception as e:
                                print(f"[WARNING] Re-classification failed for {thread_id}: {e}", flush=True)
                                continue
                    except Exception as e:
                        print(f"[WARNING] Re-classification batch error: {e}", flush=True)

                threading.Thread(target=reclassify_old_emails, daemon=True).start()
        except Exception as e:
            print(f"[WARNING] Background fetch/classify error: {e}", flush=True)

    # OPTIMIZATION: Always return cached emails immediately, fetch new ones in background
    # This way UI shows results instantly instead of blocking for Gmail API calls
    # Background thread will update database, and next request will have more emails
    threading.Thread(target=fetch_and_classify_new, daemon=True).start()
    
    # Note: For even faster UX, you could implement WebSocket/SSE to push new emails
    # to frontend as they're classified, but for now this gives instant response

    # Apply category filter if specified
    if category_filter:
        classified_emails = [e for e in classified_emails if e.get("category") == category_filter]

    # Ensure we don't exceed max_results
    classified_emails = classified_emails[:max_results]

    # Group by category
    categories: Dict[str, List[Dict[str, Any]]] = {
        "urgent": [],
        "waiting_for_reply": [],
        "action_items": [],
        "newsletters": [],
        "invoices": [],
        "clients": [],
        "normal": [],
    }
    for email in classified_emails:
        cat = email.get("category", "normal")
        if cat in categories:
            categories[cat].append(email)

    return {
        "success": True,
        "categories": categories,
        "total": len(classified_emails),
    }


def classify_background(user_id: str, max_emails: int = 20) -> Dict[str, Any]:
    """
    Trigger background classification for unclassified emails.
    Returns immediately after starting the worker thread.
    """
    from app.database import get_db  # local import to avoid cycles

    def _worker() -> None:
        try:
            creds = load_google_credentials(user_id)
            service = build("gmail", "v1", credentials=creds)

            # Get unclassified emails from inbox
            resp = service.users().messages().list(
                userId="me",
                q="in:inbox -from:me",
                maxResults=max_emails * 2,
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

                    # Store in database
                    if emails_col is not None:
                        emails_col.update_one(
                            {"user_id": user_id, "thread_id": thread_id},
                            {
                                "$set": {
                                    "user_id": user_id,
                                    "thread_id": thread_id,
                                    "from": headers.get("From", ""),
                                    "subject": headers.get("Subject", "(No subject)"),
                                    "snippet": full_msg.get("snippet", "")[:200],
                                    "category": classification["category"],
                                    "scores": classification["scores"],
                                    "classified_at": datetime.utcnow().isoformat(),
                                    "classification_version": CLASSIFICATION_VERSION,
                                }
                            },
                            upsert=True,
                        )

                    return {"thread_id": thread_id, "classification": classification}
                except Exception as e:
                    print(f"[WARNING] Background classification failed for {msg_id}: {e}", flush=True)
                    return None
            
            # Process messages in parallel
            count = 0
            message_ids = [msg["id"] for msg in messages[:max_emails * 2]]  # Get extra to account for threads
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_msg_id = {
                    executor.submit(fetch_and_classify_message, msg_id): msg_id
                    for msg_id in message_ids
                }
                
                for future in as_completed(future_to_msg_id):
                    if count >= max_emails:
                        break
                    try:
                        result = future.result()
                        if result is not None:
                            count += 1
                    except Exception as e:
                        msg_id = future_to_msg_id[future]
                        print(f"[WARNING] Failed to process message {msg_id}: {e}", flush=True)
                        continue

            print(f"[INFO] Background classification completed: {count} emails classified", flush=True)
        except Exception as e:
            print(f"[ERROR] Background classification error: {e}", flush=True)

    threading.Thread(target=_worker, daemon=True).start()
    return {"success": True, "message": "Background classification started"}


def send_new_email(user_id: str, to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send a new email (compose)."""
    try:
        msg = tool_send_email(user_id=user_id, to=to, subject=subject, body=body)
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


