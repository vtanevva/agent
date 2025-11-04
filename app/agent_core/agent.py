"""Agent core module for tool-calling and agent orchestration"""

import os
import json
import openai
from dotenv import load_dotenv

from app.agent_core.tool_registry import all_openai_schemas, call

# Import calendar tools to register them
try:
    from app.tools.calendar_manager import create_calendar_event, list_calendar_events
except ImportError as e:
    print(f"Warning: Could not import calendar_manager tools: {e}")
except Exception as e:
    print(f"Error importing calendar tools: {e}")

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


def run_agent(user_id: str, message: str, history: list):
    """Run the chat‑>tool‑>narration loop and return the assistant’s reply."""

    tool_hint = {
        "role": "system",
        "content": (
            # ── outbound mail ─────────────────────────────────────────
            "If the user asks to email someone and an address is present, "
            "ALWAYS call the send_email tool exactly once. "
            "Invent a polite subject/body if missing.\n\n"
            # ── inbox listing ─────────────────────────────────────────
            "If the user asks to see recent mail, ALWAYS call the "
            "list_recent_emails tool once and reply ONLY with its raw JSON. "
            "This applies even if emails were shown before in the conversation.\n\n"
            # ── replying inside a thread ─────────────────────────────
            "If the user asks to reply to a Gmail thread and provides a threadId "
            "(or the UI pre‑fills 'Reply to thread <ID> to <email>: <body>'), "
            "ALWAYS call the reply_email tool exactly once. "
            "Use the threadId, recipient address, and body they provided. "
            "Do NOT call send_email in that case.\n\n"
            # ── calendar events ───────────────────────────────────────
            "If the user asks to see calendar events, schedule, appointments, or meetings, "
            "ALWAYS call the list_calendar_events tool once and reply ONLY with its raw JSON. "
            "If they want to schedule something, call create_calendar_event. "
            "Parse natural language for dates and times (e.g., 'tomorrow at 2pm', 'next Monday 3-4pm')."
        ),
    }

    messages = [tool_hint] + history + [{"role": "user", "content": message}]

    # ── detect listing‑mail queries and force tool choice ──────────────
    lower = message.lower()
    wants_list = any(
        phrase in lower
        for phrase in (
            # existing
            "recent email",
            "last email",
            "last 5 emails",
            "latest emails",
            "show my emails",
            "show inbox",
            # new synonyms
            "check emails",
            "check my emails",
            "check inbox",
            "past email",
            "past emails",
            "check past email",
            "check past emails",
            "old emails",
            "older emails",
            # additional phrases
            "past messages",
            "show past messages",
            "check past messages",
            "show me past messages",
        )
    )
    
    # ── detect calendar queries and force tool choice ──────────────
    wants_calendar = any(
        phrase in lower
        for phrase in (
            "calendar",
            "events",
            "schedule",
            "appointments",
            "meetings",
            "show my calendar",
            "calendar events",
        )
    )
    print(f"Email detection: wants_list={wants_list}, message='{message}'")
    print(f"Calendar detection: wants_calendar={wants_calendar}, message='{message}'")
    
    # Debug: Print available tools
    available_tools = all_openai_schemas()
    print(f"Available tools: {[tool['function']['name'] for tool in available_tools]}")
    
    if wants_list:
        forced_choice = {"type": "function", "function": {"name": "list_recent_emails"}}
        print(f"Forcing email list tool choice: {forced_choice}")
    elif wants_calendar:
        forced_choice = {"type": "function", "function": {"name": "list_calendar_events"}}
        print(f"Forcing calendar tool choice: {forced_choice}")
    else:
        forced_choice = "auto"
    # -------------------------------------------------------------------

    # 1 – first pass: GPT chooses / is forced to a tool
    print(f"Making OpenAI call with forced_choice: {forced_choice}")
    first = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=all_openai_schemas(),
        tool_choice=forced_choice,
    )
    assistant_msg = first.choices[0].message
    print(f"Assistant message content: {assistant_msg.content}")
    print(f"Tool calls: {getattr(assistant_msg, 'tool_calls', [])}")
    messages.append(assistant_msg)

    # 2 – execute tool calls (if any)
    tool_calls = getattr(assistant_msg, "tool_calls", []) or []
    print(f"Number of tool calls to execute: {len(tool_calls)}")
    
    for tc in tool_calls:
        # Handle both old and new API formats
        try:
            # New API format (OpenAI v1.0+)
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            tool_call_id = tc.id
        except (AttributeError, TypeError):
            # Old API format (fallback)
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])
            tool_call_id = tc["id"]
        
        fn_args["user_id"] = user_id            # enforce real user_id
        
        print(f"Executing tool: {fn_name} with args: {fn_args}")

        tool_result = call(fn_name, **fn_args)
        print(f"Tool result: {tool_result}")

        # ── NEW: short‑circuit for inbox listing ───────────────
        if fn_name == "list_recent_emails":
            print("Short-circuiting for list_recent_emails")
            print(f"Tool result type: {type(tool_result)}")
            print(f"Tool result content: {tool_result[:200] if len(str(tool_result)) > 200 else tool_result}")
            return tool_result                  # raw JSON back to UI
        # ── NEW: short‑circuit for calendar listing ───────────────
        if fn_name == "list_calendar_events":
            print("Short-circuiting for list_calendar_events")
            return tool_result                  # raw JSON back to UI
        # ────────────────────────────────────────────────────────

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": fn_name,
                "content": tool_result,
            }
        )


    # 3 – final pass: GPT narrates result or returns raw JSON
    final = openai.chat.completions.create(model="gpt-4o-mini", messages=messages)
    return final.choices[0].message.content
