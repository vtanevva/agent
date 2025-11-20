import os
from typing import Optional, List, Dict

from dotenv import load_dotenv

load_dotenv()


def run_gmail_autogen(user_id: str, message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Run a lightweight AutoGen conversation for Gmail tasks using existing tools.
    This function requires the 'autogen' package; if not installed, a helpful
    message is returned instead of raising.
    """
    try:
        # AutoGen v0.2.x API
        from autogen import AssistantAgent, UserProxyAgent, register_function
    except Exception as e:  # pragma: no cover - graceful fallback
        return (
            "AutoGen is not installed. Please install it first:\n"
            "pip install 'pyautogen>=0.2.0'\n"
            f"Details: {e}"
        )

    # Import existing tool implementations
    from app.tools.gmail_list import list_recent_emails as _list_recent_emails
    from app.tools.gmail_mail import send_email as _send_email
    from app.tools.gmail_reply import reply_email as _reply_email
    from app.tools.gmail_style import analyze_email_style as _analyze_email_style
    from app.tools.gmail_style import generate_reply_draft as _generate_reply_draft

    # Wrap tools to implicitly inject user_id (the LLM shouldn't have to provide it)
    def list_recent_emails(max_results: int = 5) -> str:
        return _list_recent_emails(user_id=user_id, max_results=max_results)

    def send_email(to: str, subject: Optional[str] = None, body: Optional[str] = None) -> str:
        return _send_email(user_id=user_id, to=to, subject=subject, body=body)

    def reply_email(thread_id: str, to: str, body: str, subj_prefix: str = "Re:") -> str:
        return _reply_email(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            body=body,
            subj_prefix=subj_prefix,
        )

    def analyze_email_style(max_samples: int = 10) -> str:
        return _analyze_email_style(user_id=user_id, max_samples=max_samples)

    def generate_reply_draft(thread_id: str, to: str, user_points: str = "", max_samples: int = 10) -> str:
        return _generate_reply_draft(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            user_points=user_points,
            max_samples=max_samples,
        )

    # LLM configuration
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    api_key = os.getenv("OPENAI_API_KEY")
    llm_config = {
        "config_list": [{"model": model, "api_key": api_key}],
        "timeout": 60,
    }

    system_message = (
        "You are a focused Gmail agent. Choose a tool when the user asks to:\n"
        "- list inbox threads (list_recent_emails)\n"
        "- send a new email (send_email)\n"
        "- reply in an existing thread by threadId/messageId (reply_email)\n"
        "Keep responses concise and execute a tool exactly once when appropriate."
    )

    assistant = AssistantAgent(
        name="gmail_agent",
        system_message=system_message,
        llm_config=llm_config,
    )

    user_proxy = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
    )

    # Register tools for the assistant (caller) to be executed by the user proxy (executor)
    register_function(
        list_recent_emails,
        caller=assistant,
        executor=user_proxy,
        name="list_recent_emails",
        description="Return a JSON array of the user's latest received inbox threads.",
    )
    register_function(
        send_email,
        caller=assistant,
        executor=user_proxy,
        name="send_email",
        description="Send an email via the user's Gmail account.",
    )
    register_function(
        reply_email,
        caller=assistant,
        executor=user_proxy,
        name="reply_email",
        description="Send a reply inside an existing Gmail thread.",
    )
    register_function(
        analyze_email_style,
        caller=assistant,
        executor=user_proxy,
        name="analyze_email_style",
        description="Analyze user's writing style from recent Sent emails and return a JSON profile.",
    )
    register_function(
        generate_reply_draft,
        caller=assistant,
        executor=user_proxy,
        name="generate_reply_draft",
        description="Generate a reply draft for a thread, emulating user's style.",
    )

    # Initiate a short tool-oriented conversation. History is not wired into AutoGen yet,
    # but we keep the parameter for future threading integration.
    chat_result = user_proxy.initiate_chat(assistant, message=message, max_turns=2)

    # Best-effort extraction of the assistant's last message
    try:
        # AutoGen stores messages per counterpart; fetch messages sent to the user_proxy
        messages = assistant.chat_messages.get(user_proxy, []) if hasattr(assistant, "chat_messages") else []
        if isinstance(messages, list) and messages:
            last = messages[-1]
            content = last.get("content") if isinstance(last, dict) else None
            if content:
                return content
        # Fallback to stringifying the chat result if structure differs
        return str(chat_result) if chat_result is not None else "Done."
    except Exception:
        return "Done."


