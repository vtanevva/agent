from flask import Blueprint, request, jsonify

from services.classifier_ai import classify as classify_ai
from services.classifier_stub import classify as classify_stub
from services.classification_context import build_classification_input
from services.gmail_text import prepare_email_for_classification
from services.slack_text import prepare_text_for_classification

classify_bp = Blueprint("classify", __name__)

@classify_bp.post("/debug/classify")
def debug_classify():
    payload = request.get_json(force=True)
    text = payload.get("text", "")
    return jsonify({"classification": classify_stub(text)}), 200


@classify_bp.post("/debug/classify_ai")
def debug_classify_ai():
    """
    Debug endpoint for the real classifier (LLM + heuristics), without side effects.

    Payload supports:
      - channel: "slack" | "gmail" | "plain" (default "plain")
      - text (plain/slack)
      - subject/body (gmail)
      - context: { client_name, project_name, project_context }
    """
    payload = request.get_json(force=True) or {}
    channel = (payload.get("channel") or "plain").strip().lower()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    if channel == "gmail":
        subject = str(payload.get("subject") or "")
        body = str(payload.get("body") or "")
        clean = prepare_email_for_classification(subject, body)
    else:
        text = str(payload.get("text") or "")
        clean = prepare_text_for_classification(text) if channel == "slack" else text.strip()

    enriched = build_classification_input(
        raw_message_text=clean,
        client_name=context.get("client_name"),
        project_name=context.get("project_name"),
        project_context=context.get("project_context"),
    )

    classification = classify_ai(enriched, raw_text=clean) or {}

    return (
        jsonify(
            {
                "channel": channel,
                "input_clean": clean,
                "input_context": enriched,
                "classification": classification,
            }
        ),
        200,
    )