"""File API routes for Google Drive operations."""

from flask import Blueprint, request, jsonify

from app.agents.file_agent import FileAgent
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

files_bp = Blueprint("files", __name__, url_prefix="/api/files")

# Initialize services (will be set by the main app)
llm_service = None
memory_service = None
file_agent = None


def init_file_routes(app, llm_svc, memory_svc):
    """Initialize file routes with services"""
    global llm_service, memory_service, file_agent
    llm_service = llm_svc
    memory_service = memory_svc
    file_agent = FileAgent(llm_service, memory_service)
    app.register_blueprint(files_bp)


@files_bp.route("/search", methods=["POST"])
def search_files():
    """
    Search for files related to a prompt.
    
    Request body:
    {
        "user_id": "user123",
        "query": "find my task list",
        "max_results": 10
    }
    """
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        query = data.get("query")
        max_results = data.get("max_results", 10)
        
        if not user_id or not query:
            return jsonify({"error": "Missing user_id or query"}), 400
        
        logger.info(f"File search request from {user_id}: {query}")
        
        result = file_agent.handle_chat(
            user_id=user_id,
            message=f"search for {query}",
        )
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in search_files: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@files_bp.route("/list", methods=["POST"])
def list_files():
    """
    List recent files.
    
    Request body:
    {
        "user_id": "user123",
        "max_results": 20
    }
    """
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        max_results = data.get("max_results", 20)
        
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        
        logger.info(f"List files request from {user_id}")
        
        result = file_agent.handle_chat(
            user_id=user_id,
            message="show recent files",
        )
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in list_files: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@files_bp.route("/by-type", methods=["POST"])
def list_files_by_type():
    """
    List files by specific type.
    
    Request body:
    {
        "user_id": "user123",
        "file_types": ["document", "spreadsheet"],
        "max_results": 20
    }
    """
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        file_types = data.get("file_types", [])
        max_results = data.get("max_results", 20)
        
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        
        if not file_types:
            return jsonify({"error": "Missing file_types"}), 400
        
        logger.info(f"List files by type request from {user_id}: {file_types}")
        
        file_type_msg = " and ".join(file_types)
        result = file_agent.handle_chat(
            user_id=user_id,
            message=f"show me {file_type_msg}",
        )
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in list_files_by_type: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@files_bp.route("/detail/<file_id>", methods=["GET"])
def get_file_detail(file_id: str):
    """
    Get details for a specific file.
    
    Query params:
    - user_id: User identifier
    """
    try:
        user_id = request.args.get("user_id")
        
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        
        logger.info(f"Get file detail request from {user_id}: {file_id}")
        
        result = file_agent.handle_chat(
            user_id=user_id,
            message=f"show file detail {file_id}",
        )
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in get_file_detail: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@files_bp.route("/sync", methods=["POST"])
def sync_files():
    """
    Trigger a background sync of file metadata.
    
    Request body:
    {
        "user_id": "user123"
    }
    """
    try:
        from app.services.file_service import sync_files_metadata
        
        data = request.get_json()
        user_id = data.get("user_id")
        
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        
        logger.info(f"File sync request from {user_id}")
        
        result = sync_files_metadata(user_id)
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error in sync_files: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
