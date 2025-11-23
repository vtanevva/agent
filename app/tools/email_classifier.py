"""Email classification system for Smart Inbox Triage"""

import re
import openai
from typing import Dict, List, Optional, Tuple

# Classification version - increment this when classification rules change
# This allows re-classification of existing emails when rules are updated
CLASSIFICATION_VERSION = "2.0"  # Updated for LinkedIn/social filtering and improved thresholds


def compute_rules_score(email: Dict) -> Dict[str, int]:
    """
    Compute rule-based scores for different categories.
    Returns a dict with scores for each category.
    """
    subject = (email.get("subject") or "").lower()
    body = (email.get("body") or "").lower()
    snippet = (email.get("snippet") or "").lower()
    
    text = f"{subject} {body} {snippet}"
    
    scores = {
        "urgent": 0,
        "waiting_for_reply": 0,
        "action_items": 0,
        "newsletters": 0,
        "invoices": 0,
        "clients": 0,
    }
    
    # Urgent keywords
    urgent_keywords = ["urgent", "asap", "immediately", "important", "critical", "emergency"]
    urgent_phrases = ["by end of day", "within 24 hours", "action required", "as soon as possible"]
    if any(kw in text for kw in urgent_keywords):
        scores["urgent"] += 30
    if any(phrase in text for phrase in urgent_phrases):
        scores["urgent"] += 20
    if "!!!" in subject or subject.count("!") >= 3:
        scores["urgent"] += 15
    
    # Waiting for reply
    waiting_phrases = [
        "waiting for your response", "waiting for your reply", "following up",
        "please respond", "awaiting your response", "when can you", "did you see",
        "just checking in", "ping"
    ]
    if any(phrase in text for phrase in waiting_phrases):
        scores["waiting_for_reply"] += 25
    
    # Reminders are urgent, especially meeting/appointment reminders
    if "reminder" in text:
        if "meeting" in text or "appointment" in text:
            scores["urgent"] += 40  # Meeting/appointment reminders are urgent
        else:
            scores["urgent"] += 25  # Other reminders are also time-sensitive
        scores["action_items"] += 15  # Reminders also indicate action needed
    
    # Action items
    action_phrases = [
        "can you do", "please fix", "next steps", "action item", "todo",
        "task", "deadline", "need to", "should we", "let's", "please review",
        "meeting", "meetings", "appointment", "schedule", "calendar"
    ]
    if any(phrase in text for phrase in action_phrases):
        scores["action_items"] += 20
    
    # Reminders are urgent (especially meeting reminders)
    if "reminder" in text:
        if "meeting" in text or "appointment" in text:
            scores["urgent"] += 40  # Meeting/appointment reminders are urgent
        else:
            scores["urgent"] += 25  # Other reminders are also time-sensitive
        scores["action_items"] += 15  # Reminders also indicate action needed
    
    # Invoices
    invoice_keywords = ["invoice", "receipt", "payment", "billing", "statement", "due", "pay"]
    if any(kw in text for kw in invoice_keywords):
        scores["invoices"] += 30
    
    # Newsletters and social connection requests
    newsletter_keywords = ["unsubscribe", "newsletter", "promotion", "special offer", "sale"]
    social_keywords = ["want to connect", "connection request", "linkedin", "connect with you", 
                       "follow you", "viewed your profile", "endorsed you"]
    if any(kw in text for kw in newsletter_keywords):
        scores["newsletters"] += 25
    if any(kw in text for kw in social_keywords):
        scores["newsletters"] += 30  # Social connection requests go to newsletters/normal
    if "unsubscribe" in text.lower():
        scores["newsletters"] += 15
    
    return scores


def compute_sender_score(email: Dict, user_id: str) -> Dict[str, int]:
    """
    Compute sender-based scores.
    Checks sender email against known contacts, domains, etc.
    """
    from_email = (email.get("from") or "").lower()
    if not from_email:
        return {k: 0 for k in ["urgent", "waiting_for_reply", "action_items", "newsletters", "invoices", "clients"]}
    
    # Extract email address from "Name <email@domain.com>" format
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', from_email)
    if not email_match:
        return {k: 0 for k in ["urgent", "waiting_for_reply", "action_items", "newsletters", "invoices", "clients"]}
    
    sender_email = email_match.group(0).lower()
    sender_domain = sender_email.split("@")[1] if "@" in sender_email else ""
    
    scores = {
        "urgent": 0,
        "waiting_for_reply": 0,
        "action_items": 0,
        "newsletters": 0,
        "invoices": 0,
        "clients": 0,
    }
    
    # Check if sender is a known client (from contacts)
    # Cache contacts lookup to avoid repeated DB queries
    if not hasattr(compute_sender_score, '_contacts_cache'):
        compute_sender_score._contacts_cache = {}
    
    cache_key = f"{user_id}_contacts"
    if cache_key not in compute_sender_score._contacts_cache:
        try:
            from app.utils.db_utils import get_contacts_collection
            contacts_col = get_contacts_collection()
            if contacts_col:
                # Load all contacts for this user once and cache
                all_contacts = list(contacts_col.find(
                    {"user_id": user_id},
                    {"email": 1, "groups": 1}
                ))
                compute_sender_score._contacts_cache[cache_key] = {
                    c.get("email", "").lower(): c for c in all_contacts
                }
            else:
                compute_sender_score._contacts_cache[cache_key] = {}
        except Exception:
            compute_sender_score._contacts_cache[cache_key] = {}
    
    contacts_map = compute_sender_score._contacts_cache.get(cache_key, {})
    contact = contacts_map.get(sender_email)
    if contact:
        # Known contact - likely client communication
        scores["clients"] += 30
        # Check if they're in a client group
        groups = contact.get("groups", [])
        if any("client" in str(g).lower() for g in groups):
            scores["clients"] += 20
    
    # Critical domains (AWS, Stripe, etc.)
    critical_domains = ["aws.amazon.com", "stripe.com", "github.com", "slack.com", "atlassian.com"]
    if any(domain in sender_domain for domain in critical_domains):
        scores["urgent"] += 15
        scores["action_items"] += 10
    
    # Invoice/payment domains
    invoice_domains = ["paypal.com", "stripe.com", "square.com", "quickbooks.com", "xero.com", "freshbooks.com"]
    if any(domain in sender_domain for domain in invoice_domains):
        scores["invoices"] += 35
    
    # Newsletter/social domains (LinkedIn, social networks, promotional)
    newsletter_domains = ["substack.com", "mailchimp.com", "constantcontact.com", "sendgrid.com", 
                          "campaignmonitor.com", "mailerlite.com", "convertkit.com"]
    social_domains = ["linkedin.com", "linkedinmail.com", "facebook.com", "twitter.com", 
                      "instagram.com", "tiktok.com", "pinterest.com"]
    if any(domain in sender_domain for domain in newsletter_domains):
        scores["newsletters"] += 30
    if any(domain in sender_domain for domain in social_domains):
        scores["newsletters"] += 35  # Social connection requests are like newsletters
    
    # Internal team (same domain or common internal domains)
    # This would need to be configured per user, but for now we'll skip
    
    return scores


def compute_llm_score(email: Dict) -> Dict[str, int]:
    """
    Use LLM to classify email and return scores.
    """
    subject = email.get("subject", "")
    snippet = email.get("snippet", "")
    body_preview = (email.get("body") or "")[:500]  # Limit body for prompt
    
    prompt = f"""Classify this email into one of: URGENT, IMPORTANT, ACTION, CLIENT, INVOICE, NEWSLETTER, WAITING, NORMAL.

Urgent = time-sensitive, blocking, requires reply within 24h.
Important = business-related but not urgent.
Action = contains tasks, next steps, meetings, appointments, reminders, calendar events, deadlines, or requires action. Most business emails that need attention should be ACTION, not NORMAL.
Client = business client communication.
Invoice = billing, receipts, payments.
Newsletter = promotional, informational, social connection requests (LinkedIn, Facebook), marketing emails, or automated notifications.
Waiting = sender is waiting for a reply.
Normal = only truly unimportant emails like spam, automated system messages, or completely irrelevant content. If an email seems important or requires any action, classify as ACTION instead.

Subject: {subject}
Snippet: {snippet}
Body preview: {body_preview}

Return only ONE label from: URGENT, IMPORTANT, ACTION, CLIENT, INVOICE, NEWSLETTER, WAITING, NORMAL"""

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an email classification assistant. Return only the label."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=10,
            temperature=0.1,
        )
        
        label = response.choices[0].message.content.strip().upper()
        
        # Map LLM labels to scores
        scores = {
            "urgent": 0,
            "waiting_for_reply": 0,
            "action_items": 0,
            "newsletters": 0,
            "invoices": 0,
            "clients": 0,
        }
        
        label_mapping = {
            "URGENT": {"urgent": 60},
            "IMPORTANT": {"urgent": 20, "action_items": 15},
            "ACTION": {"action_items": 50},
            "CLIENT": {"clients": 50},
            "INVOICE": {"invoices": 60},
            "NEWSLETTER": {"newsletters": 50},
            "WAITING": {"waiting_for_reply": 50},
            "NORMAL": {},
        }
        
        if label in label_mapping:
            scores.update(label_mapping[label])
        
        return scores
    except Exception as e:
        print(f"[ERROR] LLM classification failed: {e}", flush=True)
        return {k: 0 for k in ["urgent", "waiting_for_reply", "action_items", "newsletters", "invoices", "clients"]}


def compute_priority_category(total_scores: Dict[str, int]) -> str:
    """
    Determine final category based on total scores and thresholds.
    """
    # Thresholds (lowered urgent threshold to catch meeting reminders)
    # Prioritize filtering out newsletters/social first, then categorize important emails
    if total_scores.get("newsletters", 0) >= 30:
        return "newsletters"
    elif total_scores.get("urgent", 0) >= 50:  # Lowered from 80 to catch reminders
        return "urgent"
    elif total_scores.get("invoices", 0) >= 60:
        return "invoices"
    elif total_scores.get("clients", 0) >= 50:
        return "clients"
    elif total_scores.get("action_items", 0) >= 35:  # Lowered from 45 to catch more action items
        return "action_items"
    elif total_scores.get("waiting_for_reply", 0) >= 40:
        return "waiting_for_reply"
    else:
        # Default to action_items for emails that aren't clearly newsletters
        # Most emails that reach here are probably action items, not truly "normal"
        if total_scores.get("action_items", 0) > 0 or total_scores.get("urgent", 0) > 0:
            return "action_items"
        return "normal"


def classify_email(email: Dict, user_id: str) -> Dict:
    """
    Classify an email using all scoring methods.
    Returns classification result with category and scores.
    """
    # Get email body if not provided
    if "body" not in email or not email.get("body"):
        # Try to extract from snippet or fetch if needed
        email["body"] = email.get("snippet", "")[:500]
    
    # Compute all scores
    rules_scores = compute_rules_score(email)
    sender_scores = compute_sender_score(email, user_id)
    llm_scores = compute_llm_score(email)
    
    # Combine scores
    total_scores = {}
    for category in ["urgent", "waiting_for_reply", "action_items", "newsletters", "invoices", "clients"]:
        total_scores[category] = (
            rules_scores.get(category, 0) +
            sender_scores.get(category, 0) +
            llm_scores.get(category, 0)
        )
    
    # Determine final category
    category = compute_priority_category(total_scores)
    
    return {
        "category": category,
        "scores": {
            "total": total_scores,
            "rules": rules_scores,
            "sender": sender_scores,
            "llm": llm_scores,
        },
    }

