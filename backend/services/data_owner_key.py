"""
Stable per-user data partition for SQLite `clients` / projects.

A logical user is identified by the chosen login (``app_user_id``) plus the linked
mailbox email when available. This prevents two people who share the same login
name from sharing workstreams, while still allowing a single account to be keyed
consistently across ingest and the app.
"""

from __future__ import annotations

# Unlikely in emails/names; keeps composite keys unambiguous in SQL/JSON.
_OWNER_SEP = "\x1f"

UNSCOPED = "__unscoped__"


def data_owner_key_for_session(*, app_user_id: str | None) -> str:
    """
    Build the same partition key used at ingest for a given in-app user id
    (``Home``/``Menu`` `userId` / ``profile_link.user_id``).
    """
    from storage.sqlite_db import get_gmail_for_app_user  # local import avoids cycles

    uid = (app_user_id or "").strip().lower()
    if not uid:
        return UNSCOPED
    if "@" in uid:
        return f"{uid}{_OWNER_SEP}{uid.split('@', 1)[0]}"
    em = get_gmail_for_app_user(uid)
    if em:
        return f"{em}{_OWNER_SEP}{uid}"
    return f"{_OWNER_SEP}{uid}"


def data_owner_key_for_ingest(
    *,
    app_user_id: str | None,
    workspace_email: str | None = None,
) -> str:
    """
    Build partition key for unified ingest (Gmail/Slack/chat).

    If ``app_user_id`` is a Gmail address (contains ``@``), that anchor wins.
    Otherwise, prefer the linked profile email, then the mailbox on the event.
    """
    from storage.sqlite_db import get_gmail_for_app_user, get_user_id_for_gmail_address

    uid = (app_user_id or "").strip().lower()
    if "@" in uid:
        return f"{uid}{_OWNER_SEP}{uid.split('@', 1)[0]}"

    if uid:
        em = get_gmail_for_app_user(uid)
        wem = (workspace_email or "").strip().lower() or None
        if not em and wem:
            em = wem
        if em:
            return f"{em}{_OWNER_SEP}{uid}"
        return f"{_OWNER_SEP}{uid}"

    wem = (workspace_email or "").strip().lower() or None
    if wem:
        other = get_user_id_for_gmail_address(wem)
        if other:
            return f"{wem}{_OWNER_SEP}{other}"
        return f"{wem}{_OWNER_SEP}"

    return UNSCOPED
