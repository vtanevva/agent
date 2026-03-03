"""
ContactsAgent - handles contact management and relationship tracking.

Handles:
- Relationship management (project-contact relationships)
- Contact search and updates
- View contact details
- Manage contact groups
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import uuid4

from app.utils.logging_utils import get_logger
from app.memory.models import get_project_contact_relationships_collection

logger = get_logger(__name__)


class ContactsAgent:
    """
    Agent for handling contact management and relationships.
    
    Manages project-contact relationships with source tracking.
    """
    
    def __init__(self):
        """Initialize ContactsAgent."""
        self.relationships_col = get_project_contact_relationships_collection()
    
    def create_or_update_relationship(
        self,
        user_id: str,
        projects: Optional[List[str]] = None,
        contacts: Optional[List[str]] = None,
        source_message_id: Optional[str] = None,
        source: Optional[str] = None,
        notes: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create or update a project-contact relationship.
        
        Parameters
        ----------
        user_id : str
            User identifier
        projects : list of str, optional
            List of project IDs or names
        contacts : list of str, optional
            List of contact emails
        source_message_id : str, optional
            Source message ID that created this relationship
        source : str, optional
            Source type: "email", "chat", "calendar", "manual", etc.
            
        Returns
        -------
        dict or None
            Created/updated relationship document or None if failed
        """
        if self.relationships_col is None:
            logger.warning("Project-contact relationships collection not available")
            return None
        
        if not projects and not contacts:
            logger.warning("Cannot create relationship without projects or contacts")
            return None
        
        try:
            # Normalize inputs
            projects = projects or []
            contacts = [c.lower().strip() if c else "" for c in (contacts or [])]
            contacts = [c for c in contacts if c]  # Remove empty strings
            notes = notes or []
            description = description or None
            
            # Create unique key based on user_id, projects, and contacts
            # For upsert matching, we'll use a combination
            relationship_doc = {
                "user_id": user_id,
                "projects": projects,
                "contacts": contacts,
                "source_message_ids": [source_message_id] if source_message_id else [],
                "sources": [source] if source else [],
                "notes": notes,
                "description": description,
                "updated_at": datetime.utcnow()
            }
            
            # Try to find existing relationship with same projects and contacts
            existing = self.relationships_col.find_one({
                "user_id": user_id,
                "projects": {"$all": projects} if projects else {"$size": 0},
                "contacts": {"$all": contacts} if contacts else {"$size": 0}
            })
            
            if existing:
                # Update existing relationship
                update_doc = {
                    "$set": {
                        "updated_at": datetime.utcnow()
                    }
                }
                
                add_to_set = {}
                if projects:
                    add_to_set["projects"] = {"$each": projects}
                if contacts:
                    add_to_set["contacts"] = {"$each": contacts}
                if source_message_id:
                    add_to_set["source_message_ids"] = source_message_id
                if source:
                    add_to_set["sources"] = source
                
                if notes:
                    add_to_set["notes"] = {"$each": notes}
                
                if add_to_set:
                    update_doc["$addToSet"] = add_to_set
                
                # Update description if provided
                if description is not None:
                    update_doc["$set"]["description"] = description
                
                self.relationships_col.update_one(
                    {"_id": existing["_id"]},
                    update_doc
                )
                relationship_doc["_id"] = existing["_id"]
                relationship_doc["created_at"] = existing.get("created_at", datetime.utcnow())
                logger.info(f"Updated relationship for user {user_id}: projects={projects}, contacts={contacts}")
            else:
                # Create new relationship
                relationship_doc["_id"] = str(uuid4())
                relationship_doc["created_at"] = datetime.utcnow()
                self.relationships_col.insert_one(relationship_doc)
                logger.info(f"Created new relationship for user {user_id}: projects={projects}, contacts={contacts}")
            
            return relationship_doc
            
        except Exception as e:
            logger.error(f"Failed to create/update relationship: {e}")
            return None
    
    def get_relationships_by_user(
        self,
        user_id: str,
        project: Optional[str] = None,
        contact: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get relationships for a user, optionally filtered by project or contact.
        
        Parameters
        ----------
        user_id : str
            User identifier
        project : str, optional
            Filter by project ID or name
        contact : str, optional
            Filter by contact email
            
        Returns
        -------
        list of dict
            List of relationship documents
        """
        if self.relationships_col is None:
            return []
        
        try:
            query = {"user_id": user_id}
            
            if project:
                query["projects"] = project
            if contact:
                query["contacts"] = contact.lower().strip()
            
            relationships = list(self.relationships_col.find(query))
            return relationships
            
        except Exception as e:
            logger.error(f"Failed to get relationships: {e}")
            return []
    
    def add_to_relationship(
        self,
        user_id: str,
        relationship_id: Optional[str] = None,
        projects: Optional[List[str]] = None,
        contacts: Optional[List[str]] = None,
        source_message_id: Optional[str] = None,
        source: Optional[str] = None,
        notes: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Add projects, contacts, or sources to an existing relationship.
        
        Parameters
        ----------
        user_id : str
            User identifier
        relationship_id : str, optional
            Specific relationship ID to update. If None, will try to find by projects/contacts.
        projects : list of str, optional
            Projects to add
        contacts : list of str, optional
            Contacts to add
        source_message_id : str, optional
            Source message ID to add
        source : str, optional
            Source type to add
            
        Returns
        -------
        bool
            True if updated successfully, False otherwise
        """
        if self.relationships_col is None:
            return False
        
        try:
            if relationship_id:
                query = {"_id": relationship_id, "user_id": user_id}
            else:
                # Try to find by projects/contacts
                query = {"user_id": user_id}
                if projects:
                    query["projects"] = {"$in": projects}
                if contacts:
                    query["contacts"] = {"$in": [c.lower().strip() for c in contacts]}
            
            update_doc = {
                "$set": {"updated_at": datetime.utcnow()}
            }
            
            add_to_set = {}
            if projects:
                add_to_set["projects"] = {"$each": projects}
            if contacts:
                add_to_set["contacts"] = {"$each": [c.lower().strip() for c in contacts]}
            if source_message_id:
                add_to_set["source_message_ids"] = source_message_id
            if source:
                add_to_set["sources"] = source
            if notes:
                add_to_set["notes"] = {"$each": notes}
            
            if add_to_set:
                update_doc["$addToSet"] = add_to_set
            
            if description is not None:
                update_doc["$set"]["description"] = description
            
            result = self.relationships_col.update_one(query, update_doc)
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to add to relationship: {e}")
            return False
    
    def handle_chat(
        self,
        user_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Handle a contact-related chat message.
        
        Parameters
        ----------
        user_id : str
            User identifier
        message : str
            User's message
        metadata : dict, optional
            Additional metadata (may contain projects, contacts, source_message_id, source)
            
        Returns
        -------
        str
            Response
        """
        logger.info(f"ContactsAgent called for user {user_id}")
        
        # If metadata contains relationship info, create/update relationship
        if metadata:
            projects = metadata.get("projects", [])
            contacts = metadata.get("contacts", [])
            source_message_id = metadata.get("source_message_id")
            source = metadata.get("source", "manual")
            notes = metadata.get("notes", [])
            description = metadata.get("description")
            
            if projects or contacts:
                relationship = self.create_or_update_relationship(
                    user_id=user_id,
                    projects=projects if isinstance(projects, list) else [projects] if projects else None,
                    contacts=contacts if isinstance(contacts, list) else [contacts] if contacts else None,
                    source_message_id=source_message_id,
                    source=source,
                    notes=notes if isinstance(notes, list) else [notes] if notes else None,
                    description=description,
                )
                
                if relationship:
                    response = f"Relationship created/updated successfully. Projects: {relationship.get('projects', [])}, Contacts: {relationship.get('contacts', [])}"
                    if relationship.get('notes'):
                        response += f", Notes: {len(relationship.get('notes', []))} note(s)"
                    if relationship.get('description'):
                        response += f", Description: {relationship.get('description')[:50]}..."
                    return response
        
        return "Contact management features are available. I can help you manage relationships between projects and contacts."

