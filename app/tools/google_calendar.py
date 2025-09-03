from datetime import datetime
from app.agent_core.tool_registry import register, ToolSchema

# ------------- fake implementation for now -------------------------
def add_event(user_id: str, summary: str, start_iso: str, end_iso: str):
    return (f"(demo) Added Google event «{summary}» "
            f"from {start_iso} to {end_iso} for {user_id}")

# --------- register with the global registry -----------------------
register(
    add_event,
    ToolSchema(
        name="add_event",
        description="Add a Google Calendar event for the user.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "summary": {"type": "string"},
                "start_iso": {"type": "string"},
                "end_iso": {"type": "string"}
            },
            "required": ["user_id", "summary", "start_iso", "end_iso"]
        }
    )
)
