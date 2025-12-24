"""Email service using Resend API for sending transactional emails."""
import resend
import os
from typing import Optional
from dotenv import load_dotenv

from app.utils.logging_utils import get_logger

# Load environment variables from .env file
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Initialize Resend client
_api_key = None

def _get_resend_client():
    """Get or initialize the Resend client."""
    global _api_key
    
    if _api_key is None:
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            raise ValueError("RESEND_API_KEY environment variable is not set!")
        
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("RESEND_API_KEY is empty (only whitespace)!")
        
        resend.api_key = api_key
        _api_key = api_key
    
    return resend.Emails()


def send_waitlist_welcome_email(to_email: str, name: str) -> bool:
    """
    Send a welcome email to a new waitlist signup.
    
    Args:
        to_email: Recipient email address
        name: Recipient's name
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        logger.info(f"Attempting to send welcome email to {to_email} for {name}")
        emails = _get_resend_client()
        logger.debug("Resend client initialized successfully")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; 
                    line-height: 1.6; 
                    color: #012622; 
                    background: linear-gradient(135deg, #FDFFFC 0%, #F8FAF7 100%);
                    margin: 0;
                    padding: 20px;
                }}
                .container {{ 
                    max-width: 600px; 
                    margin: 0 auto; 
                }}
                .header {{ 
                    background: linear-gradient(135deg, #012622 0%, #011A1C 100%); 
                    color: #FDFFFC; 
                    padding: 40px 30px; 
                    text-align: center; 
                    border-radius: 12px 12px 0 0; 
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 700;
                }}
                .content {{ 
                    background: #FDFFFC; 
                    padding: 40px 30px; 
                    border: 1px solid rgba(50, 22, 31, 0.1); 
                    border-top: none; 
                    border-radius: 0 0 12px 12px;
                }}
                .content p {{
                    margin: 0 0 16px 0;
                    color: #012622;
                }}
                .content p:last-of-type {{
                    margin-bottom: 0;
                }}
                .footer {{ 
                    text-align: center; 
                    padding: 20px; 
                    color: #775B59; 
                    font-size: 14px; 
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to Aivis! 🎉</h1>
                </div>
                <div class="content">
                    <p>Hi {name},</p>
                    <p>Thank you for joining the Aivis waitlist! We're excited to have you on board.</p>
                    <p>Aivis is an AI layer designed to reduce unwanted phone usage by managing communication flow, priority decisions, and cross-app information search.</p>
                    <p>We'll keep you updated as we move closer to launch. Stay tuned!</p>
                    <p>Kind regards,<br>The Aivis Team</p>
                </div>
                <div class="footer">
                    <p>You're receiving this because you signed up for the Aivis waitlist.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        logger.debug(f"Sending email with from: Aivis <info@aivis.pw>, to: {to_email}")
        result = emails.send({
            "from": "Aivis <info@aivis.pw>",
            "to": to_email,
            "subject": "Welcome to the Aivis Waitlist! 🎉",
            "html": html_content
        })
        logger.debug(f"Email send result: {result}")
        logger.info(f"Successfully sent welcome email to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send welcome email to {to_email}: {e}", exc_info=True)
        return False


def send_email(to_email: str, subject: str, html_content: str, from_email: str = "Aivis <info@aivis.pw>") -> bool:
    """
    Send a generic email using Resend.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML content of the email
        from_email: Sender email (default: "Aivis <info@aivis.pw>")
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        emails = _get_resend_client()
        
        emails.send({
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "html": html_content
        })
        
        logger.info(f"Successfully sent email to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
        return False


# Test script (when run directly)
if __name__ == "__main__":
    send_waitlist_welcome_email(
        to_email="vanesa.taneva@gmail.com",
        name="Vanesa"
    )
    logger.info("Email sent successfully!")

