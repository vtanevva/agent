import hashlib
import hmac
import json
import os
import threading
import time
import uuid

import requests
from flask import Blueprint, request, jsonify

from utils.logger import get_logger
from services.reply_writer import generate_reply
from services.slack_text import clean_text, prepare_text_for_classification
from storage.sqlite_db import insert_message_if_new, get_message_payload


log = get_logger("slack_interactive")
slack_interactive_bp = Blueprint("slack_interactive", __name__)


def _slack_signing_secret() -> str | None:
    secret = os.getenv("SLACK_SIGNING_SECRET")
    return secret.strip() if secret else None


def _verify_slack_signature() -> bool:
    """
    Verify Slack requests per https://api.slack.com/authentication/verifying-requests-from-slack

    If SLACK_SIGNING_SECRET is not set, verification is skipped (dev-friendly).
    """
    secret = _slack_signing_secret()
    if not secret:
        log.info("[SLACK_INTERACTIVE] SLACK_SIGNING_SECRET missing -> signature verification skipped")
        return True

    ts = request.headers.get("X-Slack-Request-Timestamp")
    sig = request.headers.get("X-Slack-Signature")
    if not ts or not sig:
        return False

    try:
        ts_int = int(ts)
    except Exception:
        return False

    # Prevent replay attacks
    if abs(int(time.time()) - ts_int) > 60 * 5:
        return False

    raw_body = request.get_data(cache=True)  # bytes, original body
    base = b"v0:" + ts.encode("utf-8") + b":" + raw_body
    my_sig = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(my_sig, sig)


def _slack_bot_token() -> str | None:
    tok = os.getenv("SLACK_BOT_TOKEN")
    return tok.strip() if tok else None


def _slack_api(method: str, payload: dict) -> dict:
    token = _slack_bot_token()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is missing")

    response = requests.post(
        f"https://slack.com/api/{method}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        data=json.dumps(payload),
        timeout=20,
    )
    try:
        response_json = response.json()
    except Exception:
        raise RuntimeError(f"Slack API error ({method}): non-JSON response status={response.status_code}")
    if not response_json.get("ok"):
        raise RuntimeError(f"Slack API error ({method}): {response_json}")
    return response_json


def _blocks_for_suggestion(*, suggested_reply: str, suggestion_id: str) -> list[dict]:
    preview = (suggested_reply or "").strip()
    if not preview:
        preview = "(No suggestion generated.)"

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Suggested reply:*\n```" + preview[:2900] + "```",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Copy"},
                    "action_id": "aivis_reply_copy",
                    "value": suggestion_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit"},
                    "action_id": "aivis_reply_edit",
                    "value": suggestion_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Send"},
                    "style": "primary",
                    "action_id": "aivis_reply_send",
                    "value": suggestion_id,
                },
            ],
        },
    ]


def _open_copy_modal(*, trigger_id: str, suggested_reply: str) -> None:
    text = (suggested_reply or "").strip() or "(No suggestion generated.)"

    _slack_api(
        "views.open",
        {
            "trigger_id": trigger_id,
            "view": {
                "type": "modal",
                "callback_id": "aivis_reply_copy_modal",
                "title": {"type": "plain_text", "text": "Suggested reply"},
                "close": {"type": "plain_text", "text": "Close"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Copy the text below.",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "```" + text[:2900] + "```",
                        },
                    },
                ],
            },
        },
    )


def _open_edit_modal(*, trigger_id: str, suggestion_id: str, suggested_reply: str) -> None:
    initial = (suggested_reply or "").strip()

    _slack_api(
        "views.open",
        {
            "trigger_id": trigger_id,
            "view": {
                "type": "modal",
                "callback_id": "aivis_reply_edit_modal",
                "private_metadata": json.dumps({"suggestion_id": suggestion_id}),
                "title": {"type": "plain_text", "text": "Edit reply"},
                "submit": {"type": "plain_text", "text": "Send"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "reply_block",
                        "label": {"type": "plain_text", "text": "Reply"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reply_text",
                            "multiline": True,
                            "initial_value": initial[:3000],
                        },
                    }
                ],
            },
        },
    )


def _post_ephemeral_suggestion(
    *,
    channel: str,
    user: str,
    thread_ts: str | None,
    suggestion_id: str,
    suggested_reply: str,
) -> None:
    payload: dict = {
        "channel": channel,
        "user": user,
        "text": "Suggested reply",
        "blocks": _blocks_for_suggestion(suggested_reply=suggested_reply, suggestion_id=suggestion_id),
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    _slack_api("chat.postEphemeral", payload)


def _post_thread_reply(*, channel: str, thread_ts: str | None, text: str) -> None:
    payload: dict = {"channel": channel, "text": (text or "").strip()}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    _slack_api("chat.postMessage", payload)


def _infer_reply_type(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return "short"

    if any(k in t for k in ["asap", "urgent", "today", "tomorrow", "deadline", "by eod", "by end of day"]):
        return "time_relevant"

    if any(k in t for k in ["thanks", "thank you", "thx", "got it", "ok", "okay", "noted"]):
        return "short"

    if any(k in t for k in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
        return "short"

    if "?" in t:
        return "context_relevant"

    return "context_relevant"


def _generate_and_post_suggestion_async(
    *,
    source_id: str,
    channel: str,
    user_id: str,
    thread_ts: str | None,
    original_text: str,
) -> None:
    def worker():
        try:
            log.info(
                "[SLACK_INTERACTIVE] worker start channel=%s thread_ts=%s user_id=%s",
                channel,
                thread_ts,
                user_id,
            )
            clean = clean_text(original_text or "")
            text_for_cls = prepare_text_for_classification(clean)

            reply_type = _infer_reply_type(text_for_cls)
            log.info("[SLACK_INTERACTIVE] generating via reply_writer reply_type=%s", reply_type)
            suggested = (generate_reply(clean, reply_type, summary=None) or "").strip()

            if not suggested:
                suggested = "Got it — what would you like me to say back?"

            suggestion_id = str(uuid.uuid4())
            log.info("[SLACK_INTERACTIVE] storing suggestion_id=%s", suggestion_id)
            insert_message_if_new(
                source="slack_reply_suggestion",
                source_id=suggestion_id,
                channel=channel,
                ts=str(thread_ts or ""),
                user=user_id,
                text=suggested[:500],
                payload={
                    "source_id": source_id,
                    "channel": channel,
                    "thread_ts": thread_ts,
                    "user_id": user_id,
                    "original_text": original_text,
                    "classification": {"reply_type": reply_type},
                    "suggested_reply": suggested,
                },
            )

            log.info("[SLACK_INTERACTIVE] posting ephemeral suggestion_id=%s", suggestion_id)
            _post_ephemeral_suggestion(
                channel=channel,
                user=user_id,
                thread_ts=thread_ts,
                suggestion_id=suggestion_id,
                suggested_reply=suggested,
            )
            log.info("[SLACK_INTERACTIVE] posted ephemeral suggestion_id=%s", suggestion_id)

        except Exception as err:
            log.exception(f"[SLACK_INTERACTIVE] failed to generate/post suggestion: {err}")
            try:
                _slack_api(
                    "chat.postEphemeral",
                    {
                        "channel": channel,
                        "user": user_id,
                        "text": "Sorry — I couldn’t generate a reply suggestion.",
                        **({"thread_ts": thread_ts} if thread_ts else {}),
                    },
                )
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()


@slack_interactive_bp.post("/slack/interactive")
def slack_interactive():
    if not _verify_slack_signature():
        return jsonify({"error": "invalid signature"}), 401

    payload_raw = request.form.get("payload")
    if not payload_raw:
        payload = request.get_json(silent=True) or {}
    else:
        try:
            payload = json.loads(payload_raw)
        except Exception:
            return jsonify({"error": "invalid payload"}), 400

    p_type = payload.get("type")
    log.info(
        "[SLACK_INTERACTIVE] inbound type=%s callback_id=%s",
        p_type,
        payload.get("callback_id"),
    )

    # 1) Message shortcut (message action)
    if p_type == "message_action":
        callback_id = (payload.get("callback_id") or "").strip()
        expected = (os.getenv("SLACK_REPLY_SHORTCUT_CALLBACK_ID") or "aivis_suggest_reply").strip()

        if callback_id != expected:
            log.info(
                "[SLACK_INTERACTIVE] skip message_action: callback_id mismatch (got=%s expected=%s)",
                callback_id,
                expected,
            )
            return "", 200

        log.info("[SLACK_INTERACTIVE] message_action matched callback_id=%s", callback_id)

        user_id = (payload.get("user") or {}).get("id") or ""
        channel_id = (payload.get("channel") or {}).get("id") or ""
        message = payload.get("message") or {}
        message_ts = message.get("ts") or payload.get("message_ts") or ""
        thread_ts = message.get("thread_ts") or message_ts or None
        original_text = message.get("text") or ""
        action_ts = payload.get("action_ts") or ""
        team_id = (payload.get("team") or {}).get("id") or ""

        source_id = f"shortcut:{team_id}:{callback_id}:{user_id}:{channel_id}:{message_ts}:{action_ts}"
        is_new, _ = insert_message_if_new(
            source="slack_shortcut",
            source_id=source_id,
            channel=channel_id,
            ts=str(message_ts),
            user=user_id,
            text=callback_id,
            payload=payload,
        )
        if not is_new:
            log.info("[SLACK_INTERACTIVE] dedup shortcut source_id=%s", source_id)
            return "", 200

        log.info(
            "[SLACK_INTERACTIVE] generating suggestion channel=%s thread_ts=%s user_id=%s msg_ts=%s",
            channel_id,
            thread_ts,
            user_id,
            message_ts,
        )
        _generate_and_post_suggestion_async(
            source_id=source_id,
            channel=channel_id,
            user_id=user_id,
            thread_ts=thread_ts,
            original_text=original_text,
        )
        return "", 200

    # 2) Button clicks (Copy/Edit/Send)
    if p_type == "block_actions":
        actions = payload.get("actions") or []
        if not actions:
            log.info("[SLACK_INTERACTIVE] block_actions with no actions[]")
            return "", 200

        action = actions[0] or {}
        action_id = action.get("action_id")
        suggestion_id = action.get("value") or ""
        trigger_id = payload.get("trigger_id") or ""

        log.info(
            "[SLACK_INTERACTIVE] block_actions action_id=%s suggestion_id=%s has_trigger=%s",
            action_id,
            suggestion_id,
            bool(trigger_id),
        )
        stored = get_message_payload(source="slack_reply_suggestion", source_id=suggestion_id) or {}
        suggested_reply = (stored.get("suggested_reply") or "").strip()
        channel = (stored.get("channel") or (payload.get("channel") or {}).get("id") or "").strip()
        thread_ts = stored.get("thread_ts") or None
        user_id = (stored.get("user_id") or (payload.get("user") or {}).get("id") or "").strip()

        if action_id == "aivis_reply_copy" and trigger_id:
            _open_copy_modal(trigger_id=trigger_id, suggested_reply=suggested_reply)
            return "", 200

        if action_id == "aivis_reply_edit" and trigger_id:
            _open_edit_modal(
                trigger_id=trigger_id,
                suggestion_id=suggestion_id,
                suggested_reply=suggested_reply,
            )
            return "", 200

        if action_id == "aivis_reply_send":
            def send_worker():
                try:
                    _post_thread_reply(channel=channel, thread_ts=thread_ts, text=suggested_reply)
                    _slack_api(
                        "chat.postEphemeral",
                        {
                            "channel": channel,
                            "user": user_id,
                            "text": "Sent.",
                            **({"thread_ts": thread_ts} if thread_ts else {}),
                        },
                    )
                except Exception as err:
                    log.exception(f"[SLACK_INTERACTIVE] send failed: {err}")

            threading.Thread(target=send_worker, daemon=True).start()
            return "", 200

        return "", 200

    # 3) Modal submit (Edit -> Send)
    if p_type == "view_submission":
        view = payload.get("view") or {}
        callback_id = view.get("callback_id")
        if callback_id != "aivis_reply_edit_modal":
            return "", 200

        meta_raw = view.get("private_metadata") or "{}"
        try:
            meta = json.loads(meta_raw)
        except Exception:
            meta = {}

        suggestion_id = meta.get("suggestion_id") or ""
        stored = get_message_payload(source="slack_reply_suggestion", source_id=suggestion_id) or {}
        channel = (stored.get("channel") or "").strip()
        thread_ts = stored.get("thread_ts") or None
        user_id = (stored.get("user_id") or "").strip()

        state = (view.get("state") or {}).get("values") or {}
        reply_text = ""
        try:
            reply_text = state["reply_block"]["reply_text"]["value"]  # type: ignore[index]
        except Exception:
            reply_text = ""

        def modal_send_worker():
            try:
                _post_thread_reply(channel=channel, thread_ts=thread_ts, text=reply_text)
                _slack_api(
                    "chat.postEphemeral",
                    {
                        "channel": channel,
                        "user": user_id,
                        "text": "Sent.",
                        **({"thread_ts": thread_ts} if thread_ts else {}),
                    },
                )
            except Exception as err:
                log.exception(f"[SLACK_INTERACTIVE] modal send failed: {err}")

        threading.Thread(target=modal_send_worker, daemon=True).start()
        return "", 200

    return "", 200

