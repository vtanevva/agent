"""
Email Processing Pipeline (Ingest → parallel workers → cleanup)

Goal:
- On login, ingest the latest N emails into Mongo (emails collection)
- Run independent workers in parallel:
  1) Facts extraction (long-term memory)
  2) Relationship entity updates (contact-centric)
  3) Task extraction (Aivis task pipeline)
  4) Linking worker (attach facts/tasks to relationships once available)

Key constraint:
- `emails.body_temp` must only be deleted AFTER all required jobs have completed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.database import get_db
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Job state model
# ──────────────────────────────────────────────────────────────────────

JOB_PENDING = "pending"
JOB_PROCESSING = "processing"
JOB_DONE = "done"
JOB_ERROR = "error"
JOB_SKIPPED = "skipped"


@dataclass(frozen=True)
class EmailJobState:
    facts: str = JOB_PENDING
    relationships: str = JOB_PENDING
    tasks: str = JOB_PENDING
    calendar: str = JOB_PENDING
    linking: str = JOB_PENDING


def _now() -> datetime:
    return datetime.utcnow()


def ensure_email_processing_indexes() -> None:
    """Create indexes used by the worker claim queries."""
    db = get_db()
    if not db.is_connected or db.db is None:
        return

    emails = db.db["emails"]

    # Create indexes one-by-one (idempotent) to avoid a single conflict
    # preventing all other indexes from being created.
    index_specs = [
        ([(("user_id", 1), ("received_at", -1))], "user_id_1_received_at_-1", False),
        ([(("user_id", 1), ("batch_id", 1), ("received_at", -1))], "user_id_1_batch_id_1_received_at_-1", False),
        ([(("user_id", 1), ("facts_status", 1), ("received_at", -1))], "user_id_1_facts_status_1_received_at_-1", False),
        ([(("user_id", 1), ("relationships_status", 1), ("received_at", -1))], "user_id_1_relationships_status_1_received_at_-1", False),
        ([(("user_id", 1), ("tasks_status", 1), ("received_at", -1))], "user_id_1_tasks_status_1_received_at_-1", False),
        ([(("user_id", 1), ("calendar_status", 1), ("received_at", -1))], "user_id_1_calendar_status_1_received_at_-1", False),
        ([(("user_id", 1), ("linking_status", 1), ("received_at", -1))], "user_id_1_linking_status_1_received_at_-1", False),
        # IMPORTANT: do NOT force unique here.
        # Some environments already have a non-unique index with this auto-generated name,
        # and changing uniqueness would cause a name/spec conflict.
        ([(("user_id", 1), ("thread_id", 1), ("source", 1))], "user_id_1_thread_id_1_source_1", False),
    ]

    for key_tuple_list, name, unique in index_specs:
        keys = list(key_tuple_list[0])
        try:
            emails.create_index(keys, name=name, unique=unique)
        except Exception as e:
            logger.warning(f"Failed to ensure emails index {name}: {e}")


def _parse_received_at(date_str: Optional[str]) -> datetime:
    if not date_str:
        return _now()
    try:
        from dateutil import parser as date_parser

        return date_parser.parse(date_str)
    except Exception:
        return _now()


# ──────────────────────────────────────────────────────────────────────
# Ingestion
# ──────────────────────────────────────────────────────────────────────

def ingest_latest_emails(
    user_id: str,
    max_emails: int = 20,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest the latest emails into MongoDB `emails` collection and initialize job statuses.

    This ingestion is intentionally minimal and deterministic:
    - It pulls the most recent threads from provider(s)
    - It stores `body_temp` so workers can process without refetching
    """
    ensure_email_processing_indexes()

    max_emails = max(1, min(int(max_emails or 20), 50))

    db = get_db()
    if not db.is_connected or db.db is None:
        return {"success": False, "error": "Database not connected"}

    try:
        from app.services.email import unified_service
    except Exception as e:
        return {"success": False, "error": f"Email service unavailable: {e}"}

    batch_id = f"batch-{uuid4().hex[:10]}"
    emails_col = db.db["emails"]

    listed = unified_service.list_recent_emails(
        user_id=user_id,
        max_results=max_emails,
        provider=provider,
        unified=False,
    )
    if not listed.get("success"):
        return {"success": False, "error": listed.get("error", "Failed to list emails")}

    items = listed.get("emails", []) or []
    ingested = 0
    updated = 0
    failed = 0

    for item in items:
        thread_id = item.get("threadId") or item.get("thread_id") or ""
        source = item.get("source") or provider or "gmail"
        if not thread_id:
            continue

        try:
            detail = unified_service.get_thread_detail(
                user_id=user_id,
                thread_id=thread_id,
                provider=source,
            )
            if not detail.get("success"):
                failed += 1
                continue

            sender = detail.get("from") or item.get("from") or ""
            subject = detail.get("subject") or item.get("subject") or "(No subject)"
            body = (detail.get("body") or "").strip()
            snippet = item.get("snippet") or (body[:200] if body else "")
            received_at = _parse_received_at(detail.get("date"))

            # Stable IDs for dedupe + downstream linking
            message_id = detail.get("message_id") or thread_id
            canonical_thread_id = detail.get("thread_id") or thread_id

            # If this email was already fully processed, do NOT persist body_temp again.
            # (privacy + avoids leaving body_temp around with no worker to delete it)
            existing = emails_col.find_one(
                {"user_id": user_id, "thread_id": canonical_thread_id, "source": source},
                {
                    "facts_status": 1,
                    "relationships_status": 1,
                    "tasks_status": 1,
                    "calendar_status": 1,
                    "linking_status": 1,
                    "body_temp": 1,
                },
            )
            doneish = {JOB_DONE, JOB_SKIPPED}
            already_done = False
            if existing:
                already_done = (
                    existing.get("facts_status") in doneish
                    and existing.get("relationships_status") in doneish
                    and existing.get("tasks_status") in doneish
                    and existing.get("calendar_status") in doneish
                    and existing.get("linking_status") in doneish
                )

            now = _now()

            # Use an aggregation pipeline update so we can set defaults only if missing
            # (without overwriting completed jobs).
            update_pipeline: List[Dict[str, Any]] = [
                {
                    "$set": {
                        "user_id": user_id,
                        "thread_id": canonical_thread_id,
                        "source": source,
                        "message_id": message_id,
                        "from": sender,
                        "subject": subject,
                        "snippet": snippet,
                        "received_at": received_at,
                        "ingested_at": now,
                        "batch_id": batch_id,
                        "created_at": {"$ifNull": ["$created_at", now]},
                        "facts_status": {"$ifNull": ["$facts_status", JOB_PENDING]},
                        "relationships_status": {"$ifNull": ["$relationships_status", JOB_PENDING]},
                        "tasks_status": {"$ifNull": ["$tasks_status", JOB_PENDING]},
                        "calendar_status": {"$ifNull": ["$calendar_status", JOB_PENDING]},
                        "linking_status": {"$ifNull": ["$linking_status", JOB_PENDING]},
                    }
                }
            ]

            if already_done:
                # Ensure we are not reintroducing body_temp for completed items.
                update_pipeline.append({"$unset": "body_temp"})
            else:
                update_pipeline.append({"$set": {"body_temp": body}})

            res = emails_col.update_one(
                {"user_id": user_id, "thread_id": canonical_thread_id, "source": source},
                update_pipeline,
                upsert=True,
            )

            if res.upserted_id is not None:
                ingested += 1
            else:
                updated += 1

        except Exception as e:
            failed += 1
            logger.warning(f"Ingestion failed for thread {thread_id}: {e}")
            continue

    return {
        "success": True,
        "batch_id": batch_id,
        "requested": max_emails,
        "fetched": len(items),
        "ingested": ingested,
        "updated": updated,
        "failed": failed,
    }


def ingest_threads(
    user_id: str,
    thread_ids: List[str],
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest specific thread IDs into MongoDB `emails` collection and initialize job statuses.

    Used by Gmail Pub/Sub push processing (history delta → thread IDs).
    """
    ensure_email_processing_indexes()

    thread_ids = [str(t).strip() for t in (thread_ids or []) if str(t).strip()]
    # Bound cost — a single notification can include many items during catch-up
    thread_ids = thread_ids[:50]

    db = get_db()
    if not db.is_connected or db.db is None:
        return {"success": False, "error": "Database not connected"}

    try:
        from app.services.email import unified_service
    except Exception as e:
        return {"success": False, "error": f"Email service unavailable: {e}"}

    batch_id = f"batch-{uuid4().hex[:10]}"
    emails_col = db.db["emails"]

    ingested = 0
    updated = 0
    failed = 0

    source = provider or "gmail"

    for thread_id in thread_ids:
        try:
            detail = unified_service.get_thread_detail(
                user_id=user_id,
                thread_id=thread_id,
                provider=source,
            )
            if not detail.get("success"):
                failed += 1
                continue

            sender = detail.get("from") or ""
            subject = detail.get("subject") or "(No subject)"
            body = (detail.get("body") or "").strip()
            snippet = (body[:200] if body else "")[:200]
            received_at = _parse_received_at(detail.get("date"))

            message_id = detail.get("message_id") or thread_id
            canonical_thread_id = detail.get("thread_id") or thread_id

            existing = emails_col.find_one(
                {"user_id": user_id, "thread_id": canonical_thread_id, "source": source},
                {
                    "facts_status": 1,
                    "relationships_status": 1,
                    "tasks_status": 1,
                    "calendar_status": 1,
                    "linking_status": 1,
                    "body_temp": 1,
                },
            )
            doneish = {JOB_DONE, JOB_SKIPPED}
            already_done = False
            if existing:
                already_done = (
                    existing.get("facts_status") in doneish
                    and existing.get("relationships_status") in doneish
                    and existing.get("tasks_status") in doneish
                    and existing.get("calendar_status") in doneish
                    and existing.get("linking_status") in doneish
                )

            now = _now()
            update_pipeline: List[Dict[str, Any]] = [
                {
                    "$set": {
                        "user_id": user_id,
                        "thread_id": canonical_thread_id,
                        "source": source,
                        "message_id": message_id,
                        "from": sender,
                        "subject": subject,
                        "snippet": snippet,
                        "received_at": received_at,
                        "ingested_at": now,
                        "batch_id": batch_id,
                        "created_at": {"$ifNull": ["$created_at", now]},
                        "facts_status": {"$ifNull": ["$facts_status", JOB_PENDING]},
                        "relationships_status": {"$ifNull": ["$relationships_status", JOB_PENDING]},
                        "tasks_status": {"$ifNull": ["$tasks_status", JOB_PENDING]},
                        "calendar_status": {"$ifNull": ["$calendar_status", JOB_PENDING]},
                        "linking_status": {"$ifNull": ["$linking_status", JOB_PENDING]},
                    }
                }
            ]

            if already_done:
                update_pipeline.append({"$unset": "body_temp"})
            else:
                update_pipeline.append({"$set": {"body_temp": body}})

            res = emails_col.update_one(
                {"user_id": user_id, "thread_id": canonical_thread_id, "source": source},
                update_pipeline,
                upsert=True,
            )

            if res.upserted_id is not None:
                ingested += 1
            else:
                updated += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Ingestion failed for thread {thread_id}: {e}")
            continue

    return {
        "success": True,
        "batch_id": batch_id,
        "requested": len(thread_ids),
        "ingested": ingested,
        "updated": updated,
        "failed": failed,
    }


# ──────────────────────────────────────────────────────────────────────
# Claim + cleanup helpers
# ──────────────────────────────────────────────────────────────────────

def _claim_next_email(
    *,
    user_id: str,
    job_field: str,
    batch_id: Optional[str],
    worker_id: str,
    lock_minutes: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Atomically claim the next email for a given job (newest-first).
    """
    db = get_db()
    if not db.is_connected or db.db is None:
        return None

    from pymongo import ReturnDocument

    emails = db.db["emails"]
    now = _now()
    lock_expired_before = now - timedelta(minutes=max(1, lock_minutes))

    status_field = f"{job_field}_status"
    claimed_at_field = f"{job_field}_claimed_at"
    claimed_by_field = f"{job_field}_claimed_by"

    query: Dict[str, Any] = {
        "user_id": user_id,
        status_field: {"$in": [JOB_PENDING, JOB_ERROR]},
        "$or": [
            {claimed_at_field: {"$exists": False}},
            {claimed_at_field: {"$lt": lock_expired_before}},
        ],
    }
    if batch_id:
        query["batch_id"] = batch_id

    update = {
        "$set": {
            status_field: JOB_PROCESSING,
            claimed_at_field: now,
            claimed_by_field: worker_id,
            f"{job_field}_started_at": now,
        },
        "$unset": {f"{job_field}_error": ""},
    }

    doc = emails.find_one_and_update(
        query,
        update,
        sort=[("received_at", -1)],
        return_document=ReturnDocument.AFTER,
    )
    return doc


def _mark_job_done(
    *,
    email_doc_id,
    job_field: str,
    extra_set: Optional[Dict[str, Any]] = None,
    status: str = JOB_DONE,
    error: Optional[str] = None,
) -> None:
    db = get_db()
    if not db.is_connected or db.db is None:
        return

    emails = db.db["emails"]
    now = _now()

    status_field = f"{job_field}_status"
    update: Dict[str, Any] = {"$set": {status_field: status, f"{job_field}_completed_at": now}}
    if extra_set:
        update["$set"].update(extra_set)
    if error:
        update["$set"][f"{job_field}_error"] = error
        update["$set"][status_field] = JOB_ERROR

    emails.update_one({"_id": email_doc_id}, update)


def _maybe_delete_body_temp(email_doc_id) -> bool:
    """
    Delete body_temp only after ALL jobs are finished (done or skipped).
    Atomic: only unsets if gate condition matches.
    """
    db = get_db()
    if not db.is_connected or db.db is None:
        return False

    emails = db.db["emails"]
    doneish = {"$in": [JOB_DONE, JOB_SKIPPED]}
    res = emails.update_one(
        {
            "_id": email_doc_id,
            "body_temp": {"$exists": True},
            "facts_status": doneish,
            "relationships_status": doneish,
            "tasks_status": doneish,
            "calendar_status": doneish,
            "linking_status": doneish,
        },
        {"$unset": {"body_temp": ""}, "$set": {"body_deleted_at": _now()}},
    )
    return res.modified_count > 0


# ──────────────────────────────────────────────────────────────────────
# Workers
# ──────────────────────────────────────────────────────────────────────

def run_facts_worker(
    user_id: str,
    batch_id: Optional[str] = None,
    max_items: int = 50,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    worker_id = worker_id or f"facts-{uuid4().hex[:6]}"
    processed = 0
    stored_total = 0
    failed = 0

    from app.memory.memory_gate import get_memory_gate
    from app.memory.models import get_memory_facts_collection
    from app.memory.vector_store import get_vector_store

    gate = get_memory_gate()
    facts_col = get_memory_facts_collection()
    vector_store = get_vector_store()

    if facts_col is None:
        return {"success": False, "error": "Facts collection unavailable"}

    for _ in range(max(1, min(int(max_items or 50), 500))):
        doc = _claim_next_email(user_id=user_id, job_field="facts", batch_id=batch_id, worker_id=worker_id)
        if not doc:
            break

        processed += 1
        try:
            thread_id = doc.get("thread_id", "")
            sender = doc.get("from", "")
            subject = doc.get("subject", "")
            body = (doc.get("body_temp") or doc.get("snippet") or "")[:2000]

            source_ref = f"email:{thread_id}"
            extraction_text = f"Subject: {subject}\n\nFrom: {sender}\n\nContent: {body}"

            # Skip if already have active facts for this thread (cheap)
            existing_for_thread = facts_col.find_one({"user_id": user_id, "source_ref": source_ref, "is_active": True})
            if existing_for_thread:
                _mark_job_done(email_doc_id=doc["_id"], job_field="facts", status=JOB_SKIPPED, extra_set={"facts_skip_reason": "already_extracted"})
                _maybe_delete_body_temp(doc["_id"])
                continue

            candidate_facts = gate.extract_candidate_facts(text=extraction_text, user_id=user_id, source_ref=source_ref)
            if not candidate_facts:
                _mark_job_done(email_doc_id=doc["_id"], job_field="facts", status=JOB_SKIPPED, extra_set={"facts_skip_reason": "no_facts"})
                _maybe_delete_body_temp(doc["_id"])
                continue

            existing_facts = list(facts_col.find({"user_id": user_id, "is_active": True}))
            unique_facts = gate.deduplicate_facts(candidate_facts, existing_facts)

            if not unique_facts:
                _mark_job_done(email_doc_id=doc["_id"], job_field="facts", status=JOB_SKIPPED, extra_set={"facts_skip_reason": "all_duplicates"})
                _maybe_delete_body_temp(doc["_id"])
                continue

            stored_count = gate.store_facts(user_id, unique_facts)
            stored_total += stored_count

            # Embed facts (best-effort)
            try:
                stored_facts = list(
                    facts_col.find(
                        {"user_id": user_id, "source_ref": source_ref, "is_active": True},
                        {"_id": 1, "text": 1, "type": 1, "confidence": 1},
                    ).sort("created_at", -1)
                )
                vectors = []
                for f in stored_facts:
                    vectors.append(
                        {
                            "id": str(f["_id"]),
                            "text": f.get("text", ""),
                            "metadata": {
                                "fact_type": (f.get("type") or ""),
                                "confidence": f.get("confidence", 0.0),
                                "source": "email",
                            },
                        }
                    )
                if vectors:
                    vector_store.upsert_vectors(user_id=user_id, vectors=vectors, vector_type="fact")
            except Exception as e:
                logger.warning(f"Fact embedding failed for thread {thread_id}: {e}")

            _mark_job_done(
                email_doc_id=doc["_id"],
                job_field="facts",
                extra_set={"facts_stored": stored_count, "facts_source_ref": source_ref},
            )
            _maybe_delete_body_temp(doc["_id"])

        except Exception as e:
            failed += 1
            _mark_job_done(email_doc_id=doc["_id"], job_field="facts", error=str(e))
            _maybe_delete_body_temp(doc["_id"])

    return {"success": True, "processed": processed, "stored": stored_total, "failed": failed, "worker_id": worker_id}


def run_relationships_worker(
    user_id: str,
    batch_id: Optional[str] = None,
    max_items: int = 50,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    worker_id = worker_id or f"rel-{uuid4().hex[:6]}"
    processed = 0
    failed = 0

    from app.services.relationships_service import get_relationships_service

    rel_service = get_relationships_service()

    for _ in range(max(1, min(int(max_items or 50), 500))):
        doc = _claim_next_email(user_id=user_id, job_field="relationships", batch_id=batch_id, worker_id=worker_id)
        if not doc:
            break
        processed += 1

        try:
            email_data = {
                "thread_id": doc.get("thread_id", ""),
                "from": doc.get("from", ""),
                "to": doc.get("to", ""),  # may not be present; RelationshipsService handles gracefully
                "subject": doc.get("subject", ""),
                "body": (doc.get("body_temp") or doc.get("snippet") or "")[:2000],
            }

            result = rel_service.process_email(user_id, email_data)
            tracked_emails = result.get("tracked_emails", []) if isinstance(result, dict) else []
            email_sent_by_user = bool(result.get("email_sent_by_user")) if isinstance(result, dict) else False

            _mark_job_done(
                email_doc_id=doc["_id"],
                job_field="relationships",
                extra_set={
                    "relationship_contacts": tracked_emails,
                    "email_sent_by_user": email_sent_by_user,
                },
            )
            _maybe_delete_body_temp(doc["_id"])

        except Exception as e:
            failed += 1
            _mark_job_done(email_doc_id=doc["_id"], job_field="relationships", error=str(e))
            _maybe_delete_body_temp(doc["_id"])

    return {"success": True, "processed": processed, "failed": failed, "worker_id": worker_id}


def run_tasks_worker(
    user_id: str,
    batch_id: Optional[str] = None,
    max_items: int = 25,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract tasks from emails and write to the task pipeline collections.

    Notes:
    - This worker replaces the older "ingest_and_process() reads emails then deletes body_temp" flow.
    - It does NOT delete body_temp directly; cleanup is gated by _maybe_delete_body_temp().
    """
    worker_id = worker_id or f"tasks-{uuid4().hex[:6]}"
    processed = 0
    created = 0
    failed = 0

    # Reuse existing deterministic task pipeline
    from app.services.task_pipeline_service import get_task_pipeline_service

    pipeline = get_task_pipeline_service()

    # Optional noise filtering via classifier if available
    try:
        from app.tools.email.classifier import classify_email, CLASSIFICATION_VERSION  # type: ignore

        classifier_available = True
    except Exception:
        classifier_available = False

    IMPORTANT_CATEGORIES = {"urgent", "clients", "action_items", "waiting_for_reply", "invoices", "normal"}
    SKIP_CATEGORIES = {"notifications", "social", "promotional", "transactional", "newsletters"}

    db = get_db()
    emails_col = db.db["emails"] if (db.is_connected and db.db is not None) else None
    if emails_col is None:
        return {"success": False, "error": "Database not connected"}

    for _ in range(max(1, min(int(max_items or 25), 200))):
        doc = _claim_next_email(user_id=user_id, job_field="tasks", batch_id=batch_id, worker_id=worker_id)
        if not doc:
            break

        processed += 1
        try:
            category = doc.get("category")
            classification_version = doc.get("classification_version")

            # Cheap auto-classification if missing (to skip obvious noise)
            if (not category or not classification_version) and classifier_available:
                try:
                    email_for_classify = {
                        "from": doc.get("from", ""),
                        "subject": doc.get("subject", ""),
                        "snippet": (doc.get("snippet") or "")[:500],
                        "body": (doc.get("body_temp") or doc.get("snippet") or "")[:1500],
                    }
                    classification = classify_email(email_for_classify, user_id)
                    category = classification.get("category")
                    emails_col.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                "category": category,
                                "scores": classification.get("scores", {}),
                                "classification_version": CLASSIFICATION_VERSION,
                                # Ensure triaged_inbox can sort/return this new item
                                "classified_at": _now().isoformat(),
                            }
                        },
                    )
                except Exception:
                    pass

            if category in SKIP_CATEGORIES:
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="tasks",
                    status=JOB_SKIPPED,
                    extra_set={"tasks_skip_reason": f"noise_category:{category}"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            if category and category not in IMPORTANT_CATEGORIES:
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="tasks",
                    status=JOB_SKIPPED,
                    extra_set={"tasks_skip_reason": f"not_important:{category}"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            # Build email_data for pipeline
            body_text = doc.get("body_temp") or doc.get("snippet") or ""
            email_data = {
                "message_id": doc.get("message_id", doc.get("thread_id", "")),
                "thread_id": doc.get("thread_id", ""),
                "sender": doc.get("from", ""),
                "sender_name": pipeline._extract_name(doc.get("from", "")),
                "subject": doc.get("subject", ""),
                "snippet": doc.get("snippet", ""),
                "body": body_text,
                "timestamp": doc.get("received_at") or _now(),
                "labels": doc.get("labels", []),
            }

            task_id = pipeline.process_gmail_event(user_id, email_data)
            if task_id:
                created += 1

            _mark_job_done(
                email_doc_id=doc["_id"],
                job_field="tasks",
                extra_set={"created_task_id": task_id, "task_processed_at": _now()},
            )
            _maybe_delete_body_temp(doc["_id"])

        except Exception as e:
            failed += 1
            _mark_job_done(email_doc_id=doc["_id"], job_field="tasks", error=str(e))
            _maybe_delete_body_temp(doc["_id"])

    return {"success": True, "processed": processed, "created": created, "failed": failed, "worker_id": worker_id}


def run_calendar_worker(
    user_id: str,
    batch_id: Optional[str] = None,
    max_items: int = 25,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detect meeting-like emails and create calendar events.

    This is best-effort and designed to be safe:
    - Only runs for non-noise categories
    - Uses cheap regex/heuristics first
    - Dedupe per email thread via stored `calendar_event_id`
    """
    worker_id = worker_id or f"cal-{uuid4().hex[:6]}"
    processed = 0
    created = 0
    skipped = 0
    failed = 0

    db = get_db()
    emails_col = db.db["emails"] if (db.is_connected and db.db is not None) else None
    if emails_col is None:
        return {"success": False, "error": "Database not connected"}

    # Quick connectivity check (avoid expensive work if no calendar provider)
    try:
        from app.services.calendar import check_user_calendar_connections, create_calendar_event

        connections = check_user_calendar_connections(user_id)
        if not (connections.get("google_connected") or connections.get("outlook_connected")):
            return {
                "success": True,
                "processed": 0,
                "created": 0,
                "skipped": 0,
                "failed": 0,
                "worker_id": worker_id,
                "note": "no_calendar_connected",
            }
    except Exception as e:
        return {"success": False, "error": f"Calendar service unavailable: {e}", "worker_id": worker_id}

    # Deterministic parsing helpers
    from app.tools.calendar.detect_requests import detect_calendar_requests, parse_datetime_from_text
    from app.utils.timezone_utils import get_effective_user_timezone

    SKIP_CATEGORIES = {"notifications", "social", "promotional", "transactional", "newsletters"}
    MEETING_HINTS = [
        "meeting",
        "meet",
        "let's meet",
        "lets meet",
        "invite",
        "invitation",
        "calendar",
        "google meet",
        "meet.google.com",
        "zoom",
        "teams",
        "microsoft teams",
        "video call",
        "conference",
        "appointment",
        "schedule",
        "reschedule",
        "call",
        "demo",
        "interview",
        "standup",
    ]

    def _extract_sender_name(sender: str) -> str:
        s = (sender or "").strip()
        if "<" in s:
            return s.split("<", 1)[0].strip().strip('"')
        s = s.strip('"')
        if "@" in s and " " not in s:
            return s.split("@", 1)[0].strip()
        return s

    def _is_generic_summary(summary: str) -> bool:
        import re

        s = re.sub(r"[^a-z0-9\s]", " ", (summary or "").lower())
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            return True
        tokens = [t for t in s.split(" ") if t]
        if not tokens:
            return True

        date_time_words = {
            "today",
            "tomorrow",
            "next",
            "this",
            "at",
            "on",
            "in",
            "am",
            "pm",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "jan",
            "january",
            "feb",
            "february",
            "mar",
            "march",
            "apr",
            "april",
            "may",
            "jun",
            "june",
            "jul",
            "july",
            "aug",
            "august",
            "sep",
            "sept",
            "september",
            "oct",
            "october",
            "nov",
            "november",
            "dec",
            "december",
        }
        core = [t for t in tokens if t not in date_time_words and not t.isdigit()]
        if not core:
            core = tokens
        core_s = " ".join(core)

        generic_set = {
            "lets meet",
            "let us meet",
            "let s meet",
            "meet",
            "meeting",
            "quick meeting",
            "call",
            "quick call",
            "chat",
            "quick chat",
            "catch up",
            "sync",
            "sync up",
        }
        if core_s in generic_set or core_s.startswith("lets meet") or core_s.startswith("meet "):
            return True

        verbs = {"meet", "meeting", "call", "chat", "sync"}
        verbish = [t for t in core if t in verbs]
        nonverb = [t for t in core if t not in verbs]
        return bool(verbish) and len(nonverb) <= 1

    def _looks_like_meeting(text: str) -> bool:
        t = (text or "").lower()
        if not t:
            return False
        if any(h in t for h in MEETING_HINTS):
            return True
        # Word-boundary check to reduce false negatives like "Let's meet Friday…"
        try:
            import re

            return re.search(r"\bmeet\b", t) is not None
        except Exception:
            return False

    def _to_utc_naive(dt: datetime) -> datetime:
        try:
            from datetime import timezone as _tz

            if getattr(dt, "tzinfo", None) is not None:
                return dt.astimezone(_tz.utc).replace(tzinfo=None)
        except Exception:
            pass
        return dt.replace(tzinfo=None)

    def _best_effort_extract(text: str, subject_fallback: str) -> tuple[Optional[str], Optional[datetime], Optional[datetime], str]:
        """
        Returns (summary, start_dt, end_dt, method).
        """
        reqs = detect_calendar_requests(text or "")
        if reqs:
            req = reqs[0]
            start_dt, end_dt = parse_datetime_from_text(req.get("full_match", "") or "", reference_dt=user_now)
            summary = (req.get("description") or subject_fallback or "Meeting").strip()
            if start_dt:
                return summary, start_dt, end_dt, "regex"

        # Fallback: try parsing from subject line alone
        start_dt, end_dt = parse_datetime_from_text(subject_fallback or "", reference_dt=user_now)
        if start_dt:
            return (subject_fallback or "Meeting").strip(), start_dt, end_dt, "subject_parse"

        return None, None, None, "none"

    def _llm_extract(subject: str, sender: str, snippet: str, body: str) -> Optional[Dict[str, Any]]:
        import json
        import re

        from app.services.llm_service import get_llm_service

        llm = get_llm_service()
        prompt = f"""Extract calendar event details from this EMAIL.

EMAIL:
From: {sender}
Subject: {subject}
Snippet: {snippet}
Body (truncated):
{(body or '')[:1500]}

Return ONLY valid JSON with keys:
- summary (string, required)
- start_time (string, required; can be natural language like "tomorrow at 2pm" if exact time not explicit)
- end_time (string|null, optional)
- location (string|null, optional)

If there is no clear meeting/event invitation, return: {{"create": false}}
Otherwise return: {{"create": true, "summary": "...", "start_time": "...", "end_time": null, "location": null}}"""

        text = llm.chat_completion_text(
            messages=[
                {"role": "system", "content": "You extract calendar event details from emails. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=220,
        )

        raw = (text or "").strip()
        # best-effort JSON extraction
        try:
            return json.loads(raw)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                return None
            try:
                return json.loads(m.group(0))
            except Exception:
                return None

    # Resolve user's timezone once per worker run.
    try:
        from zoneinfo import ZoneInfo

        tz_name = get_effective_user_timezone(user_id)
        user_tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        user_tz = None

    user_now = datetime.now(user_tz) if user_tz else datetime.utcnow()

    for _ in range(max(1, min(int(max_items or 25), 200))):
        doc = _claim_next_email(user_id=user_id, job_field="calendar", batch_id=batch_id, worker_id=worker_id)
        if not doc:
            break

        processed += 1
        try:
            # Dedupe: never create twice for same ingested email doc
            current_message_id = doc.get("message_id") or ""
            last_event_message_id = doc.get("calendar_event_message_id") or ""
            if (doc.get("calendar_event_id") or doc.get("calendar_event_created_at")) and current_message_id and last_event_message_id == current_message_id:
                skipped += 1
                logger.info(f"[CAL] Skip already created message_id={current_message_id} thread={doc.get('thread_id')}")
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="calendar",
                    status=JOB_SKIPPED,
                    extra_set={"calendar_skip_reason": "already_created_for_message"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            category = (doc.get("category") or "").strip().lower()
            if category in SKIP_CATEGORIES:
                skipped += 1
                logger.info(f"[CAL] Skip noise category={category} thread={doc.get('thread_id')}")
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="calendar",
                    status=JOB_SKIPPED,
                    extra_set={"calendar_skip_reason": f"noise_category:{category}"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            subject = doc.get("subject") or "(No subject)"
            sender = doc.get("from") or ""
            snippet = (doc.get("snippet") or "")[:500]
            body = (doc.get("body_temp") or "")[:4000]
            combined = f"{subject}\n{snippet}\n{body}"

            if not _looks_like_meeting(combined):
                skipped += 1
                logger.info(f"[CAL] Skip no meeting hints thread={doc.get('thread_id')}")
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="calendar",
                    status=JOB_SKIPPED,
                    extra_set={"calendar_skip_reason": "no_meeting_hints"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            summary, start_dt, end_dt, method = _best_effort_extract(combined, subject_fallback=subject)

            location = ""
            if not start_dt:
                extracted = _llm_extract(subject=subject, sender=sender, snippet=snippet, body=body)
                if extracted and extracted.get("create") is True:
                    summary = (extracted.get("summary") or subject or "Meeting").strip()
                    start_text = (extracted.get("start_time") or "").strip()
                    end_text = (extracted.get("end_time") or None)
                    location = (extracted.get("location") or "") or ""

                    # Parse natural language into datetimes (fallback to detect_requests parser)
                    start_dt, end_dt = parse_datetime_from_text(start_text, reference_dt=user_now)
                    if not start_dt:
                        # last resort: try parsing from subject/body again
                        _, start_dt, end_dt, _ = _best_effort_extract(combined, subject_fallback=subject)
                    method = "llm" if start_dt else "llm_parse_failed"

            if not start_dt:
                skipped += 1
                logger.info(f"[CAL] Skip could not parse datetime method={method} thread={doc.get('thread_id')}")
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="calendar",
                    status=JOB_SKIPPED,
                    extra_set={"calendar_skip_reason": f"could_not_parse_datetime:{method}"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            # Standardize meeting event titles to "Meeting with <sender>".
            # We do this because subject-derived summaries are often junk ("lets", "re:", etc.)
            try:
                name = _extract_sender_name(sender)
                if name:
                    summary = f"Meeting with {name}"
            except Exception:
                pass

            if not end_dt:
                end_dt = start_dt + timedelta(hours=1)

            # Avoid creating events in the past (simple guard)
            if _to_utc_naive(start_dt) < (_now() - timedelta(minutes=10)):
                skipped += 1
                logger.info(f"[CAL] Skip start in past start={start_dt} thread={doc.get('thread_id')}")
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="calendar",
                    status=JOB_SKIPPED,
                    extra_set={"calendar_skip_reason": "start_in_past"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            description = f"Created from email.\n\nFrom: {sender}\nSubject: {subject}\n\nSnippet:\n{(doc.get('snippet') or '')[:500]}"

            res = create_calendar_event(
                user_id=user_id,
                summary=str(summary or "Meeting")[:160],
                start_time=start_dt.isoformat(),
                end_time=end_dt.isoformat(),
                description=description[:1500],
                location=(location or "")[:200],
                attendees=None,
                timezone=tz_name,
                provider=None,
            )

            if not res.get("success"):
                skipped += 1
                logger.warning(
                    f"[CAL] Create failed thread={doc.get('thread_id')} message_id={current_message_id} "
                    f"error={res.get('error', 'unknown')!r}"
                )
                _mark_job_done(
                    email_doc_id=doc["_id"],
                    job_field="calendar",
                    status=JOB_SKIPPED,
                    extra_set={"calendar_skip_reason": f"calendar_create_failed:{res.get('error', 'unknown')}"},
                )
                _maybe_delete_body_temp(doc["_id"])
                continue

            created += 1
            logger.info(
                f"[CAL] Created event thread={doc.get('thread_id')} message_id={current_message_id} "
                f"start={start_dt.isoformat()} tz={tz_name}"
            )
            _mark_job_done(
                email_doc_id=doc["_id"],
                job_field="calendar",
                extra_set={
                    "calendar_event_id": res.get("event_id"),
                    "calendar_event_html_link": res.get("html_link", ""),
                    "calendar_event_provider": res.get("provider", ""),
                    "calendar_event_summary": res.get("summary", summary),
                    "calendar_event_start": res.get("start", start_dt.isoformat()),
                    "calendar_event_end": res.get("end", end_dt.isoformat()),
                    "calendar_event_created_at": _now(),
                    "calendar_event_message_id": current_message_id,
                    "calendar_create_method": method,
                },
            )
            _maybe_delete_body_temp(doc["_id"])

        except Exception as e:
            failed += 1
            _mark_job_done(email_doc_id=doc["_id"], job_field="calendar", error=str(e))
            _maybe_delete_body_temp(doc["_id"])

    return {
        "success": True,
        "processed": processed,
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "worker_id": worker_id,
    }


def run_linking_worker(
    user_id: str,
    batch_id: Optional[str] = None,
    max_items: int = 100,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Link tasks/facts produced from an email thread to the relationship entities.

    Requirement:
    - Relationship entities are updated first by RelationshipsWorker.
    - Linking happens only once tasks/facts exist.
    """
    worker_id = worker_id or f"link-{uuid4().hex[:6]}"
    processed = 0
    linked_tasks = 0
    linked_facts = 0
    skipped = 0
    failed = 0

    from app.services.relationships_service import get_relationships_service
    from app.memory.models import get_memory_facts_collection
    from app.memory.task_models import get_events_collection, get_aivis_tasks_collection

    rel_service = get_relationships_service()
    facts_col = get_memory_facts_collection()
    events_col = get_events_collection()
    aivis_tasks_col = get_aivis_tasks_collection()

    db = get_db()
    emails_col = db.db["emails"] if (db.is_connected and db.db is not None) else None
    if emails_col is None:
        return {"success": False, "error": "Database not connected"}

    for _ in range(max(1, min(int(max_items or 100), 1000))):
        # Linking can only happen once relationships + tasks are finished (or skipped),
        # and after facts are finished (or skipped). We still allow linking even if tasks/facts were skipped.
        doc = _claim_next_email(user_id=user_id, job_field="linking", batch_id=batch_id, worker_id=worker_id)
        if not doc:
            break
        processed += 1

        try:
            # If prerequisite workers are not done, re-queue by marking pending again.
            doneish = {JOB_DONE, JOB_SKIPPED}
            if doc.get("relationships_status") not in doneish or doc.get("tasks_status") not in doneish or doc.get("facts_status") not in doneish:
                emails_col.update_one({"_id": doc["_id"]}, {"$set": {"linking_status": JOB_PENDING}})
                skipped += 1
                continue

            contacts = doc.get("relationship_contacts") or []
            if not contacts:
                _mark_job_done(email_doc_id=doc["_id"], job_field="linking", status=JOB_SKIPPED, extra_set={"linking_skip_reason": "no_contacts"})
                _maybe_delete_body_temp(doc["_id"])
                continue

            thread_id = doc.get("thread_id", "")
            source_ref = f"email:{thread_id}"

            # Gather fact IDs for this thread
            fact_ids: List[Any] = []
            if facts_col is not None and thread_id:
                fact_ids = [f["_id"] for f in facts_col.find({"user_id": user_id, "source_ref": source_ref, "is_active": True}, {"_id": 1})]

            # Gather Aivis task IDs for this thread by joining events -> tasks
            task_ids: List[str] = []
            if events_col is not None and aivis_tasks_col is not None and thread_id:
                event_docs = list(events_col.find({"user_id": user_id, "data.thread_id": thread_id}, {"_id": 1}))
                event_ids = [e["_id"] for e in event_docs]
                if event_ids:
                    task_ids = [t["_id"] for t in aivis_tasks_col.find({"user_id": user_id, "source_event": {"$in": event_ids}}, {"_id": 1})]

            # Link to each contact
            for contact_email in contacts:
                if task_ids:
                    if rel_service.link_tasks(user_id, contact_email, task_ids):
                        linked_tasks += len(task_ids)
                if fact_ids:
                    if rel_service.link_facts(user_id, contact_email, [str(fid) for fid in fact_ids]):
                        linked_facts += len(fact_ids)

            _mark_job_done(
                email_doc_id=doc["_id"],
                job_field="linking",
                extra_set={
                    "linked_task_count": len(task_ids),
                    "linked_fact_count": len(fact_ids),
                },
            )
            _maybe_delete_body_temp(doc["_id"])

        except Exception as e:
            failed += 1
            _mark_job_done(email_doc_id=doc["_id"], job_field="linking", error=str(e))
            _maybe_delete_body_temp(doc["_id"])

    return {
        "success": True,
        "processed": processed,
        "linked_tasks": linked_tasks,
        "linked_facts": linked_facts,
        "skipped": skipped,
        "failed": failed,
        "worker_id": worker_id,
    }


# ──────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────

def enqueue_login_email_pipeline(user_id: str, max_emails: int = 20, provider: Optional[str] = None) -> str:
    """
    Enqueue ingestion + parallel workers for the latest emails.

    Ingestion runs first, then worker jobs run in parallel (requires queue workers >= 4).
    """
    from app.memory.background_jobs import get_job_queue

    job_queue = get_job_queue()

    def _orchestrate():
        ingest_res = ingest_latest_emails(user_id=user_id, max_emails=max_emails, provider=provider)
        if not ingest_res.get("success"):
            logger.error(f"Login email ingest failed for {user_id}: {ingest_res.get('error')}")
            return

        batch_id = ingest_res.get("batch_id")
        # Enqueue worker jobs (parallel)
        job_queue.enqueue(run_facts_worker, user_id, batch_id, job_id=f"facts-{user_id}-{batch_id}")
        job_queue.enqueue(run_relationships_worker, user_id, batch_id, job_id=f"rels-{user_id}-{batch_id}")
        job_queue.enqueue(run_tasks_worker, user_id, batch_id, job_id=f"tasks-{user_id}-{batch_id}")
        job_queue.enqueue(run_calendar_worker, user_id, batch_id, job_id=f"cal-{user_id}-{batch_id}")
        job_queue.enqueue(run_linking_worker, user_id, batch_id, job_id=f"link-{user_id}-{batch_id}")

    return job_queue.enqueue(_orchestrate, job_id=f"login-email-pipeline-{user_id}-{uuid4().hex[:6]}")


def enqueue_thread_email_pipeline(user_id: str, thread_ids: List[str], provider: Optional[str] = None) -> str:
    """
    Enqueue ingestion + parallel workers for a specific list of thread IDs.
    Used by Gmail Pub/Sub push processing.
    """
    from app.memory.background_jobs import get_job_queue

    job_queue = get_job_queue()

    def _orchestrate():
        ingest_res = ingest_threads(user_id=user_id, thread_ids=thread_ids, provider=provider)
        if not ingest_res.get("success"):
            logger.error(f"Thread ingest failed for {user_id}: {ingest_res.get('error')}")
            return

        batch_id = ingest_res.get("batch_id")
        job_queue.enqueue(run_facts_worker, user_id, batch_id, job_id=f"facts-{user_id}-{batch_id}")
        job_queue.enqueue(run_relationships_worker, user_id, batch_id, job_id=f"rels-{user_id}-{batch_id}")
        job_queue.enqueue(run_tasks_worker, user_id, batch_id, job_id=f"tasks-{user_id}-{batch_id}")
        job_queue.enqueue(run_calendar_worker, user_id, batch_id, job_id=f"cal-{user_id}-{batch_id}")
        job_queue.enqueue(run_linking_worker, user_id, batch_id, job_id=f"link-{user_id}-{batch_id}")

    return job_queue.enqueue(_orchestrate, job_id=f"thread-email-pipeline-{user_id}-{uuid4().hex[:6]}")

