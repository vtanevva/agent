"""
Task Pipeline API Routes - MVP Demo

Endpoints:
- POST /api/tasks/process-email - Process an email into tasks
- GET /api/tasks - Get user's tasks (filtered by priority)
- POST /api/tasks/:id/complete - Mark task as done
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from app.services.task_pipeline_service import get_task_pipeline_service
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


@tasks_bp.route("/ingest", methods=["POST"])
def ingest_and_process():
    """
    Trigger the login-style email pipeline (ingest + parallel workers).
    
    Request body:
    {
      "user_id": "user_123",
      "max_emails": 20  // optional, default 20
    }
    
    Response:
    {
      "success": true,
      "job_id": "login-email-pipeline-...",
      "message": "Email processing started"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        user_id = data.get("user_id")
        max_emails = data.get("max_emails", 20)
        
        if not user_id:
            return jsonify({"success": False, "error": "Missing user_id"}), 400
        
        from app.services.email_processing_pipeline import enqueue_login_email_pipeline

        job_id = enqueue_login_email_pipeline(user_id=user_id, max_emails=max_emails, provider="gmail")
        return jsonify({"success": True, "job_id": job_id, "message": "Email processing started"})
        
    except Exception as e:
        logger.error(f"Error in ingest: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@tasks_bp.route("/process-email", methods=["POST"])
def process_email():
    """
    Process a Gmail email through the task pipeline
    
    Request body:
    {
      "user_id": "user_123",
      "email": {
        "message_id": "msg_abc",
        "thread_id": "thread_123",
        "sender": "sam@company.com",
        "sender_name": "Sam Chen",
        "subject": "Can we confirm tomorrow?",
        "snippet": "Hey, just wanted to confirm...",
        "body": "Full email body...",
        "timestamp": "2026-01-28T09:12:00",
        "labels": ["INBOX", "UNREAD"]
      }
    }
    
    Response:
    {
      "success": true,
      "task_id": "aivis_abc123",
      "task": { ... AivisTask document ... }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        user_id = data.get("user_id")
        email_data = data.get("email")
        
        if not user_id or not email_data:
            return jsonify({"success": False, "error": "Missing user_id or email"}), 400
        
        # Parse timestamp if string
        if isinstance(email_data.get("timestamp"), str):
            try:
                email_data["timestamp"] = datetime.fromisoformat(email_data["timestamp"].replace("Z", "+00:00"))
            except Exception:
                email_data["timestamp"] = datetime.utcnow()
        
        # Process through pipeline
        pipeline = get_task_pipeline_service()
        task_id = pipeline.process_gmail_event(user_id, email_data)
        
        if not task_id:
            return jsonify({
                "success": True,
                "task_id": None,
                "message": "No actionable tasks found in this email"
            })
        
        # Fetch the created task
        tasks = pipeline.get_tasks_by_priority(user_id, limit=100)
        task = next((t for t in tasks if t["_id"] == task_id), None)
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "task": serialize_task(task) if task else None
        })
        
    except Exception as e:
        logger.error(f"Error processing email: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@tasks_bp.route("", methods=["GET"])
def get_tasks():
    """
    Get user's tasks, optionally filtered by priority
    
    Query params:
    - user_id: User ID (required)
    - priority: NOW|TODAY|THIS_WEEK|LATER|SOMEDAY (optional)
    - limit: Max tasks to return (default: 50)
    
    Response:
    {
      "success": true,
      "tasks": [ ... list of AivisTask documents ... ],
      "count": 10
    }
    """
    try:
        user_id = request.args.get("user_id")
        priority = request.args.get("priority")
        limit = int(request.args.get("limit", 50))
        
        if not user_id:
            return jsonify({"success": False, "error": "Missing user_id"}), 400
        
        pipeline = get_task_pipeline_service()
        tasks = pipeline.get_tasks_by_priority(user_id, priority, limit)
        
        return jsonify({
            "success": True,
            "tasks": [serialize_task(t) for t in tasks],
            "count": len(tasks)
        })
        
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@tasks_bp.route("/<task_id>/complete", methods=["POST"])
def complete_task(task_id: str):
    """
    Mark a task as completed
    
    Request body:
    {
      "user_id": "user_123"
    }
    
    Response:
    {
      "success": true,
      "task_id": "aivis_abc123"
    }
    """
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        
        if not user_id:
            return jsonify({"success": False, "error": "Missing user_id"}), 400
        
        pipeline = get_task_pipeline_service()
        success = pipeline.mark_task_done(user_id, task_id)
        
        if not success:
            return jsonify({"success": False, "error": "Task not found or already completed"}), 404
        
        return jsonify({
            "success": True,
            "task_id": task_id
        })
        
    except Exception as e:
        logger.error(f"Error completing task: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


def serialize_task(task: dict) -> dict:
    """Serialize a task document for JSON response (convert datetime to ISO string)"""
    if not task:
        return None
    
    serialized = task.copy()
    
    # Convert datetime fields to ISO strings
    for field in ["created_at", "updated_at", "completed_at", "due_datetime"]:
        if field in serialized and serialized[field]:
            if isinstance(serialized[field], datetime):
                serialized[field] = serialized[field].isoformat()
    
    return serialized
