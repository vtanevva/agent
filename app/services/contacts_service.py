from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from email.utils import getaddresses
from googleapiclient.discovery import build

from app.db.collections import get_contacts_collection, get_conversations_collection
from app.utils.oauth_utils import load_google_credentials


# ──────────────────────────────────────────────────────────────────────
# Internal helpers (name / company / grouping heuristics)
# ──────────────────────────────────────────────────────────────────────


def _company_from_email(email: str) -> str:
    """Extract a plausible company name from email domain; ignore public providers."""
    try:
        domain = (email or "").split("@", 1)[1].lower()
    except Exception:
        return ""
    public = {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "protonmail.com",
        "zoho.com",
        "gmx.com",
        "aol.com",
        "pm.me",
    }
    if domain in public:
        return ""
    parts = domain.split(".")
    core = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
    if not core:
        return ""
    # avoid technical subdomains if accidentally chosen
    if core in {"mail", "mx", "smtp", "pop", "imap", "cpanel", "webmail", "ns"} and len(parts) >= 3:
        core = parts[-3]
    if not core:
        return ""
    return core[:1].upper() + core[1:].lower()


def _name_from_email(email: str) -> str:
    """Guess a human name from an email local-part."""
    try:
        local = (email or "").split("@", 1)[0]
        # strip +tag
        local = local.split("+", 1)[0]
        import re

        parts = re.split(r"[._\-]+", local)
        parts = [p for p in parts if p and p.isalpha()]
        if not parts:
            return ""
        # common no-name words to skip
        blacklist = {"info", "contact", "sales", "support", "hello", "mail", "team", "admin"}
        parts = [p for p in parts if p.lower() not in blacklist] or parts
        # Title Case
        return " ".join(w[:1].upper() + w[1:].lower() for w in parts[:3])
    except Exception:
        return ""


def _canonical_person_name(current_name: str, email: str) -> str:
    """
    Compute a canonical person name (no company suffix, not a role mailbox).
    Used for grouping same-person contacts across multiple emails.
    """
    base = (current_name or "").strip()
    if not base or base.lower() == "(no name)":
        base = _name_from_email(email) or ""
    # If base appears with a suffix ' - Company', strip it
    if " - " in base:
        base = base.split(" - ", 1)[0].strip()
    # Drop if role mailbox
    role_set = {
        "info",
        "hr",
        "support",
        "sales",
        "contact",
        "admin",
        "hello",
        "mail",
        "team",
        "office",
        "careers",
        "jobs",
        "billing",
        "help",
        "service",
        "services",
        "enquiries",
        "inquiries",
        "noreply",
        "no reply",
        "no-reply",
    }
    if base.lower() in role_set:
        return ""
    # Normalize spacing/case
    parts = [p for p in base.replace("_", " ").replace(".", " ").split() if p]
    if not parts:
        return ""
    return " ".join(w[:1].upper() + w[1:].lower() for w in parts[:4])


def _looks_like_email(text: str) -> bool:
    """Heuristic to detect if a given name string is actually an email."""
    if not text or "@" not in text:
        return False
    # very loose check: has one '@' and at least one dot after
    try:
        local, domain = text.split("@", 1)
        return bool(local) and "." in domain
    except Exception:
        return False


def _normalized_display_name(current_name: str, email: str) -> str:
    """
    Build display name using rules:
    - If current_name is missing/empty/'(No name)', derive from local-part.
    - If the base name is a generic role (info/hr/support/...), append company: 'Company - role'.
    - If the base name itself looks like an email, derive Name from email and use 'Name - Company' when company exists.
    - Otherwise keep the base name as-is (do NOT append company).
    """
    base = (current_name or "").strip()
    if not base or base.lower() == "(no name)":
        base = _name_from_email(email) or ""
    company = _company_from_email(email)
    if not base:
        # If we cannot derive a base, fall back to company alone
        return company or ""
    # If the provided name is actually an email string, promote to 'Name - Company'
    if _looks_like_email(base):
        derived = _name_from_email(email)
        if company and derived:
            return f"{derived} - {company}"
        return derived or base
    # Decide if base is a generic role mailbox
    role_set = {
        "info",
        "hr",
        "support",
        "sales",
        "contact",
        "admin",
        "hello",
        "mail",
        "team",
        "office",
        "careers",
        "jobs",
        "billing",
        "help",
        "service",
        "services",
        "enquiries",
        "inquiries",
        "noreply",
        "no reply",
        "no-reply",
    }
    base_l = base.lower()
    if base_l in role_set:
        # Format role nicely: HR uppercased; others lower-case
        display_role = "HR" if base_l == "hr" else base_l.replace("no reply", "no-reply")
        return f"{company} - {display_role}" if company else display_role
    # Non-generic personal-looking name: keep as-is, no company suffix
    return base


def _category_groups_for_email(email: str) -> List[str]:
    """
    Heuristic category groups based on email domain.
    Returns a list of lower-case category names like ['travel','food','events','housing'].
    """
    try:
        domain = (email or "").split("@", 1)[1].lower()
    except Exception:
        return []
    cats = set()
    travel_keys = {
        "airbnb",
        "booking",
        "expedia",
        "kayak",
        "skyscanner",
        "tripadvisor",
        "trivago",
        "agoda",
        "hostelworld",
        "uber",
        "lyft",
        "bolt",
        "blablacar",
        "ryanair",
        "easyjet",
        "delta",
        "united",
        "american",
        "lufthansa",
        "wizzair",
        "aircanada",
        "britishairways",
        "emirates",
        "qatarairways",
        "airasia",
        "sbb",
        "bahn",
        "amtrak",
    }
    food_keys = {
        "ubereats",
        "doordash",
        "deliveroo",
        "justeat",
        "grubhub",
        "postmates",
        "wolt",
        "glovo",
        "foodpanda",
        "deliveryhero",
        "dominos",
        "pizzahut",
        "mcdonalds",
        "burgerking",
        "kfc",
        "chipotle",
        "boltfood",
    }
    event_keys = {
        "eventbrite",
        "ticketmaster",
        "tickets",
        "eventim",
        "meetup",
        "dice",
        "ticketek",
        "universe",
        "skiddle",
        "festicket",
        "axs",
        "billetto",
        "eventzilla",
        "splashthat",
        "bizzabo",
    }
    housing_keys = {
        "zillow",
        "realtor",
        "trulia",
        "redfin",
        "apartments",
        "apartmentlist",
        "rent",
        "rentals",
        "rightmove",
        "zoopla",
        "spareroom",
        "roomster",
        "nestoria",
        "idealista",
        "fotocasa",
        "immobilienscout",
        "immowelt",
        "immobiliare",
        "leboncoin",
        "seloger",
        "funda",
        "bolig",
        "booking",
        "airbnb",
        "vrbo",
        "homeaway",
        "bookingcom",
        "hostelworld",
        "hostelbookers",
    }
    toks = [t for t in domain.replace(".", " ").replace("-", " ").split() if t]
    lower_join = " ".join(toks)
    if any(k in domain for k in travel_keys) or any(
        k in lower_join for k in {"travel", "flight", "hotel", "hostel", "train", "bus", "ferry"}
    ):
        cats.add("travel")
    if any(k in domain for k in food_keys) or any(
        k in lower_join
        for k in {"eat", "food", "pizza", "burger", "kebab", "sushi", "delivery", "cafe", "restaurant"}
    ):
        cats.add("food")
    if any(k in domain for k in event_keys) or any(
        k in lower_join for k in {"event", "ticket", "festival", "conference", "meetup"}
    ):
        cats.add("events")
    if any(k in domain for k in housing_keys) or any(
        k in lower_join
        for k in {
            "housing",
            "rent",
            "rental",
            "apartment",
            "flat",
            "house",
            "property",
            "realestate",
            "real estate",
            "accommodation",
            "room",
            "rooms",
            "landlord",
            "tenant",
        }
    ):
        cats.add("housing")
    return list(cats)


def _generate_nickname(name: str, email: Optional[str] = None) -> str:
    """Generate a nickname from a full name. 'First - Company' if company exists, else just first name."""
    if not name or name.lower() == "(no name)":
        return ""

    name = name.strip()
    parts = name.split()

    if len(parts) == 0:
        return ""

    # Extract first name
    first_name = parts[0]

    # Check if name already contains company (format: "Name - Company")
    if " - " in name:
        # Already has company format, use as is
        return name

    # Try to extract company from email domain
    company = _company_from_email(email) if email else None

    # Build nickname: "First Name - Company" or just "First Name"
    if company:
        nickname = f"{first_name} - {company}"
        return nickname[:50]  # Cap at 50 chars
    else:
        return first_name


# ──────────────────────────────────────────────────────────────────────
# Public service functions
# ──────────────────────────────────────────────────────────────────────


def sync_contacts(user_id: str, max_sent: int = 1000, force: bool = False) -> Dict[str, Any]:
    """
    Initialize or refresh user's contacts from recent Sent messages.

    Mirrors the original /api/contacts/sync logic, but returns plain dicts.
    """
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    # If already initialized and not forced, return existing after normalization/grouping
    if not force:
        existing_count = contacts_col.count_documents({"user_id": user_id})
        if existing_count > 0:
            existing_docs = list(
                contacts_col.find(
                    {"user_id": user_id},
                    {"_id": 0, "email": 1, "name": 1, "archived": 1},
                )
            )
            role_set = {
                "info",
                "hr",
                "support",
                "sales",
                "contact",
                "admin",
                "hello",
                "mail",
                "team",
                "office",
                "careers",
                "jobs",
                "billing",
                "help",
                "service",
                "services",
                "enquiries",
                "inquiries",
                "noreply",
                "no reply",
                "no-reply",
            }
            for d in existing_docs:
                em = (d.get("email") or "").lower()
                nm = (d.get("name") or "").strip()
                needs_norm = (not nm) or (nm.lower() == "(no name)") or (nm.lower() in role_set)
                if not needs_norm and nm:
                    # also normalize if name is actually an email string
                    try:
                        if "@" in nm and "." in nm.split("@", 1)[1]:
                            needs_norm = True
                        else:
                            needs_norm = False
                    except Exception:
                        pass
                if needs_norm:
                    new_name = _normalized_display_name(nm, em)
                    if new_name and new_name != nm:
                        contacts_col.update_one(
                            {"user_id": user_id, "email": em},
                            {"$set": {"name": new_name}},
                        )

            # Generate nicknames for all contacts that don't have one
            no_nickname = list(
                contacts_col.find(
                    {
                        "user_id": user_id,
                        "$or": [
                            {"nickname": {"$exists": False}},
                            {"nickname": ""},
                        ],
                        "name": {"$exists": True, "$ne": "", "$ne": "(No name)"},
                    },
                    {"_id": 0, "email": 1, "name": 1},
                )
            )
            for d in no_nickname:
                em = d.get("email", "")
                nm = d.get("name", "")
                if nm:
                    auto_nickname = _generate_nickname(nm, em)
                    if auto_nickname:
                        contacts_col.update_one(
                            {"user_id": user_id, "email": em},
                            {"$set": {"nickname": auto_nickname}},
                        )

            # Add category-based groups for all existing contacts FIRST
            all_existing = list(contacts_col.find({"user_id": user_id}, {"_id": 0, "email": 1}))
            for ed in all_existing:
                em = (ed.get("email") or "").lower()
                cats = _category_groups_for_email(em)
                if cats:
                    contacts_col.update_one(
                        {"user_id": user_id, "email": em},
                        {"$addToSet": {"groups": {"$each": cats}}},
                    )

            # Rebuild groups based on person/company for existing (non-archived) contacts
            from collections import defaultdict

            docs = list(
                contacts_col.find(
                    {"user_id": user_id, "archived": {"$ne": True}},
                    {"_id": 0, "email": 1, "name": 1},
                )
            )
            by_person = defaultdict(list)
            by_company = defaultdict(list)
            for d in docs:
                em = d.get("email", "")
                nm = d.get("name", "")
                person = _canonical_person_name(nm, em)
                if person:
                    by_person[person].append(em)
                comp = _company_from_email(em)
                if comp:
                    by_company[comp].append(em)
            for person, emails in by_person.items():
                if len(emails) >= 2:
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}, "groups": {"$exists": False}},
                        {"$set": {"groups": []}},
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}, "groups": {"$type": "object"}},
                        {"$set": {"groups": []}},
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}},
                        {"$addToSet": {"groups": person}},
                    )
            for comp, emails in by_company.items():
                if len(emails) >= 2:
                    category_groups = {"travel", "food", "events", "housing"}
                    emails_without_cats: List[str] = []
                    for em in emails:
                        doc = contacts_col.find_one({"user_id": user_id, "email": em}, {"groups": 1})
                        if doc:
                            existing_groups = [
                                g.lower() if isinstance(g, str) else "" for g in (doc.get("groups") or [])
                            ]
                            if not any(cat in existing_groups for cat in category_groups):
                                emails_without_cats.append(em)
                    if emails_without_cats:
                        contacts_col.update_many(
                            {"user_id": user_id, "email": {"$in": emails_without_cats}, "groups": {"$exists": False}},
                            {"$set": {"groups": []}},
                        )
                        contacts_col.update_many(
                            {"user_id": user_id, "email": {"$in": emails_without_cats}, "groups": {"$type": "object"}},
                            {"$set": {"groups": []}},
                        )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails_without_cats}},
                        {"$addToSet": {"groups": comp}},
                    )

            # Cleanup: Remove company groups from contacts that have category groups
            category_groups2 = {"travel", "food", "events", "housing"}
            all_contacts = list(contacts_col.find({"user_id": user_id}, {"_id": 0, "email": 1, "groups": 1}))
            for contact in all_contacts:
                em = contact.get("email", "")
                original_groups = [
                    g if isinstance(g, str) else "" for g in (contact.get("groups") or [])
                ]
                existing_groups_lower = [g.lower() for g in original_groups if g]
                has_category = any(cat in existing_groups_lower for cat in category_groups2)
                if has_category:
                    comp = _company_from_email(em)
                    if comp:
                        comp_lower = comp.lower()
                        groups_to_remove: List[str] = [
                            g for g in original_groups if g and g.lower() == comp_lower
                        ]
                        for gtr in groups_to_remove:
                            contacts_col.update_one(
                                {"user_id": user_id, "email": em},
                                {"$pull": {"groups": gtr}},
                            )

            items = list(contacts_col.find({"user_id": user_id}, {"_id": 0}).limit(500))
            return {"success": True, "initialized": True, "contacts": items}

    # Otherwise, fetch from Gmail Sent and build contacts
    try:
        creds = load_google_credentials(user_id)
        svc = build("gmail", "v1", credentials=creds)

        # Fetch up to max_sent messages from Sent via pagination
        msgs: List[Dict[str, Any]] = []
        next_token = None
        remaining = max(0, max_sent)
        while remaining > 0:
            page_size = min(500, remaining)
            req = svc.users().messages().list(
                userId="me",
                q="in:sent -from:mailer-daemon@googlemail.com",
                maxResults=page_size,
                pageToken=next_token,
            )
            resp = req.execute()
            batch = resp.get("messages", []) or []
            msgs.extend(batch)
            remaining -= len(batch)
            next_token = resp.get("nextPageToken")
            if not next_token or not batch:
                break

        seen: Dict[str, Dict[str, Any]] = {}
        for m in msgs:
            meta = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["To", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
            tos = headers.get("To", "")
            dt = headers.get("Date", "")
            try:
                last_seen = datetime.utcnow().isoformat()
            except Exception:
                last_seen = datetime.utcnow().isoformat()
            for name, email in getaddresses([tos]):
                email_norm = (email or "").strip().lower()
                if not email_norm:
                    continue
                if email_norm not in seen:
                    seen[email_norm] = {
                        "user_id": user_id,
                        "email": email_norm,
                        "name": (name or ""),
                        "count": 1,
                        "first_seen": last_seen,
                        "last_seen": last_seen,
                    }
                else:
                    seen[email_norm]["count"] += 1
                    seen[email_norm]["last_seen"] = last_seen

        # Upsert into DB
        for email_norm, doc in seen.items():
            normalized_name = _normalized_display_name(doc.get("name") or "", email_norm)
            auto_nickname = _generate_nickname(normalized_name, email_norm) if normalized_name else ""

            contacts_col.update_one(
                {"user_id": user_id, "email": email_norm},
                {
                    "$setOnInsert": {
                        "user_id": user_id,
                        "email": email_norm,
                        "first_seen": doc["first_seen"],
                        "name": normalized_name,
                        "nickname": auto_nickname,
                    },
                    "$set": {
                        "last_seen": doc["last_seen"],
                    },
                    "$inc": {"count": doc["count"]},
                    "$addToSet": {"groups": {"$each": _category_groups_for_email(email_norm)}},
                },
                upsert=True,
            )

            # Also update nickname for existing contacts if they don't have one
            if auto_nickname:
                contacts_col.update_one(
                    {"user_id": user_id, "email": email_norm, "nickname": {"$exists": False}},
                    {"$set": {"nickname": auto_nickname}},
                )

        # Normalize names for any existing contacts with placeholder or missing names
        needs = list(
            contacts_col.find(
                {
                    "user_id": user_id,
                    "$or": [
                        {"name": {"$exists": False}},
                        {"name": ""},
                        {"name": "(No name)"},
                        {"name": {"$regex": r"^info$", "$options": "i"}},
                    ],
                },
                {"_id": 0, "email": 1, "name": 1},
            )
        )
        for d in needs:
            em = d.get("email", "")
            new_name = _normalized_display_name(d.get("name", ""), em)
            if new_name:
                contacts_col.update_one(
                    {"user_id": user_id, "email": em},
                    {"$set": {"name": new_name}},
                )

        # Generate nicknames for all contacts that don't have one
        no_nickname2 = list(
            contacts_col.find(
                {
                    "user_id": user_id,
                    "$or": [
                        {"nickname": {"$exists": False}},
                        {"nickname": ""},
                    ],
                    "name": {"$exists": True, "$ne": "", "$ne": "(No name)"},
                },
                {"_id": 0, "email": 1, "name": 1},
            )
        )
        for d in no_nickname2:
            em = d.get("email", "")
            nm = d.get("name", "")
            if nm:
                auto_nickname = _generate_nickname(nm, em)
                if auto_nickname:
                    contacts_col.update_one(
                        {"user_id": user_id, "email": em},
                        {"$set": {"nickname": auto_nickname}},
                    )

        # Add category-based groups for all existing contacts FIRST
        all_existing2 = list(contacts_col.find({"user_id": user_id}, {"_id": 0, "email": 1}))
        for ed in all_existing2:
            em = (ed.get("email") or "").lower()
            cats = _category_groups_for_email(em)
            if cats:
                contacts_col.update_one(
                    {"user_id": user_id, "email": em},
                    {"$addToSet": {"groups": {"$each": cats}}},
                )

        # Auto-group by canonical person name and company (clusters with size >= 2)
        from collections import defaultdict

        docs2 = list(
            contacts_col.find(
                {"user_id": user_id, "archived": {"$ne": True}},
                {"_id": 0, "email": 1, "name": 1},
            )
        )
        by_person2 = defaultdict(list)
        by_company2 = defaultdict(list)
        for d in docs2:
            em = d.get("email", "")
            nm = d.get("name", "")
            person = _canonical_person_name(nm, em)
            if person:
                by_person2[person].append(em)
            comp = _company_from_email(em)
            if comp:
                by_company2[comp].append(em)
        for person, emails in by_person2.items():
            if len(emails) >= 2:
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}, "groups": {"$exists": False}},
                    {"$set": {"groups": []}},
                )
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}, "groups": {"$type": "object"}},
                    {"$set": {"groups": []}},
                )
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}},
                    {"$addToSet": {"groups": person}},
                )
        for comp, emails in by_company2.items():
            if len(emails) >= 2:
                category_groups = {"travel", "food", "events", "housing"}
                emails_without_cats2: List[str] = []
                for em in emails:
                    doc = contacts_col.find_one({"user_id": user_id, "email": em}, {"groups": 1})
                    if doc:
                        existing_groups = [
                            g.lower() if isinstance(g, str) else "" for g in (doc.get("groups") or [])
                        ]
                        if not any(cat in existing_groups for cat in category_groups):
                            emails_without_cats2.append(em)
                if emails_without_cats2:
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails_without_cats2}, "groups": {"$exists": False}},
                        {"$set": {"groups": []}},
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails_without_cats2}, "groups": {"$type": "object"}},
                        {"$set": {"groups": []}},
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails_without_cats2}},
                        {"$addToSet": {"groups": comp}},
                    )

        # Cleanup: Remove company groups from contacts that have category groups
        category_groups3 = {"travel", "food", "events", "housing"}
        all_contacts2 = list(contacts_col.find({"user_id": user_id}, {"_id": 0, "email": 1, "groups": 1}))
        for contact in all_contacts2:
            em = contact.get("email", "")
            existing_groups = [g if isinstance(g, str) else "" for g in (contact.get("groups") or [])]
            existing_groups_lower = [g.lower() for g in existing_groups if g]
            has_category = any(cat in existing_groups_lower for cat in category_groups3)
            if has_category:
                comp = _company_from_email(em)
                if comp:
                    comp_lower = comp.lower()
                    groups_to_remove2: List[str] = [g for g in existing_groups if g and g.lower() == comp_lower]
                    for gtr in groups_to_remove2:
                        contacts_col.update_one(
                            {"user_id": user_id, "email": em},
                            {"$pull": {"groups": gtr}},
                        )

        items = list(contacts_col.find({"user_id": user_id}, {"_id": 0}).limit(500))
        return {"success": True, "initialized": True, "contacts": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_contacts(user_id: str, include_archived: bool = False) -> Dict[str, Any]:
    """List stored contacts for a user, merging duplicates by email."""
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    query: Dict[str, Any] = {"user_id": user_id}
    if not include_archived:
        query["archived"] = {"$ne": True}
    docs = list(
        contacts_col.find(query, {"_id": 0})
        .sort([("last_seen", -1), ("count", -1)])
        .limit(2000)
    )
    merged: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        email = (d.get("email") or "").lower()
        if not email:
            continue
        # normalize groups to lower-case unique list of strings
        grps: List[str] = []
        for g in d.get("groups", []) or []:
            if isinstance(g, str):
                key = g.strip().lower()
                if key and key not in grps:
                    grps.append(key)
        name = d.get("name")
        entry = merged.get(email)
        if not entry:
            nd = dict(d)
            nd["email"] = email
            nd["groups"] = grps
            nd["name"] = name or ""
            merged[email] = nd
        else:
            # merge counts and timestamps
            try:
                entry["count"] = entry.get("count", 0) + int(d.get("count", 0))
            except Exception:
                pass
            ls = d.get("last_seen")
            if ls and (not entry.get("last_seen") or str(ls) > str(entry.get("last_seen"))):
                entry["last_seen"] = ls
            fs = d.get("first_seen")
            if fs and (not entry.get("first_seen") or str(fs) < str(entry.get("first_seen"))):
                entry["first_seen"] = fs
            # prefer longer non-empty name
            if name and (not entry.get("name") or len(name) > len(entry.get("name"))):
                entry["name"] = name
            # union groups (already normalized)
            for g in grps:
                if g not in entry["groups"]:
                    entry["groups"].append(g)
    return {"success": True, "contacts": list(merged.values())}


def resolve_contact_email(user_id: str, name_or_email: str) -> Dict[str, Any]:
    """
    Resolve a human-friendly name or nickname to an email address.

    Nicknames are taken directly from the contact details stored in the
    `contacts` collection (the same nickname you see/edit in the Contacts UI).

    This is used for commands like "send an email to Marin - Fontys" where
    "Marin - Fontys" is a contact nickname. If the input is already an email
    address, it is returned unchanged.

    Returns
    -------
    dict
        {
          "success": True/False,
          "input": original_string,
          "resolved_email": email_or_original,
          "matched": bool  # True if we found a contact match
        }
    """
    original = (name_or_email or "").strip()
    if not original:
        return {
            "success": False,
            "input": original,
            "resolved_email": "",
            "matched": False,
            "error": "Empty name_or_email",
        }

    # If it's already an email, just return it
    if "@" in original:
        return {
            "success": True,
            "input": original,
            "resolved_email": original,
            "matched": False,
        }

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {
            "success": False,
            "input": original,
            "resolved_email": original,
            "matched": False,
            "error": "Database not connected",
        }

    name_lower = original.strip().lower()

    # Try exact match on name or nickname
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"^{name_lower}$", "$options": "i"}},
                {"nickname": {"$regex": f"^{name_lower}$", "$options": "i"}},
            ],
        },
        {"email": 1},
    )
    if contact and contact.get("email"):
        email_val = contact.get("email")
        return {
            "success": True,
            "input": original,
            "resolved_email": email_val,
            "matched": True,
        }

    # Try word-boundary match (partial name or nickname)
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"\\b{name_lower}\\b", "$options": "i"}},
                {"nickname": {"$regex": f"\\b{name_lower}\\b", "$options": "i"}},
            ],
        },
        {"email": 1},
    )
    if contact and contact.get("email"):
        email_val = contact.get("email")
        return {
            "success": True,
            "input": original,
            "resolved_email": email_val,
            "matched": True,
        }

    # No match found - return original
    return {
        "success": True,
        "input": original,
        "resolved_email": original,
        "matched": False,
    }


def normalize_contact_names(user_id: str) -> Dict[str, Any]:
    """Fill missing names from email local-part for a user's contacts."""
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    docs = list(
        contacts_col.find(
            {
                "user_id": user_id,
                "$or": [
                    {"name": {"$exists": False}},
                    {"name": ""},
                    {"name": "(No name)"},
                    {"name": {"$regex": r"^info$", "$options": "i"}},
                ],
            },
            {"_id": 0, "email": 1, "name": 1},
        )
    )
    updated = 0
    for d in docs:
        email = d.get("email", "")
        new_name = _normalized_display_name(d.get("name", ""), email)
        if new_name:
            contacts_col.update_one(
                {"user_id": user_id, "email": email},
                {"$set": {"name": new_name}},
            )
            updated += 1
    return {"success": True, "updated": updated}


def archive_contact(user_id: str, email: str, archived: bool = True) -> Dict[str, Any]:
    """Archive or unarchive a contact."""
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    contacts_col.update_one(
        {"user_id": user_id, "email": email},
        {
            "$set": {
                "archived": archived,
                "archived_at": datetime.utcnow().isoformat() if archived else None,
            }
        },
        upsert=False,
    )
    return {"success": True, "email": email, "archived": archived}


def update_contact(
    user_id: str,
    email: str,
    name: Optional[str],
    nickname: Optional[str],
    groups: Optional[List[str]],
) -> Dict[str, Any]:
    """Update contact fields: name, nickname, groups (array of strings)."""
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    update_doc: Dict[str, Any] = {}
    if name is not None:
        update_doc["name"] = name
    if nickname is not None:
        update_doc["nickname"] = nickname
    if groups is not None:
        # normalize groups to unique list of lowercase strings
        try:
            norm: List[str] = []
            for g in groups:
                s = (g or "").strip()
                if not s:
                    continue
                if s.lower() not in [x.lower() for x in norm]:
                    norm.append(s)
            update_doc["groups"] = norm
        except Exception:
            update_doc["groups"] = []

    if not update_doc:
        return {"success": False, "error": "No fields to update"}

    contacts_col.update_one(
        {"user_id": user_id, "email": email},
        {"$set": update_doc},
        upsert=False,
    )
    doc = contacts_col.find_one({"user_id": user_id, "email": email}, {"_id": 0})
    return {"success": True, "contact": doc}


def list_contact_groups(user_id: str) -> Dict[str, Any]:
    """Return distinct groups for a user's contacts."""
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    pipeline = [
        {"$match": {"user_id": user_id, "archived": {"$ne": True}}},
        # Ensure groups is an array (if not present or wrong type -> empty array)
        {
            "$project": {
                "groups": {
                    "$cond": [
                        {"$isArray": "$groups"},
                        "$groups",
                        [],
                    ]
                }
            }
        },
        {"$unwind": {"path": "$groups", "preserveNullAndEmptyArrays": False}},
        # Only keep string values for groups
        {"$match": {"groups": {"$type": "string"}}},
        {"$group": {"_id": {"$toLower": "$groups"}}},
        {"$sort": {"_id": 1}},
    ]
    groups = [d["_id"] for d in contacts_col.aggregate(pipeline)]
    return {"success": True, "groups": groups}


def get_contact_detail(user_id: str, email: str) -> Dict[str, Any]:
    """
    Get detailed contact information including notes, last interaction, and past conversations.
    """
    contacts_col = get_contacts_collection()
    conversations_col = get_conversations_collection()

    if contacts_col is None or conversations_col is None:
        return {"success": False, "error": "Database not connected"}

    # Get contact info
    contact = contacts_col.find_one({"user_id": user_id, "email": email}, {"_id": 0})
    if not contact:
        return {"success": False, "error": "Contact not found"}

    # Get last interaction from Gmail (best effort)
    last_interaction = None
    try:
        creds = load_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds)
        query = f"from:{email} OR to:{email}"
        resp = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=1,
        ).execute()
        messages = resp.get("messages", [])
        if messages:
            msg = service.users().messages().get(
                userId="me",
                id=messages[0]["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "To", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            last_interaction = {
                "subject": headers.get("Subject", "(No subject)"),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", "")[:200],
            }
    except Exception as e:
        print(f"[ERROR] Failed to get last interaction: {e}", flush=True)

    # Get past conversations mentioning this contact
    past_conversations: List[Dict[str, Any]] = []
    try:
        contact_name = contact.get("name", "").lower()
        contact_nickname = contact.get("nickname", "").lower()
        search_terms = [email]
        if contact_name:
            search_terms.append(contact_name)
        if contact_nickname:
            search_terms.append(contact_nickname)

        all_conversations = conversations_col.find({"user_id": user_id})
        for conv in all_conversations:
            messages = conv.get("messages", [])
            for msg in messages:
                text = (msg.get("text") or "").lower()
                if any(term in text for term in search_terms if term):
                    session_id = conv.get("session_id", "")
                    created_at = conv.get("created_at", "")
                    past_conversations.append(
                        {
                            "session_id": session_id,
                            "created_at": created_at.isoformat()
                            if hasattr(created_at, "isoformat")
                            else str(created_at),
                            "message": msg.get("text", "")[:200],
                            "role": msg.get("role", ""),
                        }
                    )
                    break
            if len(past_conversations) >= 10:
                break
    except Exception as e:
        print(f"[ERROR] Failed to get past conversations: {e}", flush=True)

    general_notes = contact.get("notes", "")

    return {
        "success": True,
        "contact": contact,
        "last_interaction": last_interaction,
        "general_notes": general_notes,
        "past_conversations": past_conversations,
    }


def get_contact_conversations(
    user_id: str,
    email: str,
    limit: int = 20,
) -> Dict[str, Any]:
    """Get all conversations related to a specific contact."""
    conversations_col = get_conversations_collection()
    contacts_col = get_contacts_collection()

    if conversations_col is None or contacts_col is None:
        return {"success": False, "error": "Database not connected"}

    contact = contacts_col.find_one({"user_id": user_id, "email": email}, {"_id": 0})
    if not contact:
        return {"success": False, "error": "Contact not found"}

    contact_name = contact.get("name", "").lower()
    contact_nickname = contact.get("nickname", "").lower()
    search_terms = [email]
    if contact_name:
        search_terms.append(contact_name)
    if contact_nickname:
        search_terms.append(contact_nickname)

    conversations: List[Dict[str, Any]] = []
    try:
        all_conversations = conversations_col.find({"user_id": user_id}).sort("created_at", -1)
        for conv in all_conversations:
            messages = conv.get("messages", [])
            relevant_messages: List[Dict[str, Any]] = []
            for msg in messages:
                text = (msg.get("text") or "").lower()
                if any(term in text for term in search_terms if term):
                    relevant_messages.append(
                        {
                            "text": msg.get("text", ""),
                            "role": msg.get("role", ""),
                            "timestamp": msg.get("timestamp", ""),
                        }
                    )

            if relevant_messages:
                created_at = conv.get("created_at", "")
                conversations.append(
                    {
                        "session_id": conv.get("session_id", ""),
                        "created_at": created_at.isoformat()
                        if hasattr(created_at, "isoformat")
                        else str(created_at),
                        "messages": relevant_messages,
                    }
                )

            if len(conversations) >= limit:
                break
    except Exception as e:
        print(f"[ERROR] Failed to get conversations: {e}", flush=True)

    return {
        "success": True,
        "conversations": conversations,
    }


