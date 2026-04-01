import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def create_gmail_draft(
    service,
    to_email: str,
    subject: str,
    reply_text: str,
    thread_id: str | None = None,
    message_id: str | None = None,
):
    """
    Create a Gmail draft.
    If thread_id is provided, Gmail will try to associate the draft with that thread.
    """

    message = MIMEMultipart()
    message["To"] = to_email
    message["Subject"] = subject

    # Optional thread-style headers
    if message_id:
        message["In-Reply-To"] = message_id
        message["References"] = message_id

    msg = MIMEText(reply_text or "", "plain", "utf-8")
    message.attach(msg)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    body = {
        "message": {
            "raw": raw_message,
        }
    }

    if thread_id:
        body["message"]["threadId"] = thread_id

    draft = service.users().drafts().create(
        userId="me",
        body=body,
    ).execute()

    return draft["id"]