"""Best-effort user email / namespace resolution (Mongo helpers removed)."""


def get_user_email(user_id: str) -> str:
    uid = (user_id or "").strip().lower()
    return uid or "unknown"
