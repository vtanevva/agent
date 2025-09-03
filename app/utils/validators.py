import re
from typing import Optional, Dict, Any
from .error_handler import ValidationError

class InputValidator:
    """Input validation and sanitization utilities"""
    
    # Email validation regex
    EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    # User ID validation (alphanumeric + hyphens, 3-50 chars)
    USER_ID_REGEX = re.compile(r'^[a-zA-Z0-9-]{3,50}$')
    
    # Session ID validation (alphanumeric + hyphens, 8-100 chars)
    SESSION_ID_REGEX = re.compile(r'^[a-zA-Z0-9-]{8,100}$')
    
    # Message content validation (basic XSS prevention)
    MESSAGE_REGEX = re.compile(r'^[^<>{}]*$')
    
    @classmethod
    def validate_email(cls, email: str) -> str:
        """Validate and sanitize email address"""
        if not email or not isinstance(email, str):
            raise ValidationError("Email address is required")
        
        email = email.strip().lower()
        if not cls.EMAIL_REGEX.match(email):
            raise ValidationError("Invalid email address format")
        
        if len(email) > 254:  # RFC 5321 limit
            raise ValidationError("Email address too long")
            
        return email
    
    @classmethod
    def validate_user_id(cls, user_id: str) -> str:
        """Validate and sanitize user ID"""
        if not user_id or not isinstance(user_id, str):
            raise ValidationError("User ID is required")
        
        user_id = user_id.strip().lower()
        if not cls.USER_ID_REGEX.match(user_id):
            raise ValidationError("Invalid user ID format (alphanumeric + hyphens, 3-50 chars)")
            
        return user_id
    
    @classmethod
    def validate_session_id(cls, session_id: str) -> str:
        """Validate and sanitize session ID"""
        if not session_id or not isinstance(session_id, str):
            raise ValidationError("Session ID is required")
        
        session_id = session_id.strip()
        if not cls.SESSION_ID_REGEX.match(session_id):
            raise ValidationError("Invalid session ID format")
            
        return session_id
    
    @classmethod
    def validate_message(cls, message: str, max_length: int = 2000) -> str:
        """Validate and sanitize chat message"""
        if not message or not isinstance(message, str):
            raise ValidationError("Message is required")
        
        message = message.strip()
        if len(message) > max_length:
            raise ValidationError(f"Message too long (max {max_length} characters)")
        
        if not cls.MESSAGE_REGEX.match(message):
            raise ValidationError("Message contains invalid characters")
            
        return message
    
    @classmethod
    def validate_chat_request(cls, data: Dict[str, Any]) -> Dict[str, str]:
        """Validate chat API request data"""
        if not isinstance(data, dict):
            raise ValidationError("Invalid request format")
        
        validated = {}
        
        # Validate message
        message = data.get("message", "").strip()
        validated["message"] = cls.validate_message(message)
        
        # Validate user_id
        user_id = data.get("user_id", "anonymous")
        validated["user_id"] = cls.validate_user_id(user_id)
        
        # Validate session_id (optional)
        session_id = data.get("session_id")
        if session_id:
            validated["session_id"] = cls.validate_session_id(session_id)
        
        return validated
    
    @classmethod
    def sanitize_html(cls, text: str) -> str:
        """Basic HTML sanitization"""
        if not text:
            return ""
        
        # Remove potentially dangerous HTML tags
        dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input']
        for tag in dangerous_tags:
            text = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(f'<{tag}[^>]*/?>', '', text, flags=re.IGNORECASE)
        
        # Remove onclick, onload, etc. attributes
        text = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    @classmethod
    def validate_oauth_state(cls, state: str) -> bool:
        """Validate OAuth state parameter"""
        if not state or not isinstance(state, str):
            return False
        
        # State should be alphanumeric and reasonable length
        return bool(re.match(r'^[a-zA-Z0-9]{10,100}$', state))
