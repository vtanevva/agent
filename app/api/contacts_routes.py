"""Contacts-related API routes."""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app.memory.models import get_project_contact_relationships_collection

contacts_bp = Blueprint('contacts', __name__, url_prefix='/api/contacts')


@contacts_bp.route("/status", methods=["GET"])
def contacts_status():
    """Placeholder for Contacts routes."""
    return {"status": "not implemented"}, 501


@contacts_bp.route("/with-relationships", methods=["POST"])
def contacts_with_relationships():
    """
    Get contacts with their associated projects, notes, and descriptions from relationships.
    
    Returns a list of contacts, each with:
    - Contact information (name, email, etc.)
    - Associated projects (from relationships)
    - Notes (from relationships)
    - Description (from relationships)
    """
    data = request.get_json(force=True, silent=True) or {}
    original_user_id = (data.get("user_id") or "anonymous").strip()
    user_id = original_user_id.lower()
    
    relationships_col = get_project_contact_relationships_collection()
    
    if not relationships_col:
        return jsonify({"success": False, "error": "Database not connected"}), 500
    
    try:
        from app.utils.logging_utils import get_logger
        logger = get_logger(__name__)
        
        # Debug: Check what's actually in the database
        all_count = relationships_col.count_documents({})
        logger.info(f"[CONTACTS API] Querying for user_id: '{user_id}', Total relationships in DB: {all_count}")
        
        # Try query with exact user_id
        relationships = list(relationships_col.find({"user_id": user_id}))
        logger.info(f"[CONTACTS API] Found {len(relationships)} relationships with exact user_id match")
        
        # If no results, check what user_ids actually exist
        if len(relationships) == 0 and all_count > 0:
            sample = relationships_col.find_one({})
            if sample:
                sample_user_id = sample.get("user_id")
                logger.warning(f"[CONTACTS API] No matches! Querying for '{user_id}' but sample has user_id: '{sample_user_id}'")
                # Try with original user_id (not lowercased)
                relationships = list(relationships_col.find({"user_id": original_user_id}))
                logger.info(f"[CONTACTS API] After trying original user_id '{original_user_id}': {len(relationships)} relationships")
                # If still no results, try case-insensitive search
                if len(relationships) == 0:
                    import re
                    relationships = list(relationships_col.find({"user_id": re.compile(f"^{re.escape(original_user_id)}$", re.IGNORECASE)}))
                    logger.info(f"[CONTACTS API] After case-insensitive search: {len(relationships)} relationships")
        
        if relationships:
            logger.info(f"[CONTACTS API] First relationship: projects={relationships[0].get('projects')}, contacts={relationships[0].get('contacts')}")
        
        # Format relationships - expand project-contact combinations
        # Show ALL relationships: with projects, with contacts, or both
        project_contact_rels = []
        for rel in relationships:
            rel_projects = [p for p in (rel.get("projects", []) or []) if p and str(p).strip()]
            rel_contacts = [c for c in (rel.get("contacts", []) or []) if c and str(c).strip()]
            
            created_at = rel.get("created_at")
            updated_at = rel.get("updated_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            if isinstance(updated_at, datetime):
                updated_at = updated_at.isoformat()
            
            # If we have both projects and contacts, create entries for each combination
            if rel_projects and rel_contacts:
                for project in rel_projects:
                    for contact_email in rel_contacts:
                        project_contact_rels.append({
                            "project": project,
                            "contact_email": contact_email,
                            "description": rel.get("description"),
                            "notes": rel.get("notes", []),
                            "sources": rel.get("sources", []),
                            "created_at": created_at,
                            "updated_at": updated_at
                        })
            # If we have projects but no contacts
            elif rel_projects:
                for project in rel_projects:
                    project_contact_rels.append({
                        "project": project,
                        "contact_email": "(No contacts assigned)",
                        "description": rel.get("description"),
                        "notes": rel.get("notes", []),
                        "sources": rel.get("sources", []),
                        "created_at": created_at,
                        "updated_at": updated_at
                    })
            # If we have contacts but no projects
            elif rel_contacts:
                for contact_email in rel_contacts:
                    project_contact_rels.append({
                        "project": "(No project assigned)",
                        "contact_email": contact_email,
                        "description": rel.get("description"),
                        "notes": rel.get("notes", []),
                        "sources": rel.get("sources", []),
                        "created_at": created_at,
                        "updated_at": updated_at
                    })
            # If we have neither (shouldn't happen, but handle it)
            else:
                project_contact_rels.append({
                    "project": "(No project assigned)",
                    "contact_email": "(No contacts assigned)",
                    "description": rel.get("description"),
                    "notes": rel.get("notes", []),
                    "sources": rel.get("sources", []),
                    "created_at": created_at,
                    "updated_at": updated_at
                })
        
        return jsonify({
            "success": True,
            "project_contact_relationships": project_contact_rels,
            "relationships_count": len(project_contact_rels)
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

