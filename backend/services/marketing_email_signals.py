"""
Heuristics to avoid promoting bulk marketing / newsletters / notifications
into Grafik tasks.

Two complementary checks:

- ``is_likely_marketing_or_newsletter``: subject/body + header cues that
  indicate promo/CSAT/food-receipt mail.
- ``is_automated_or_bulk_sender``: sender/header cues that indicate the mail
  was sent by a machine/list (notifications, no-reply, ESP traffic).

``should_suppress_as_non_actionable`` combines both so callers can ask a single
"should this become a task?" question.

Uses RFC-style headers when present (Gmail Pub/Sub path) and conservative
body/subject cues when headers are missing (manual /ingest/gmail).
"""

from __future__ import annotations

import re
from typing import Any

_RE_SUBJECT_PROMO = re.compile(
    r"(?i)\b(newsletter|weekly digest|daily digest|flash sale|black friday|"
    r"cyber monday|limited time|\d+\s*%\s*off|exclusive offer|special offer|"
    r"promo(tion)? code|deal of the day|shop now|order today|"
    r"chance to win|\bwin\s+a\b|gift card|voucher|giveaway|lucky draw|"
    r"you'?re invited to win|prize draw|claim your (reward|prize))\b"
)

# Post-purchase CSAT / delivery surveys (not actionable work mail).
_RE_SUBJECT_SURVEY_OR_SATISFACTION = re.compile(
    r"(?i)(\bhappy delivery\b|"
    r"анкета\s+за\s+оценяване|"
    r"оценяване\s+на\s+доставката|"
    r"\bанкета\b.*\b(оценяване|delivery|order)\b|"
    r"\brate your (order|delivery|purchase)\b|"
    r"\bhow was your (order|delivery|purchase)\b|"
    r"\b(take|complete|fill out)\s+(our|this|the)\s+(\d+[-\s]?)?(second|minute|min)\s+survey\b|"
    r"\bshort survey\b|\bcustomer satisfaction survey\b|\bfeedback survey\b|"
    r"\bdelivery experience\b.*\b(survey|feedback)\b|"
    r"\btell us (what you think|about your (order|delivery))\b)"
)

# e.g. "U3M6FD | Chance to win a €100 Ryanair Gift Card"
_RE_SUBJECT_CAMPAIGN_ID_AND_PIPE_PROMO = re.compile(
    r"(?i)^\s*[A-Z0-9]{4,14}\s*\|\s*.+?\b("
    r"chance|gift\s*card|voucher|prize|giveaway|"
    r"€|\$\s*\d|eur\d|gbp\d|"
    r"ryanair|easyjet|wizz\s*air|"
    r"\bwin\b"
    r")\b"
)

# Fast-food / QSR menu drops (e.g. “Spicy McNuggets® are back”).
_RE_SUBJECT_QSR_MENU_PROMO = re.compile(
    r"(?i)(?:\b(?:spicy\s+)?mcnuggets\b|\bmcflurry\b|filet[\s-]?o[\s-]?fish\b|\bquarter\s*pounder\b|"
    r"\bchicken\s+mcnuggets\b)(?:\s*®)?\s*.*\b(?:are|is)\s+back\b|"
    r"\b(?:are|is)\s+back\b(?:\s*®)?\s*.*\b(?:spicy\s+)?mcnuggets\b|\b(?:are|is)\s+back\b.*\bmcflurry\b|"
    r"\bmcdonald'?s?\b.*\b(?:meal deal|menu|limited\s*time)\b.*\b(?:\$\s*\d|£\s*\d|\d+\s*for\s+\d+)\b"
)

# Food-delivery / takeaway receipts (not typical B2B “invoice for PO …”).
_RE_SUBJECT_FOOD_ORDER_RECEIPT = re.compile(
    r"(?i)(\bhere\s+is\s+the\s+invoice\s+of\s+your\s+order\b|"
    r"\binvoice\s+of\s+your\s+order\s+on\b|"
    r"\byour\s+order\s+on\s+(takeaway\.com|thuisbezorgd\.|just\s*eat|uber\s*eats?|"
    r"deliveroo|doordash|grubhub|foodpanda|wolt|bolt\s*food)\b|"
    r"\border\s+confirmation\b.*\b(takeaway|uber\s*eats?|deliveroo|doordash|just\s*eat)\b|"
    r"\breceipt\s+for\s+your\s+order\b.*\b(takeaway|uber|deliveroo|doordash)\b)"
)

_RE_BODY_VENDOR_FOOTER = re.compile(
    r"(?i)(mailchimp|constant\s+contact|sendinblue|brevo|campaign\s+monitor|"
    r"hubspot\s+email|sendgrid|customer\.io|klaviyo|beehiiv|substack)"
)

_RE_BODY_UNSUB_PAIR = re.compile(
    r"(?is)unsubscribe.{0,200}(view\s+in\s+your\s+browser|view\s+this\s+email\s+in\s+your\s+browser)|"
    r"(view\s+in\s+your\s+browser|view\s+this\s+email\s+in\s+your\s+browser).{0,200}unsubscribe"
)


def _header_map_from_payload(payload: dict[str, Any] | None) -> dict[str, str]:
    """
    Normalize headers to lower-cased keys for lookup.
    Supports:
      - payload['headers'] as dict name -> value
      - payload['headers'] as list of {name, value}
    """
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("headers")
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k is None:
                continue
            key = str(k).strip().lower()
            if key:
                out[key] = str(v or "").strip()
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("Name") or "").strip()
            if not name:
                continue
            out[name.lower()] = str(item.get("value") or item.get("Value") or "").strip()
        return out
    return out


def _get_header(headers: dict[str, str], name: str) -> str:
    return str(headers.get(name.lower()) or "").strip()


def is_likely_marketing_or_newsletter(
    *,
    payload: dict[str, Any] | None,
    subject: str,
    raw_text: str,
) -> bool:
    """
    Return True when the message is very likely bulk marketing / newsletter traffic.

    Intentionally conservative on single strong signals that also appear on legitimate
    transactional mail (e.g. List-Unsubscribe alone on GitHub notifications).
    """
    headers = _header_map_from_payload(payload)
    subj = (subject or "").strip()
    body = (raw_text or "").strip()
    combined = f"{subj}\n{body}"[:8000]

    precedence = _get_header(headers, "Precedence").lower()
    if precedence == "bulk":
        return True

    auto_sub = _get_header(headers, "Auto-Submitted").lower()
    if auto_sub.startswith("auto-generated"):
        return True

    list_unsub = _get_header(headers, "List-Unsubscribe")
    list_id = _get_header(headers, "List-Id")

    if list_unsub and _RE_SUBJECT_PROMO.search(subj):
        return True

    if list_unsub and list_id and _RE_BODY_UNSUB_PAIR.search(combined):
        return True

    if list_unsub and _RE_BODY_VENDOR_FOOTER.search(combined):
        return True

    if _RE_BODY_VENDOR_FOOTER.search(combined) and _RE_SUBJECT_PROMO.search(subj):
        return True

    if _RE_SUBJECT_SURVEY_OR_SATISFACTION.search(subj):
        return True

    if _RE_SUBJECT_CAMPAIGN_ID_AND_PIPE_PROMO.search(subj):
        return True

    if _RE_SUBJECT_QSR_MENU_PROMO.search(subj):
        return True

    if _RE_SUBJECT_FOOD_ORDER_RECEIPT.search(subj):
        return True

    if list_unsub and re.search(
        r"(?i)(chance to win|gift\s*card|win\s+a\s+€|win\s+a\s+\$|survey|rate your)",
        subj,
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Automated / bulk sender detection
# ---------------------------------------------------------------------------

_RE_EXTRACT_EMAIL = re.compile(r"<([^>]+)>")

# Sender local-parts that are almost always machine-sent.
_NOREPLY_LOCAL_PARTS = {
    "noreply",
    "no-reply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "do_not_reply",
    "notifications",
    "notification",
    "notify",
    "alerts",
    "alert",
    "mailer",
    "mailer-daemon",
    "mailerdaemon",
    "postmaster",
    "bounce",
    "bounces",
    "bounces+",
    "newsletter",
    "newsletters",
    "news",
    "digest",
    "updates",
    "offers",
    "promo",
    "promotions",
    "marketing",
    "reply+",
    "auto-confirm",
    "auto-reply",
    "autoreply",
    "system",
    "robot",
    "automated",
    "automation",
}

# Local-part substrings (e.g. "github-noreply", "notifications-bot", "reminders@…").
_NOREPLY_LOCAL_SUBSTRINGS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "notification",
    "notifications",
    "mailer-daemon",
    "mailerdaemon",
    "newsletter",
    "reminder",
    "reminders",
    "digest",
    "alerts",
    "campaign",
    "broadcast",
    "bounces",
    "bounce+",
    "receipts",
    "receipt",
    "statements",
    "statement",
    "transactions",
    "transactional",
)

# Known ESP / bulk-infra domains (bounce addresses, Return-Path, Sender, From).
_ESP_DOMAINS = (
    "sendgrid.net",
    "sendgrid.info",
    "mailgun.org",
    "mailgun.net",
    "mailgun.info",
    "amazonses.com",
    "sparkpostmail.com",
    "sparkpost.com",
    "postmarkapp.com",
    "pmta",
    "mailchimp.com",
    "mcsv.net",
    "mcdlv.net",
    "list-manage.com",
    "customeriomail.com",
    "customer.io",
    "klaviyomail.com",
    "hubspotemail.net",
    "hubspotlinks.com",
    "braze.com",
    "brazemail.com",
    "intercom-mail.com",
    "intercom-clicks.com",
    "constantcontact.com",
    "rsgsv.net",
    "substack.com",
    "substackcdn.com",
    "beehiiv.com",
    "convertkit-mail.com",
    "ck.page",
    "mailersend.net",
    "sendy.",
    "bnc3.mailjet.com",
    "mailjet.com",
)

# Generic bulk-sending domain substrings (covers long-tail newsletters /
# notification services that aren't in ``_ESP_DOMAINS``). Matched as a
# substring of the full domain, so ``tldrnewsletter.com`` is caught by
# ``newsletter`` and ``em.example.com`` by ``em.``.
_BULK_DOMAIN_SUBSTRINGS = (
    "newsletter",
    "newsletters",
    "marketing",
    "mailer.",
    "mailers.",
    "notification",
    "notifications",
    "notify.",
    "notifies.",
    "alerts.",
    "campaign",
    "campaigns",
    "bounces.",
    "bounce.",
    "bulkmail",
    "bulk.",
    "promo.",
    "promos.",
    "digest.",
    "digests.",
    "mkt.",
    "messaging.",
    "em.",       # common "em.brand.com" bulk subdomain convention
    "emarsys",
    "exacttarget",
    "salesforce-email",
    "pardot",
    "mktomail",
    "marketo",
    "sfmc-mail",
    "eloqua",
    "listrakbi",
)

# Body-text phrases that virtually only appear in list / bulk mail. Used as a
# last-resort fallback when headers are missing from older DB rows.
_RE_BODY_BULK_PHRASES = re.compile(
    r"(?i)("
    r"\bunsubscribe\s+(here|below|from|at|link|now)\b|"
    r"\bto\s+unsubscribe\b|"
    r"\bclick\s+here\s+to\s+unsubscribe\b|"
    r"\bmanage\s+(your\s+)?(email\s+)?preferences\b|"
    r"\bupdate\s+(your\s+)?(email\s+)?preferences\b|"
    r"\bemail\s+preferences\b|"
    r"\bview\s+(this\s+email\s+)?in\s+your\s+browser\b|"
    r"\byou(?:'re|\s+are)\s+receiving\s+this\s+(email|message|newsletter)\b|"
    r"\byou\s+signed\s+up\s+(for|to)\b|"
    r"\bthis\s+email\s+was\s+sent\s+to\b|"
    r"\badd\s+us\s+to\s+your\s+address\s+book\b|"
    r"\bpowered\s+by\s+(mailchimp|substack|beehiiv|sendgrid|klaviyo|brevo|customer\.io|hubspot)\b"
    r")"
)

_RE_BULK_X_MAILER = re.compile(
    r"(?i)(mailchimp|sendgrid|mailgun|amazon\s*ses|sparkpost|postmark|"
    r"klaviyo|braze|hubspot|customer\.io|intercom|constant\s*contact|"
    r"substack|beehiiv|campaign\s*monitor|mailjet|brevo|sendinblue)"
)


def _extract_email(header_value: str) -> str:
    s = str(header_value or "").strip().lower()
    if not s:
        return ""
    m = _RE_EXTRACT_EMAIL.search(s)
    if m:
        return (m.group(1) or "").strip().lower()
    if "@" in s and " " not in s:
        return s
    for tok in re.split(r"\s+", s):
        if "@" in tok:
            return tok.strip("<>,;").lower()
    return ""


def _domain_of(email_addr: str) -> str:
    s = (email_addr or "").strip().lower()
    if "@" not in s:
        return ""
    return s.rsplit("@", 1)[1].strip("<> \t")


def _local_of(email_addr: str) -> str:
    s = (email_addr or "").strip().lower()
    if "@" not in s:
        return s
    return s.split("@", 1)[0]


def _is_noreply_local(local: str) -> bool:
    l = (local or "").strip().lower()
    if not l:
        return False
    # Strip common separators/plus-addressing for matching.
    base = re.split(r"[+]", l, 1)[0]
    if base in _NOREPLY_LOCAL_PARTS:
        return True
    for needle in _NOREPLY_LOCAL_SUBSTRINGS:
        if needle in base:
            return True
    return False


def _is_esp_domain(domain: str) -> bool:
    d = (domain or "").strip().lower()
    if not d:
        return False
    for esp in _ESP_DOMAINS:
        if d == esp or d.endswith("." + esp) or esp in d:
            return True
    return False


def _is_bulk_domain(domain: str) -> bool:
    """
    Looser than ``_is_esp_domain``: matches generic bulk-sending domain
    conventions (e.g. ``tldrnewsletter.com``, ``em.brand.com``,
    ``notifications.stripe.com``).
    """
    d = (domain or "").strip().lower()
    if not d:
        return False
    for needle in _BULK_DOMAIN_SUBSTRINGS:
        if needle in d:
            return True
    return False


def is_automated_or_bulk_sender(
    *,
    payload: dict[str, Any] | None,
    sender: str,
    raw_text: str | None = None,
) -> bool:
    """
    True when the message was sent by a list/notification system / no-reply
    address / ESP pipeline — i.e., not a human writing to you directly.

    Precision-first: every signal listed here is essentially never present on
    a real 1:1 human email from Gmail/Outlook/company domains.

    ``raw_text`` is optional. When provided and headers are missing (common for
    older DB rows ingested without full header capture), we fall back to
    body-level phrases like "unsubscribe" / "view in browser" that virtually
    only appear in list/bulk mail.
    """
    headers = _header_map_from_payload(payload)

    # --- Strong header signals ---------------------------------------------
    if _get_header(headers, "List-Unsubscribe"):
        return True
    if _get_header(headers, "List-Unsubscribe-Post"):
        return True
    if _get_header(headers, "List-Id"):
        return True

    precedence = _get_header(headers, "Precedence").lower()
    if precedence in {"bulk", "list", "junk", "auto_reply"}:
        return True

    auto_sub = _get_header(headers, "Auto-Submitted").lower()
    if auto_sub and auto_sub != "no":
        return True

    if _get_header(headers, "Feedback-ID"):
        return True

    # Vendor-specific headers: existence alone is a very strong signal.
    for h_name in (
        "X-Campaign",
        "X-Campaign-Id",
        "X-Mailchimp-Campaign-Id",
        "X-Mc-User",
        "X-SG-EID",
        "X-SG-ID",
        "X-Ses-Outgoing",
        "X-Klaviyo-Message-Id",
        "X-HS-Email-Campaign-Id",
        "X-Mj-Mid",
    ):
        if _get_header(headers, h_name):
            return True

    x_mailer = _get_header(headers, "X-Mailer")
    if x_mailer and _RE_BULK_X_MAILER.search(x_mailer):
        return True

    # --- Envelope / sender domain signals ---------------------------------
    return_path = _extract_email(_get_header(headers, "Return-Path"))
    envelope_sender = _extract_email(_get_header(headers, "Sender"))
    reply_to = _extract_email(_get_header(headers, "Reply-To"))

    for addr in (return_path, envelope_sender, reply_to):
        if not addr:
            continue
        d = _domain_of(addr)
        if _is_esp_domain(d) or _is_bulk_domain(d):
            return True
        if _is_noreply_local(_local_of(addr)):
            return True

    # --- From header / provided sender string -----------------------------
    from_header = _get_header(headers, "From") or (sender or "")
    from_addr = _extract_email(from_header)
    if from_addr:
        d = _domain_of(from_addr)
        if _is_esp_domain(d) or _is_bulk_domain(d):
            return True
        if _is_noreply_local(_local_of(from_addr)):
            return True

    # Fallback: the caller's ``sender`` string contains a no-reply hint even if
    # it's not a well-formed email (rare, but cheap to catch).
    if re.search(
        r"(?i)\b(no[-_]?reply|do[-_\s]?not[-_\s]?reply|notifications?|mailer-daemon|"
        r"postmaster|newsletter|digest|reminders?|alerts?|campaigns?)\b",
        str(sender or ""),
    ):
        return True

    # --- Body-level fallback (for older rows without headers captured) ----
    if raw_text and _RE_BODY_BULK_PHRASES.search(str(raw_text)[:8000]):
        return True

    return False


def should_suppress_as_non_actionable(
    *,
    payload: dict[str, Any] | None,
    subject: str,
    raw_text: str,
    sender: str,
) -> tuple[bool, str | None]:
    """
    Single entry point used by callers that want to decide whether a Gmail
    message should stay out of tasks/action lists.

    Returns (suppress, reason).
    """
    if is_automated_or_bulk_sender(payload=payload, sender=sender, raw_text=raw_text):
        return True, "automated_or_bulk_sender"
    if is_likely_marketing_or_newsletter(
        payload=payload, subject=subject, raw_text=raw_text
    ):
        return True, "likely_marketing_newsletter"
    return False, None
