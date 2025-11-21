import os
from typing import Optional, List, Dict, Any

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
    from app.tools.gmail_detail import get_thread_detail as _get_thread_detail
    from app.utils.oauth_utils import load_google_credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from app import chat_embeddings as mem

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

    # ──────────────────────────────────────────────────────────────────
    # Additional tools to match requested GmailAgent API
    # ──────────────────────────────────────────────────────────────────
    def list_emails(label: str = "INBOX", max_results: int = 50) -> list:
        """List threads for a Gmail label (default INBOX). Returns a list of dicts."""
        creds = load_google_credentials(user_id)
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        try:
            # Prefer threads.list for thread-level listing
            resp = svc.users().threads().list(
                userId="me",
                labelIds=[label] if label else None,
                maxResults=max_results,
            ).execute()
            threads = resp.get("threads", []) or []
            items: List[Dict[str, Any]] = []
            for idx, t in enumerate(threads, start=1):
                # Fetch first message metadata in thread
                th = svc.users().threads().get(userId="me", id=t["id"], format="metadata").execute()
                first = th.get("messages", [{}])[0]
                headers = {h["name"]: h["value"] for h in first.get("payload", {}).get("headers", [])}
                items.append({
                    "idx": idx,
                    "threadId": th.get("id"),
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", "(No subject)"),
                    "snippet": first.get("snippet", "")[:200],
                    "label": label or "",
                })
                if len(items) >= max_results:
                    break
            return items
        except Exception as e:
            return [{"error": f"list_emails failed: {e}"}]

    def get_email(email_id: str) -> dict:
        """Get a single email/thread detail by messageId or threadId."""
        try:
            result = _get_thread_detail(user_id=user_id, thread_id=email_id)
            # _get_thread_detail returns a JSON string
            import json as _json
            return _json.loads(result)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_emails(query: str, max_results: int = 20) -> list:
        """Search emails using Gmail search syntax; returns a list of thread summaries."""
        creds = load_google_credentials(user_id)
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        try:
            resp = svc.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results * 2,  # fetch extra to de-dup threads
            ).execute()
            msgs = resp.get("messages", []) or []
            seen_threads = set()
            results: List[Dict[str, Any]] = []
            for m in msgs:
                meta = svc.users().messages().get(
                    userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "From"]
                ).execute()
                t_id = meta.get("threadId")
                if t_id in seen_threads:
                    continue
                seen_threads.add(t_id)
                headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
                results.append({
                    "threadId": t_id,
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", "(No subject)"),
                    "snippet": meta.get("snippet", "")[:200],
                })
                if len(results) >= max_results:
                    break
            return results
        except Exception as e:
            return [{"error": f"search_emails failed: {e}"}]

    def embed_text(text: str) -> List[float]:
        """Return embedding vector for text."""
        try:
            vec = mem.embed_text(text)
            return [float(x) for x in vec]
        except Exception as e:
            return []

    def store_email_embedding(email_id: str, vector: List[float], metadata: Dict) -> None:
        """Store an email embedding into vector DB; best-effort if Pinecone is configured."""
        if getattr(mem, "index", None) is None:
            # No vector DB configured
            return
        try:
            ns = f"emails:{user_id}"
            vid = f"email:{email_id}"
            mem.index.upsert(
                vectors=[{"id": vid, "values": vector, "metadata": metadata or {}}],
                namespace=ns,
            )
        except Exception:
            # Swallow errors to keep tool robust
            return

    def retrieve_similar_emails(query: str, k: int = 5) -> List[Dict]:
        """Retrieve similar stored emails using vector search, if available."""
        if getattr(mem, "index", None) is None:
            return []
        try:
            ns = f"emails:{user_id}"
            vec = mem.embed_text(query)
            resp = mem.index.query(
                namespace=ns,
                vector=vec,
                top_k=k,
                include_metadata=True,
            )
            out = []
            for m in resp.matches:
                out.append({
                    "id": m.id,
                    "score": float(m.score),
                    "metadata": dict(m.metadata or {}),
                })
            return out
        except Exception:
            return []

    def detect_writing_style(samples: Optional[List[str]] = None) -> dict:
        """Return a style profile; use provided samples if given, else auto-analyze Sent emails."""
        try:
            if samples and len(samples) > 0:
                # Lightweight extraction via OpenAI
                import openai
                prompt = (
                    "Analyze the user's writing style from the provided email samples. "
                    "Return a concise JSON with fields: tone, formality (0-1), typical_phrases (array), "
                    "signature (string if present), bullet_preference (true/false), length_preference ('short'|'medium'|'long')."
                )
                messages = [{"role": "system", "content": "You are a precise writing style analyzer."},
                            {"role": "user", "content": prompt + "\n\nSamples:\n" + "\n\n---\n\n".join(samples[:5])}]
                resp = openai.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=messages,
                    temperature=0.2,
                    max_tokens=400,
                )
                import json as _json
                text = resp.choices[0].message.content.strip()
                try:
                    return _json.loads(text)
                except Exception:
                    return {"raw": text}
            # Fallback to built-in analyzer over Sent messages
            import json as _json
            raw = _analyze_email_style(user_id=user_id, max_samples=10)
            return _json.loads(raw)
        except Exception as e:
            return {"error": str(e)}

    def generate_reply_with_style(email: Dict, style_profile: Dict) -> str:
        """Generate a reply body given an email dict and style profile. Uses thread if available."""
        try:
            thread_id = email.get("threadId") or email.get("id")
            to = email.get("from")
            if thread_id and to:
                # Leverage existing style-aware draft generator
                return _generate_reply_draft(
                    user_id=user_id,
                    thread_id=thread_id,
                    to=to,
                    user_points="",
                    max_samples=10,
                )
            # Fallback: just produce a plain text body using LLM and style_profile
            import openai, json as _json
            style_json = _json.dumps(style_profile or {})
            subject = email.get("subject", "(No subject)")
            body = email.get("body") or email.get("snippet") or ""
            sys = "You draft concise, professional email replies following the provided style profile."
            usr = f"Subject: {subject}\n\nOriginal:\n{body}\n\nStyle profile:\n{style_json}\n\nWrite a reply body only."
            resp = openai.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": usr}],
                temperature=0.4,
                max_tokens=300,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Error generating styled reply: {e}"

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
    # Register extended API
    register_function(
        list_emails,
        caller=assistant,
        executor=user_proxy,
        name="list_emails",
        description="List threads for a Gmail label (default INBOX). Returns a list of dicts.",
    )
    register_function(
        get_email,
        caller=assistant,
        executor=user_proxy,
        name="get_email",
        description="Get a single email/thread detail by messageId or threadId.",
    )
    register_function(
        search_emails,
        caller=assistant,
        executor=user_proxy,
        name="search_emails",
        description="Search emails using Gmail search syntax; returns thread summaries.",
    )
    register_function(
        embed_text,
        caller=assistant,
        executor=user_proxy,
        name="embed_text",
        description="Return embedding vector for text.",
    )
    register_function(
        store_email_embedding,
        caller=assistant,
        executor=user_proxy,
        name="store_email_embedding",
        description="Store an email embedding with metadata in vector DB (if configured).",
    )
    register_function(
        retrieve_similar_emails,
        caller=assistant,
        executor=user_proxy,
        name="retrieve_similar_emails",
        description="Retrieve similar stored emails using vector search (if configured).",
    )
    register_function(
        detect_writing_style,
        caller=assistant,
        executor=user_proxy,
        name="detect_writing_style",
        description="Return a style profile from provided samples or from Sent messages.",
    )
    register_function(
        generate_reply_with_style,
        caller=assistant,
        executor=user_proxy,
        name="generate_reply_with_style",
        description="Generate a reply body given an email dict and style profile.",
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


