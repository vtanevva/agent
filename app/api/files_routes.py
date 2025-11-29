"""File upload and processing API routes."""

import os
import base64
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from typing import Optional

from app.services.file_processor import (
    encode_image_bytes_to_base64,
    detect_file_type,
    get_mime_type,
)
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

files_bp = Blueprint('files', __name__, url_prefix='/api/files')

# Allowed file extensions
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.doc'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOCUMENT_EXTENSIONS

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    from pathlib import Path
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@files_bp.route("/upload", methods=["POST"])
def upload_file():
    """
    Upload and process a file (image, PDF, DOCX).
    
    Returns base64-encoded data URI for images, or file info for documents.
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        user_id = request.form.get('user_id', 'anonymous')
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Read file
        file_bytes = file.read()
        
        # Check file size
        if len(file_bytes) > MAX_FILE_SIZE:
            return jsonify({
                "error": f"File too large. Max size: {MAX_FILE_SIZE / (1024 * 1024):.1f}MB"
            }), 400
        
        file_type = detect_file_type(file.filename)
        mime_type = get_mime_type(file.filename)
        
        result = {
            "success": True,
            "filename": secure_filename(file.filename),
            "file_type": file_type,
            "mime_type": mime_type,
            "size": len(file_bytes),
        }
        
        # For images, encode to base64
        if file_type == 'image':
            base64_data = encode_image_bytes_to_base64(file_bytes, mime_type)
            result["data_uri"] = base64_data
            result["message"] = "Image uploaded and encoded successfully"
        else:
            # For documents, store base64 for later processing
            base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
            result["base64_data"] = base64_encoded
            result["message"] = "Document uploaded successfully (text extraction not yet implemented)"
        
        logger.info(f"File uploaded: {file.filename} ({file_type}, {len(file_bytes)} bytes) by user {user_id}")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

