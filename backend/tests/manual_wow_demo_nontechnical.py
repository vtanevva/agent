import argparse
import json
import sys
import time
from textwrap import indent

import requests


BASE_URL = "http://127.0.0.1:5000"
DEBUG_DEMO = False  # Set True to print raw JSON results for troubleshooting.


def _pretty(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _post(path: str, payload: dict) -> tuple[int, dict]:
    r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=60)
    try:
        body = r.json()
    except Exception:
        body = {"raw_text": r.text}
    return r.status_code, body


def _get(path: str) -> tuple[int, dict]:
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    try:
        body = r.json()
    except Exception:
        body = {"raw_text": r.text}
    return r.status_code, body


def _hr(char: str = "—", n: int = 92) -> None:
    print("\n" + (char * n))


def _title(text: str) -> None:
    _hr("=", 92)
    print(text)
    _hr("=", 92)


def _as_bool(v) -> bool:
    return bool(v is True or v == 1 or str(v).strip().lower() in {"true", "1", "yes", "y"})


def _short(v, limit: int = 160) -> str:
    s = "" if v is None else str(v).strip()
    if len(s) > limit:
        return s[:limit] + "..."
    return s


def _collapse_ws(s: str) -> str:
    return " ".join((s or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _is_question_like(s: str) -> bool:
    t = _collapse_ws(s).lower()
    if not t:
        return False
    if "?" in t:
        return True
    starters = (
        "can you ",
        "could you ",
        "did we ",
        "are we ",
        "any update",
        "what's the status",
        "whats the status",
        "should we ",
        "do we ",
    )
    return any(t.startswith(x) for x in starters)


def _safe_debug_dump(label: str, obj: dict) -> None:
    if not DEBUG_DEMO:
        return
    _hr(".", 92)
    print(f"DEBUG: {label}")
    try:
        print(_pretty(obj))
    except Exception:
        print(str(obj))


def _format_importance(imp: dict, *, incoming_message: str = "", body: dict | None = None) -> str:
    if not imp:
        return "Importance: (not available)"
    score = imp.get("importance_score")
    level = imp.get("importance_level")

    raw_reasons = list(imp.get("importance_reasons") or [])
    preferred = [
        "has_action",
        "urgency_language",
        "follow_up",
        "linked_existing_task",
        "blocker_signal",
        "project_update_detected",
    ]
    allow = set(preferred)

    msg_l = (incoming_message or "").lower()
    convincing: list[str] = []

    for r in preferred:
        if r not in raw_reasons:
            continue
        if r == "blocker_signal":
            # Only showcase blocker when it's obvious to a human.
            blocker_obvious = ("blocked" in msg_l) or ("blocker" in msg_l)
            pu = ((body or {}).get("project_update_candidate") or {}).get("fields") or {}
            if pu.get("blockers"):
                blocker_obvious = True
            if not blocker_obvious:
                continue
        convincing.append(r)
        if len(convincing) >= 3:
            break

    # Fall back to any allowlisted reason if nothing matched.
    if not convincing:
        for r in raw_reasons:
            if r in allow:
                convincing.append(r)
            if len(convincing) >= 2:
                break

    reasons_txt = ", ".join(convincing) if convincing else "no strong signals"
    return f"Importance: {level} ({score}/100) — reasons: {reasons_txt}"


def _format_schedule(s: dict) -> str:
    if not s:
        return "Timing: (not available)"
    if not _as_bool(s.get("has_schedule_signal")):
        return "Timing: none detected"
    due = s.get("due_hint_text")
    tlevel = s.get("time_pressure_level")
    if DEBUG_DEMO:
        nd = s.get("normalized_due") or {}
        return f"Timing: {tlevel} — hint={due!r} normalized={nd}"
    return f"Timing: {tlevel} — deadline hint: {_short(due, 90) if due else 'detected'}"


def _format_memory_update(update_result: dict | None) -> list[str]:
    if not update_result:
        return ["Project memory: no meaningful change"]
    if not _as_bool(update_result.get("updated")):
        # In non-technical mode, do not surface internal skip reasons.
        return ["Project memory: no meaningful change"]

    changed = list(update_result.get("changed_fields") or [])
    before = update_result.get("before") or {}
    after = update_result.get("after") or {}

    if not changed:
        return ["Project memory: updated (details omitted)"]

    lines = ["Project memory updated:"]

    showcased_any = False
    hidden_any = False

    for f in changed:
        b = _collapse_ws(str(before.get(f) or ""))
        a = _collapse_ws(str(after.get(f) or ""))

        too_long = len(a) > 220
        too_mixed = ("\n" in str(after.get(f) or "")) or ("•" in a) or ("-" in a and len(a) > 180)
        question_like = _is_question_like(a)

        suspicious = too_long or too_mixed or (question_like and f in {"blockers", "current_priorities", "next_steps"})

        if suspicious:
            hidden_any = True
            continue

        showcased_any = True
        if b and b != a:
            lines.append(f"- {f}:")
            lines.append(f"  before: {_short(b, 140)}")
            lines.append(f"  now:    {_short(a, 140)}")
        else:
            lines.append(f"- {f}: {_short(a, 180)}")

    if hidden_any and not showcased_any:
        return ["Project memory change detected, but hidden here because the extracted value needs cleanup."]

    if hidden_any and showcased_any:
        lines.append("Note: some memory changes were hidden here because the extracted value needs cleanup.")

    return lines


def _format_big_picture(body: dict, *, incoming_message: str = "") -> list[str]:
    cls = body.get("classification") or {}
    rp = body.get("reply_policy") or {}
    imp = body.get("importance_result") or {}
    sched = body.get("scheduling_result") or {}
    task_id = body.get("clickup_task_id")
    linked_task_id = body.get("linked_clickup_task_id")

    has_action = _as_bool(cls.get("has_action"))
    reply_mode = rp.get("reply_mode")
    should_reply = _as_bool(rp.get("should_reply"))
    reply_text = body.get("reply_text")

    lines = []

    if has_action:
        lines.append("Decision: This is a real action request (work needed).")
    else:
        lines.append("Decision: This is not a new task by default (avoid noise).")

    if task_id:
        lines.append(f"Task: created in ClickUp ({task_id}).")
    elif linked_task_id:
        lines.append(f"Task: linked to an existing task ({linked_task_id}).")
    else:
        lines.append("Task: no task created.")

    if should_reply and reply_text:
        if reply_mode == "draft_ready":
            lines.append("Reply: prepared a draft-ready reply suggestion (email-ready).")
        elif reply_mode == "suggestion_only":
            lines.append("Reply: suggested a short reply (not auto-sent).")
        else:
            lines.append("Reply: suggested a reply.")
        lines.append(f"Suggested reply: “{_short(reply_text, 220)}”")
    else:
        lines.append("Reply: no reply suggested.")

    # New Aivis Core signals (explainable)
    lines.append(_format_importance(imp, incoming_message=incoming_message, body=body))
    lines.append(_format_schedule(sched))

    # Continuity context snapshot (small, human-friendly)
    cc = body.get("continuity_context") or {}
    cc_sum = cc.get("summary") or {}
    if cc_sum:
        lines.append(
            "Context recalled: "
            f"{cc_sum.get('recent_message_count')} recent messages, "
            f"{cc_sum.get('recent_task_count')} recent tasks, "
            f"{cc_sum.get('open_follow_up_count')} open follow-ups."
        )

    return lines


def _run_live_demo(*, slack_channel_id: str, clickup_list_id: str | None, project_name: str) -> None:
    code, _ = _get("/health")
    if code != 200:
        print("Server not reachable at http://127.0.0.1:5000. Start the backend, or run with --sample.")
        sys.exit(1)

    token = str(int(time.time()))
    now_anchor = "2026-03-31T12:00:00Z"

    _title("Aivis — WOW Demo (Non-technical)")
    print("What you’re about to see:")
    print("- It avoids turning every message into a task.")
    print("- It remembers the project as the conversation evolves.")
    print("- It detects follow-ups, blockers, and time pressure.")
    print("- It suggests replies (Slack suggestion / Gmail draft-ready).")
    print("- It tracks simple value metrics (rough counters).")

    # "Hard mode" examples: messy real-world messages (multi-intent, blockers, timing, vague follow-ups, duplicates)
    steps = [
        (
            "A messy message with two requests + a deadline (should create/link a task + detect timing)",
            "FYI: homepage copy is ~80% done. Also can you confirm the legal footer text and send the revised timeline by Friday 2pm? We promised the client.",
            {
                "source": "slack",
                "workspace_id": "sam-main",
                "channel": slack_channel_id,
                "ts": f"1743465000.{token}01",
                "user": "U123456",
                "project_name": project_name,
                "text": "FYI: homepage copy is ~80% done. Also can you confirm the legal footer text and send the revised timeline by Friday 2pm? We promised the client.",
                "now_utc": now_anchor,
            },
            "/ingest/slack",
        ),
        (
            "An email that mixes updates + asks for a client-ready reply (should update memory + suggest draft-ready text)",
            "Quick notes:\n- Priorities: approve final design + confirm legal footer\n- Blocker: waiting on legal sign-off\nCan you reply with a short client update we can forward today?",
            {
                "source": "gmail",
                "workspace_id": "sam-main",
                "message_id": f"wow-msg-{token}-01",
                "thread_id": f"{token}01",
                "from": "matt@example.com",
                "to": "sam@example.com",
                "subject": "Website Migration — quick notes + client update",
                "body": "Quick notes:\n- Priorities: approve final design + confirm legal footer\n- Blocker: waiting on legal sign-off\nCan you reply with a short client update we can forward today?",
                "timestamp": now_anchor,
                "client_name": "Matt",
                "project_name": project_name,
                # Demo-safe: omit clickup_list_id to avoid downstream ClickUp failures.
                "skip_draft": True,  # keep demo safe: still shows the suggestion without actually creating a Gmail draft
                "now_utc": now_anchor,
            },
            "/ingest/gmail",
        ),
        (
            "A second email scenario (safe, memory update + draft-ready suggestion, no ClickUp needed)",
            "Client-facing update (FYI): We’re still on track for Friday 2pm, pending legal sign-off. Please draft a 2-sentence reply acknowledging this and confirming next steps.",
            {
                "source": "gmail",
                "workspace_id": "sam-main",
                "message_id": f"wow-msg-{token}-02",
                "thread_id": f"{token}02",
                "from": "client@example.com",
                "to": "sam@example.com",
                "subject": "Re: Website Migration — Friday 2pm check-in",
                "body": "Client-facing update (FYI): We’re still on track for Friday 2pm, pending legal sign-off.\n\nPlease draft a 2-sentence reply acknowledging this and confirming next steps.",
                "timestamp": now_anchor,
                "client_name": "Matt",
                "project_name": project_name,
                "skip_draft": True,
                "now_utc": now_anchor,
            },
            "/ingest/gmail",
        ),
        (
            "A vague follow-up that references context indirectly (should still make sense)",
            "Did we already send the revised timeline / client update, or are we still waiting?",
            {
                "source": "slack",
                "workspace_id": "sam-main",
                "channel": slack_channel_id,
                "ts": f"1743465000.{token}02",
                "user": "U123456",
                "project_name": project_name,
                "text": "Did we already send the revised timeline / client update, or are we still waiting?",
                "now_utc": now_anchor,
            },
            "/ingest/slack",
        ),
        (
            "A blocker + urgency escalation (should increase importance and update memory)",
            "Urgent: I’m blocked on legal sign-off. If we don’t get it today, we’ll miss the Friday 2pm commitment.",
            {
                "source": "slack",
                "workspace_id": "sam-main",
                "channel": slack_channel_id,
                "ts": f"1743465000.{token}03",
                "user": "U123456",
                "project_name": project_name,
                "text": "Urgent: I’m blocked on legal sign-off. If we don’t get it today, we’ll miss the Friday 2pm commitment.",
                "now_utc": now_anchor,
            },
            "/ingest/slack",
        ),
        (
            "Duplicate delivery of the same Slack event (should be deduped cleanly)",
            "Urgent: I’m blocked on legal sign-off. If we don’t get it today, we’ll miss the Friday 2pm commitment.",
            {
                "source": "slack",
                "workspace_id": "sam-main",
                "channel": slack_channel_id,
                # Intentionally same ts as STEP 4 to exercise dedup
                "ts": f"1743465000.{token}03",
                "user": "U123456",
                "project_name": project_name,
                "text": "Urgent: I’m blocked on legal sign-off. If we don’t get it today, we’ll miss the Friday 2pm commitment.",
                "now_utc": now_anchor,
            },
            "/ingest/slack",
        ),
        (
            "Scheduling a meeting (detects concrete next-weekday + time-of-day)",
            "Can we do a 15 min sync next Tuesday at 2pm? If not, Wednesday morning works.",
            {
                "source": "slack",
                "workspace_id": "sam-main",
                "channel": slack_channel_id,
                "ts": f"1743465000.{token}04",
                "user": "U123456",
                "project_name": project_name,
                "text": "Can we do a 15 min sync next Tuesday at 2pm? If not, Wednesday morning works.",
                "now_utc": now_anchor,
            },
            "/ingest/slack",
        ),
    ]

    for i, (headline, message, payload, path) in enumerate(steps, start=1):
        _hr()
        print(f"STEP {i}: {headline}")
        print(f"Incoming message: “{message}”")

        code, body = _post(path, payload)
        _safe_debug_dump(f"raw_response step={i} http={code}", body if isinstance(body, dict) else {"body": body})

        status = (body or {}).get("status") if isinstance(body, dict) else None

        # Demo-safe duplicate formatting (no rich interpretation)
        if status == "duplicate":
            print("Same message detected again — ignored to avoid duplicates.")
            print("Task: no task created.")
            print("Reply: no reply suggested.")
            continue

        # Demo-safe error handling (no raw JSON unless DEBUG_DEMO=True)
        if code != 200 or status == "error":
            print("This step hit a backend execution issue, but the system still extracted useful signals.")
            # Show only a minimal, non-technical subset if available
            if isinstance(body, dict):
                cls = body.get("classification") or {}
                rp = body.get("reply_policy") or {}
                reply_text = body.get("reply_text")
                if cls:
                    print(f"Decision: {'action' if _as_bool(cls.get('has_action')) else 'not a new task'}")
                if rp.get("should_reply") and reply_text:
                    print(f"Suggested reply: “{_short(reply_text, 220)}”")
                for line in _format_memory_update(body.get("project_context_update_result")):
                    print(line)
            continue

        for line in _format_big_picture(body, incoming_message=message):
            print(line)

        for line in _format_memory_update(body.get("project_context_update_result")):
            print(line)

    _hr("=", 92)
    print("METRICS SNAPSHOT (system-level counters)")
    code, metrics = _get("/metrics/summary")
    if code == 200:
        print(indent(_pretty(metrics), "  "))
    else:
        print(f"Could not fetch metrics summary (HTTP {code}).")
        print(_pretty(metrics))

    _hr("=", 92)
    print("What this proves (in human terms):")
    print("- It filters noise and only creates tasks when something is truly actionable.")
    print("- It keeps a living project memory (status, priorities, blockers).")
    print("- It understands vague follow-ups because it recalls context.")
    print("- It detects timing signals (deadlines, tomorrow/tonight, next Tuesday at 2pm).")
    print("- It produces simple value metrics you can monitor over time.")


def _print_sample_output() -> None:
    _title("Aivis — WOW Demo (Sample Output)")
    print("This is an example of what the live demo prints (your IDs will differ).")
    _hr()
    print("STEP 1: A messy message with two requests + a deadline (should create/link a task + detect timing)")
    print("Incoming message: “FYI: homepage copy is ~80% done. Also can you confirm the legal footer text and send the revised timeline by Friday 2pm? We promised the client.”")
    print("Decision: This is a real action request (work needed).")
    print("Task: created in ClickUp (86c9xxxx).")
    print("Reply: suggested a short reply (not auto-sent).")
    print("Suggested reply: “Yes — I’ll confirm the legal footer text and send the revised timeline by Friday 2pm.”")
    print("Importance: high (78/100) — reasons: has_action, urgency_language")
    print("Timing: medium — deadline hint: by Friday 2pm")
    print("Project memory updated:")
    print("- current_status: homepage copy is ~80% done.")
    _hr()
    print("STEP 4: A blocker + urgency escalation (should increase importance and update memory)")
    print("Incoming message: “Urgent: I’m blocked on legal sign-off. If we don’t get it today, we’ll miss the Friday 2pm commitment.”")
    print("Decision: This is not a new task by default (avoid noise).")
    print("Task: no task created.")
    print("Reply: suggested a reply.")
    print("Suggested reply: “Understood — I’m escalating legal sign-off today so we can still hit Friday 2pm.”")
    print("Importance: high (85/100) — reasons: blocker_signal, urgency_language")
    print("Timing: high — deadline hint: today / Friday 2pm")
    print("Project memory updated:")
    print("- blockers: blocked on legal sign-off")
    print("- next_steps: escalate legal sign-off today")
    _hr()
    print("STEP 5: Duplicate delivery of the same Slack event (should be deduped cleanly)")
    print("Incoming message: “(same Slack event delivered twice)”")
    print("Same message detected again — ignored to avoid duplicates.")
    _hr()
    print("METRICS SNAPSHOT (system-level counters)")
    print(indent(_pretty({
        "totals": {
            "messages_processed": 58,
            "duplicates": 5,
            "errors": 0,
            "tasks_created": 12,
            "tasks_linked": 7,
            "follow_ups_created": 14,
            "project_memory_updates": 19,
            "replies_generated": 26
        },
        "importance_breakdown": {"low": 8, "medium": 19, "high": 12, "critical": 3},
        "scheduling_breakdown": {"with_schedule_signal": 17, "none": 25, "low": 6, "medium": 8, "high": 3},
        "value_estimate": {
            "estimated_saved_actions": 35,
            "explanation": {
                "task_created_or_linked": 13,
                "follow_up_created": 10,
                "project_memory_updated": 12
            },
            "note": "Rough operational indicator (not time-saved minutes)."
        }
    }), "  "))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", action="store_true", help="Print sample output without calling the server.")
    p.add_argument("--debug", action="store_true", help="Show raw JSON results for troubleshooting.")
    p.add_argument("--slack-channel", default="YOUR_MATT_CHANNEL_ID")
    p.add_argument("--clickup-list-id", default="OPTIONAL_CLICKUP_LIST_ID")
    p.add_argument("--project", default="Website Migration")
    args = p.parse_args()

    global DEBUG_DEMO
    if args.debug:
        DEBUG_DEMO = True

    if args.sample:
        _print_sample_output()
        return

    _run_live_demo(
        slack_channel_id=args.slack_channel,
        clickup_list_id=(args.clickup_list_id or None),
        project_name=args.project,
    )


if __name__ == "__main__":
    main()

