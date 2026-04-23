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
    r"you'?re invited to win|prize draw|claim your (reward|prize)|"
    # EU localizations — real mailboxes mix languages freely.
    r"last\s+chance|laatste\s+kans|ultima\s+chance|derni[eè]re\s+chance|"
    r"последен\s+шанс|[uú]ltima\s+oportunidad|"
    r"gratis\s+mee\s+te\s+spelen|mee\s+te\s+spelen|"
    r"free\s+spins|gratis\s+bonus|"
    r"kortingscode|korting\s+van|"
    # Loterij / lotteria / lottery promo hooks
    r"miljoenenjacht|jackpot|lotteri[ija]|tombola"
    r")\b"
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

    # Calendar invites / cancellations / updates — these are automated
    # meeting notifications, not human tasks. (We treat them as non-actionable
    # even when the underlying calendar system routes them via a human
    # forwarder, because their content is system-generated.)
    if _looks_like_calendar_notification(subj):
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
    "mailing.",         # e.g. mailing.italotreno.it
    "mailings.",
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
    "em.",              # common "em.brand.com" bulk subdomain convention
    "email.",           # e.g. email.ns.nl, email.domain.com
    "emails.",
    "email-",           # e.g. email-marketing.com
    "emailmarket",      # e.g. emailmarket.shein.com
    "news.",            # e.g. news.market.shein.com
    "news-",            # e.g. news-hb.hugoboss.com
    "market.",          # e.g. news.market.shein.com (also covers .market.)
    "markets.",
    "comms.",           # e.g. comms.vueling.com
    "communications.",
    "broadcast.",
    "broadcasts.",
    # Gambling / lottery / casino promo domains (always bulk).
    "loterij",          # e.g. postcodeloterij.nl
    "lotteri",          # Italian / Spanish "lotteria" / "loteria"
    "lottery",
    "casino",
    "gokken",
    "sportsbook",
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

# Numbered bulk subdomains like ``email2.microsoft.com`` / ``mail3.brand.com``.
# Matched with a regex because the digit varies.
_RE_BULK_NUMBERED_SUBDOMAIN = re.compile(
    r"(?i)(^|\.)(email|mail|mailer|mailing|news|notify|alerts|comms|mkt|"
    r"marketing|campaign|promo|digest)\d+\."
)

# Body-text phrases that virtually only appear in list / bulk mail. Used as a
# last-resort fallback when headers are missing from older DB rows.
#
# NOTE: the word "unsubscribe" alone is matched on purpose — legitimate 1:1
# email traffic effectively never contains that word, whereas every bulk
# sender (ESP-driven or hand-rolled) includes at least one "Unsubscribe" link.
_RE_BODY_BULK_PHRASES = re.compile(
    r"(?i)("
    r"\bunsubscribe\b|"
    r"\bto\s+unsubscribe\b|"
    r"\bclick\s+here\s+to\s+unsubscribe\b|"
    r"\bmanage\s+(your\s+)?(email\s+)?preferences\b|"
    r"\bupdate\s+(your\s+)?(email\s+)?preferences\b|"
    r"\bemail\s+preferences\b|"
    r"\bview\s+(this\s+email\s+)?(in\s+your\s+browser|online)\b|"
    r"\byou(?:'re|\s+are)\s+receiving\s+this\s+(email|message|newsletter)\b|"
    r"\byou\s+signed\s+up\s+(for|to)\b|"
    r"\bthis\s+email\s+was\s+sent\s+to\b|"
    r"\badd\s+us\s+to\s+your\s+address\s+book\b|"
    r"\bpowered\s+by\s+(mailchimp|substack|beehiiv|sendgrid|klaviyo|brevo|customer\.io|hubspot)\b|"
    # Multilingual equivalents common in EU/BG/NL/DE/IT/ES mailboxes.
    r"\bafmelden\b|"                   # Dutch "unsubscribe"
    r"\babmelden\b|"                   # German "unsubscribe"
    r"\bsi\s+desinscrire\b|"           # French
    r"\bd[ée]sinscrire\b|"             # French
    r"\bannulla\s+(l'?iscrizione|la\s+sottoscrizione)\b|"  # Italian
    r"\bcancelar\s+la\s+suscripci[oó]n\b|"                  # Spanish
    r"\bотпиши|отписване|прекратете\s+абонамента\b"         # Bulgarian
    r")"
)

# HTML-heavy bulk mail signature. A real 1:1 email is usually plain text or
# simple HTML with no DOCTYPE / table layout; bulk mail almost always ships
# a full ``<!DOCTYPE html>`` wrapper with ``cellpadding`` table layouts or
# inline style blocks.
_RE_BODY_HTML_BULK = re.compile(
    r"(?is)(<!doctype\s+html|cellpadding\s*=|cellspacing\s*=|"
    r"<table[^>]+bgcolor|<style[^>]*>.*?mso-|view\s+email\s+online)"
)

# Google/Outlook calendar notifications are very distinctive: the subject
# ends with ``@ <something> <YYYY.MM.DD> HH:MM`` (or similar date patterns).
# That tail virtually never appears in a human-written subject.
_RE_SUBJECT_CAL_TAIL = re.compile(
    r"@\s*\S+\s+\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}(\s+\d{1,2}:\d{2})?"
)

# Strict "verb-prefix + colon" headings used by Google Calendar across
# localizations: "Cancelled event:", "Accepted:", "Обновено събитие:" etc.
# Matching only the leading word is too broad, so we also require the
# subject to contain a date-like pattern (``_RE_SUBJECT_CAL_TAIL`` above or a
# simple ``YYYY-MM-DD``/``DD.MM.YYYY`` elsewhere in the subject).
_RE_SUBJECT_CAL_VERB = re.compile(
    r"(?i)^\s*("
    r"invitation|updated\s+invitation|cancell?ed(\s+event)?|declined|accepted|"
    r"tentatively\s+accepted|tentative|new\s+event|updated\s+event|"
    r"new\s+meeting|meeting\s+cancelled|meeting\s+canceled"
    # Localized prefixes seen in real mailboxes:
    r"|анулирано\s+събитие|отменено\s+събитие|прието\s+събитие|"
    r"отказано\s+събитие|обновено\s+събитие|нова\s+покана|покана"
    r"|evento\s+(cancellato|accettato|rifiutato|aggiornato)|invito"
    r"|invitaci[oó]n\s+(actualizada|cancelada|aceptada|rechazada)"
    r"|uitnodiging|afgewezen|geaccepteerd|bijgewerkt"
    r")\b\s*[:\-]"
)

_RE_SUBJECT_GENERIC_DATE = re.compile(
    r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)


def _looks_like_calendar_notification(subject: str) -> bool:
    s = (subject or "").strip()
    if not s:
        return False
    if _RE_SUBJECT_CAL_TAIL.search(s):
        return True
    if _RE_SUBJECT_CAL_VERB.search(s) and _RE_SUBJECT_GENERIC_DATE.search(s):
        return True
    return False

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
    ``notifications.stripe.com``, ``email2.microsoft.com``).
    """
    d = (domain or "").strip().lower()
    if not d:
        return False
    for needle in _BULK_DOMAIN_SUBSTRINGS:
        if needle in d:
            return True
    if _RE_BULK_NUMBERED_SUBDOMAIN.search(d):
        return True
    return False


# Role-account local-parts that are *usually* bulk but occasionally belong to
# a real person/team. We flag them as bulk only when a secondary signal
# (HTML body, unsubscribe word, long marketing body, bulk display name,
# promo subject) is also present.
_ROLE_LOCAL_PARTS = {
    "info",
    "sales",
    "team",
    "hello",
    "hi",
    "contact",
    "support",
    "help",
    "welcome",
    "invitations",
    "invitation",
    "invite",
    "challenges",
    "offers",
    "deals",
    "discover",
    "brand",
    "store",
    "shop",
    "news",
    "community",
    "builders",
    "editor",
    "editors",
}

# Brand/marketing cues inside the sender *display name* (the part before the
# ``<addr>``). Real human From headers rarely contain "Shop", "Deals",
# "Fashion News" etc.
_RE_DISPLAY_NAME_BULK = re.compile(
    r"(?i)\b("
    r"newsletter|news\s+(digest|update)|digest|weekly\s+update|monthly\s+update|"
    r"team|shop|store|deals|offers|rewards|marketing|promotions?|"
    r"fashion\s+news|beauty\s+news|travel\s+deals|"
    r"updates?|alerts?|notifications?"
    r")\b"
)


def _is_role_local(local: str) -> bool:
    l = (local or "").strip().lower()
    if not l:
        return False
    base = re.split(r"[+]", l, 1)[0]
    return base in _ROLE_LOCAL_PARTS


def _body_has_html_bulk_markup(raw_text: str) -> bool:
    if not raw_text:
        return False
    return bool(_RE_BODY_HTML_BULK.search(str(raw_text)[:12000]))


def _display_name_is_bulk(sender: str) -> bool:
    s = str(sender or "").strip()
    if not s:
        return False
    # Take the portion before "<addr>" when present.
    head = s.split("<", 1)[0].strip().strip('"').strip("'")
    if not head:
        return False
    return bool(_RE_DISPLAY_NAME_BULK.search(head))


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
    from_local = _local_of(from_addr) if from_addr else ""
    from_domain = _domain_of(from_addr) if from_addr else ""

    if from_addr:
        if _is_esp_domain(from_domain) or _is_bulk_domain(from_domain):
            return True
        if _is_noreply_local(from_local):
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
    body_head = str(raw_text or "")[:12000]
    body_phrase_hit = bool(raw_text) and bool(_RE_BODY_BULK_PHRASES.search(body_head))
    if body_phrase_hit:
        return True

    # Heavy HTML marketing body (``<!DOCTYPE html>`` / ``cellpadding=`` /
    # Outlook ``mso-`` styles) combined with any reasonable length is
    # essentially always a mass mailing, even without a role-local sender.
    # Threshold picked so that short transactional confirmations ("Payment
    # received") that some companies still format as HTML do NOT trip it.
    body_html_hit = _body_has_html_bulk_markup(body_head)
    if body_html_hit and len(body_head) >= 4000:
        return True

    display_bulk_hit = _display_name_is_bulk(from_header or sender)

    # --- Role-local corroboration -----------------------------------------
    # ``info@`` / ``sales@`` / ``team@`` etc. are usually bulk, but can be a
    # real small-team reply. Flag them as bulk only with a second signal.
    if from_local and _is_role_local(from_local):
        long_body_hit = len(body_head) > 1500  # role-local + any mid-size body
        if body_html_hit or display_bulk_hit or long_body_hit or body_phrase_hit:
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
