"""
Relationships Service - handles relationship tracking and management.

This service is responsible for:
- Creating and updating relationships from various sources (emails, chat, calendar)
- Linking relationships to projects, tasks, facts, and threads
- Managing relationship metadata (importance, frequency, notes)
- Syncing with contacts collection to ensure consistency
- Merging contact info into relationships
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from app.memory.models import get_relationships_collection
from app.db.collections import get_contacts_collection
from app.utils.user_email_utils import get_user_email
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class RelationshipsService:
    """
    Service for managing relationships between users and contacts.
    
    Handles:
    - Creating relationships from sent emails (recipients)
    - Updating relationships from received emails (if relationship exists)
    - Linking relationships to projects, tasks, facts, and threads
    """
    
    def __init__(self):
        """Initialize the Relationships service."""
        self.relationships_col = get_relationships_collection()
        self.contacts_col = get_contacts_collection()
    
    def _extract_email_from_string(self, email_string: str) -> Optional[str]:
        """
        Extract email address from string that may contain "Name <email@domain.com>" format.
        
        Args:
            email_string: Email string that may contain name and email
            
        Returns:
            Extracted email address or None if invalid
        """
        if not email_string:
            return None
        
        email_string = email_string.lower().strip()
        
        # Extract email from "Name <email@domain.com>" format
        if "<" in email_string and ">" in email_string:
            email = email_string.split("<")[1].split(">")[0].strip()
        elif "@" in email_string:
            email = email_string.strip()
        else:
            return None
        
        # Validate email format
        if "@" in email and "." in email.split("@")[1]:
            return email
        
        return None
    
    def _is_email_from_user(self, user_id: str, sender_email: str) -> bool:
        """
        Check if email was sent by the user.
        
        Args:
            user_id: User identifier
            sender_email: Email address of sender
            
        Returns:
            True if sender is the user, False otherwise
        """
        user_email = get_user_email(user_id).lower()
        sender_email_lower = sender_email.lower()
        return sender_email_lower == user_email
    
    def track_from_sent_email(
        self,
        user_id: str,
        recipients: str,
        thread_id: str,
    ) -> List[str]:
        """
        Track relationships from a sent email (create/update relationships for recipients).
        
        Args:
            user_id: User identifier
            recipients: Comma-separated recipient emails or single email string
            thread_id: Email thread ID
            
        Returns:
            List of recipient emails that were tracked
        """
        if not self.relationships_col:
            logger.warning("Relationships collection not available")
            return []
        
        user_email = get_user_email(user_id).lower()
        tracked_emails = []
        
        # Parse recipients (handle comma-separated and "Name <email>" format)
        if isinstance(recipients, str):
            recipient_list = [r.strip() for r in recipients.split(',')]
        else:
            recipient_list = [recipients] if recipients else []
        
        for recipient in recipient_list:
            recipient_email = self._extract_email_from_string(recipient)
            
            if not recipient_email:
                continue
            
            # Skip if recipient is the user themselves
            if recipient_email == user_email:
                continue
            
            # Create or update relationship for recipient
            try:
                self.relationships_col.update_one(
                    {
                        "user_id": user_id,
                        "contact_email": recipient_email
                    },
                    {
                        "$set": {
                            "last_contact": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        },
                        "$inc": {
                            "contact_count": 1
                        },
                        "$addToSet": {
                            "related_threads": thread_id
                        },
                        "$setOnInsert": {
                            "_id": str(uuid4()),
                            "user_id": user_id,
                            "contact_email": recipient_email,
                            "importance": "medium",
                            "relationship_type": "contact",
                            "related_projects": [],
                            "related_tasks": [],
                            "related_facts": [],
                            "created_at": datetime.utcnow()
                        }
                    },
                    upsert=True
                )
                tracked_emails.append(recipient_email)
                logger.info(f"[RELATIONSHIP] Tracked recipient {recipient_email} from sent email (thread: {thread_id})")
            except Exception as e:
                logger.error(f"Failed to track relationship for {recipient_email}: {e}")
        
        return tracked_emails
    
    def track_from_received_email(
        self,
        user_id: str,
        sender: str,
        thread_id: str,
    ) -> bool:
        """
        Track relationship from a received email (only update if relationship exists).
        
        This avoids creating relationships from newsletters/spam.
        Only updates existing relationships (where user has previously sent email to this person).
        
        Args:
            user_id: User identifier
            sender: Sender email string
            thread_id: Email thread ID
            
        Returns:
            True if relationship was updated, False if no relationship exists
        """
        if not self.relationships_col:
            logger.warning("Relationships collection not available")
            return False
        
        sender_email = self._extract_email_from_string(sender)
        
        if not sender_email:
            return False
        
        # Check if relationship exists (user has sent email to this person before)
        existing = self.relationships_col.find_one({
            "user_id": user_id,
            "contact_email": sender_email
        })
        
        if not existing:
            # No relationship exists - skip (avoids newsletters/spam)
            return False
        
        # Update existing relationship
        try:
            self.relationships_col.update_one(
                {
                    "user_id": user_id,
                    "contact_email": sender_email
                },
                {
                    "$set": {
                        "last_contact": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {
                        "contact_count": 1
                    },
                    "$addToSet": {
                        "related_threads": thread_id
                    }
                }
            )
            logger.info(f"[RELATIONSHIP] Updated existing relationship with {sender_email} (received email, thread: {thread_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to update relationship for {sender_email}: {e}")
            return False
    
    def link_project(
        self,
        user_id: str,
        contact_email: str,
        project_name: str,
    ) -> bool:
        """
        Link a project to a relationship.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            project_name: Project name or ID
            
        Returns:
            True if linked successfully, False otherwise
        """
        if not self.relationships_col:
            return False
        
        try:
            self.relationships_col.update_one(
                {
                    "user_id": user_id,
                    "contact_email": contact_email
                },
                {
                    "$addToSet": {"related_projects": project_name}
                }
            )
            logger.debug(f"Linked project '{project_name}' to relationship with {contact_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to link project to relationship: {e}")
            return False
    
    def link_tasks(
        self,
        user_id: str,
        contact_email: str,
        task_ids: List[str],
    ) -> bool:
        """
        Link tasks to a relationship.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            task_ids: List of task IDs to link
            
        Returns:
            True if linked successfully, False otherwise
        """
        if not self.relationships_col or not task_ids:
            return False
        
        try:
            self.relationships_col.update_one(
                {
                    "user_id": user_id,
                    "contact_email": contact_email
                },
                {
                    "$addToSet": {"related_tasks": {"$each": task_ids}}
                }
            )
            logger.debug(f"Linked {len(task_ids)} tasks to relationship with {contact_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to link tasks to relationship: {e}")
            return False
    
    def link_facts(
        self,
        user_id: str,
        contact_email: str,
        fact_ids: List[str],
    ) -> bool:
        """
        Link facts to a relationship.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            fact_ids: List of fact IDs to link
            
        Returns:
            True if linked successfully, False otherwise
        """
        if not self.relationships_col or not fact_ids:
            return False
        
        try:
            self.relationships_col.update_one(
                {
                    "user_id": user_id,
                    "contact_email": contact_email
                },
                {
                    "$addToSet": {"related_facts": {"$each": fact_ids}}
                }
            )
            logger.debug(f"Linked {len(fact_ids)} facts to relationship with {contact_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to link facts to relationship: {e}")
            return False
    
    def _get_or_create_contact(self, user_id: str, contact_email: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get or create a contact in the contacts collection.
        
        This ensures contacts and relationships stay in sync.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            name: Optional name for the contact
            
        Returns:
            Contact document or None if collection unavailable
        """
        if not self.contacts_col:
            return None
        
        try:
            # Check if contact exists
            contact = self.contacts_col.find_one({
                "user_id": user_id,
                "email": contact_email.lower()
            })
            
            if contact:
                return contact
            
            # Create new contact
            contact_doc = {
                "user_id": user_id,
                "email": contact_email.lower(),
                "name": name or "",
                "count": 0,
                "first_seen": datetime.utcnow(),
                "last_seen": datetime.utcnow(),
                "groups": []
            }
            
            self.contacts_col.insert_one(contact_doc)
            logger.debug(f"Created contact for {contact_email}")
            return contact_doc
            
        except Exception as e:
            logger.error(f"Failed to get/create contact for {contact_email}: {e}")
            return None
    
    def _merge_contact_info(self, user_id: str, contact_email: str, relationship_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge contact information into relationship document.
        
        Gets contact name and other info from contacts collection and adds to relationship.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            relationship_doc: Relationship document
            
        Returns:
            Relationship document with merged contact info
        """
        if not self.contacts_col:
            return relationship_doc
        
        try:
            contact = self.contacts_col.find_one({
                "user_id": user_id,
                "email": contact_email.lower()
            })
            
            if contact:
                # Merge contact info into relationship
                relationship_doc["contact_name"] = contact.get("name", "")
                relationship_doc["contact_groups"] = contact.get("groups", [])
                relationship_doc["contact_first_seen"] = contact.get("first_seen")
                relationship_doc["contact_count"] = contact.get("count", 0)
                
        except Exception as e:
            logger.warning(f"Failed to merge contact info for {contact_email}: {e}")
        
        return relationship_doc
    
    def get_relationship_with_contact(self, user_id: str, contact_email: str) -> Optional[Dict[str, Any]]:
        """
        Get relationship with merged contact information.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            
        Returns:
            Relationship document with contact info merged, or None if not found
        """
        if not self.relationships_col:
            return None
        
        try:
            relationship = self.relationships_col.find_one({
                "user_id": user_id,
                "contact_email": contact_email.lower()
            })
            
            if relationship:
                return self._merge_contact_info(user_id, contact_email, relationship)
            
            return None
        except Exception as e:
            logger.error(f"Failed to get relationship with contact for {contact_email}: {e}")
            return None
    
    def sync_contact_to_relationship(
        self,
        user_id: str,
        contact_email: str,
        name: Optional[str] = None,
    ) -> bool:
        """
        Ensure a contact exists in contacts collection when creating a relationship.
        
        This keeps contacts and relationships in sync.
        When a relationship is created, the corresponding contact should also exist.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            name: Optional name for the contact
            
        Returns:
            True if contact was created/updated, False otherwise
        """
        contact = self._get_or_create_contact(user_id, contact_email, name)
        return contact is not None
    
    def update_contact_from_relationship(
        self,
        user_id: str,
        contact_email: str,
    ) -> bool:
        """
        Update contact's last_seen from relationship's last_contact.
        
        Keeps contacts collection in sync with relationship activity.
        
        Args:
            user_id: User identifier
            contact_email: Contact email address
            
        Returns:
            True if updated, False otherwise
        """
        if not self.contacts_col or not self.relationships_col:
            return False
        
        try:
            # Get relationship's last_contact
            relationship = self.relationships_col.find_one({
                "user_id": user_id,
                "contact_email": contact_email.lower()
            })
            
            if relationship and relationship.get("last_contact"):
                # Update contact's last_seen
                self.contacts_col.update_one(
                    {
                        "user_id": user_id,
                        "email": contact_email.lower()
                    },
                    {
                        "$set": {
                            "last_seen": relationship["last_contact"]
                        }
                    }
                )
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to update contact from relationship: {e}")
            return False
    
    def process_email(
        self,
        user_id: str,
        email_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Process an email and track relationships appropriately.
        
        This is the main entry point for email-based relationship tracking.
        It determines if email was sent or received and calls appropriate method.
        Also ensures contacts are synced when relationships are created.
        
        Args:
            user_id: User identifier
            email_data: Email data dict with 'from', 'to', 'thread_id' fields
            
        Returns:
            Dict with:
                - tracked_emails: List of emails that were tracked
                - email_sent_by_user: bool indicating if email was sent by user
        """
        sender = email_data.get('from', '')
        recipients = email_data.get('to', '')
        thread_id = email_data.get('thread_id', '')
        
        if not thread_id:
            logger.warning("No thread_id provided for email relationship tracking")
            return {"tracked_emails": [], "email_sent_by_user": False}
        
        # Extract sender email
        sender_email = self._extract_email_from_string(sender)
        
        if not sender_email:
            return {"tracked_emails": [], "email_sent_by_user": False}
        
        # Check if email was sent by user
        email_sent_by_user = self._is_email_from_user(user_id, sender_email)
        
        if email_sent_by_user:
            # Email was sent - track recipients and ensure contacts exist
            tracked_emails = self.track_from_sent_email(
                user_id=user_id,
                recipients=recipients,
                thread_id=thread_id
            )
            
            # Sync contacts for each tracked email
            for recipient_email in tracked_emails:
                # Extract name from recipient string if available
                recipient_string = recipients.lower()
                name = None
                if "<" in recipient_string and ">" in recipient_string:
                    # Try to extract name from "Name <email>" format
                    try:
                        name_part = recipient_string.split("<")[0].strip().strip('"').strip("'")
                        if name_part and "@" not in name_part:
                            name = name_part.title()
                    except Exception:
                        pass
                
                self.sync_contact_to_relationship(user_id, recipient_email, name)
            
            return {
                "tracked_emails": tracked_emails,
                "email_sent_by_user": True
            }
        else:
            # Email was received - only update if relationship exists
            updated = self.track_from_received_email(
                user_id=user_id,
                sender=sender,
                thread_id=thread_id
            )
            
            # If relationship was updated, sync contact's last_seen
            if updated:
                self.update_contact_from_relationship(user_id, sender_email)
            
            return {
                "tracked_emails": [sender_email] if updated else [],
                "email_sent_by_user": False
            }


# Singleton instance
_relationships_service: Optional[RelationshipsService] = None


def get_relationships_service() -> RelationshipsService:
    """Get the singleton Relationships service instance."""
    global _relationships_service
    if _relationships_service is None:
        _relationships_service = RelationshipsService()
    return _relationships_service

