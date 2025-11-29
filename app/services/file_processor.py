"""File processing service for handling images and documents."""

import base64
import io
from typing import Optional, Dict, Any
from pathlib import Path

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def encode_image_to_base64(file_path: str) -> Optional[str]:
    """
    Encode an image file to base64 string.
    
    Parameters
    ----------
    file_path : str
        Path to image file
        
    Returns
    -------
    str or None
        Base64 encoded string with data URI prefix, or None if error
    """
    try:
        with open(file_path, 'rb') as image_file:
            image_data = image_file.read()
            base64_encoded = base64.b64encode(image_data).decode('utf-8')
            
            # Determine MIME type from file extension
            ext = Path(file_path).suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            return f"data:{mime_type};base64,{base64_encoded}"
    except Exception as e:
        logger.error(f"Error encoding image to base64: {e}", exc_info=True)
        return None


def encode_image_bytes_to_base64(image_bytes: bytes, mime_type: str = 'image/jpeg') -> str:
    """
    Encode image bytes to base64 string.
    
    Parameters
    ----------
    image_bytes : bytes
        Image file bytes
    mime_type : str
        MIME type (e.g., 'image/jpeg', 'image/png')
        
    Returns
    -------
    str
        Base64 encoded string with data URI prefix
    """
    try:
        base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
        return f"data:{mime_type};base64,{base64_encoded}"
    except Exception as e:
        logger.error(f"Error encoding image bytes to base64: {e}", exc_info=True)
        return ""


def detect_file_type(filename: str) -> str:
    """
    Detect file type from filename.
    
    Parameters
    ----------
    filename : str
        Filename or path
        
    Returns
    -------
    str
        File type: 'image', 'pdf', 'docx', or 'unknown'
    """
    ext = Path(filename).suffix.lower()
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
    if ext in image_extensions:
        return 'image'
    
    if ext == '.pdf':
        return 'pdf'
    
    if ext in {'.docx', '.doc'}:
        return 'docx'
    
    return 'unknown'


def get_mime_type(filename: str) -> str:
    """
    Get MIME type from filename.
    
    Parameters
    ----------
    filename : str
        Filename or path
        
    Returns
    -------
    str
        MIME type
    """
    ext = Path(filename).suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.svg': 'image/svg+xml',
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
    }
    return mime_types.get(ext, 'application/octet-stream')

