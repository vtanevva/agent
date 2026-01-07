"""
Memory Gate - Curates facts before storage

This module is responsible for:
- Extracting candidate facts from text
- Validating facts (not emotions, not transient)
- Deduplicating facts
- Determining fact type and confidence
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from app.config import Config
from .models import FactType

logger = logging.getLogger(__name__)


@dataclass
class CandidateFact:
    """A candidate fact extracted from text"""
    text: str
    fact_type: FactType
    confidence: float
    source_ref: Optional[str] = None


class MemoryGate:
    """
    Curates and validates facts before storage.
    
    Only stores stable, long-term facts:
    - Preferences (likes/dislikes)
    - Identity (name, job, location)
    - Work info (projects, role)
    - Relationships (family, colleagues)
    
    Does NOT store:
    - Transient emotions ("I'm feeling sad today")
    - One-off statements ("I went to the park")
    - Questions
    """
    
    def __init__(self, llm_service=None):
        """
        Initialize memory gate.
        
        Args:
            llm_service: LLM service for fact extraction
        """
        self.llm_service = llm_service
        
        # Patterns for quick filtering
        self.transient_patterns = [
            r"i('m| am) (feeling|felt)",
            r"today i",
            r"yesterday i",
            r"just (went|did|saw)",
            r"i'm (tired|busy|free)",
        ]
        
        self.question_pattern = r".*\?$"
    
    def _get_llm_service(self):
        """Lazy load LLM service"""
        if self.llm_service is None:
            from app.services.llm_service import get_llm_service
            self.llm_service = get_llm_service()
        return self.llm_service
    
    def extract_candidate_facts(
        self,
        text: str,
        user_id: str,
        source_ref: Optional[str] = None,
    ) -> List[CandidateFact]:
        """
        Extract candidate facts from text using LLM.
        
        Args:
            text: Text to extract facts from
            user_id: User ID
            source_ref: Reference to source message/doc
        
        Returns:
            List of CandidateFact objects
        """
        if not text or len(text.strip()) < 10:
            return []
        
        # Quick filter: skip obvious non-facts
        text_lower = text.lower()
        if any(re.search(pattern, text_lower) for pattern in self.transient_patterns):
            logger.debug(f"Skipped transient statement: {text[:50]}")
            return []
        
        if re.match(self.question_pattern, text.strip()):
            logger.debug(f"Skipped question: {text[:50]}")
            return []
        
        try:
            llm_service = self._get_llm_service()
            
            prompt = f"""Extract stable, long-term facts about the user from this text.

Text: "{text}"

Instructions:
- Only extract facts that are stable over time (preferences, identity, work, relationships)
- Do NOT extract transient emotions, one-off events, or activities
- Each fact should be a single, clear statement
- Classify each fact as: preference, identity, work, relationship, or other
- Assign confidence (0.0-1.0) based on certainty

Return JSON array of facts:
[
  {{"text": "fact statement", "type": "preference", "confidence": 0.9}},
  ...
]

If no stable facts found, return: []
"""
            
            response = llm_service.chat_completion_text(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )
            
            # Parse JSON response
            import json
            content = response.strip()
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            facts_data = json.loads(content)
            
            if not isinstance(facts_data, list):
                logger.warning(f"Expected list of facts, got: {type(facts_data)}")
                return []
            
            candidates = []
            for item in facts_data:
                if not isinstance(item, dict):
                    continue
                
                fact_text = item.get("text", "").strip()
                fact_type_str = item.get("type", "other").lower()
                confidence = float(item.get("confidence", 0.5))
                
                if not fact_text:
                    continue
                
                # Map to FactType enum
                fact_type = self._map_fact_type(fact_type_str)
                
                candidates.append(CandidateFact(
                    text=fact_text,
                    fact_type=fact_type,
                    confidence=confidence,
                    source_ref=source_ref,
                ))
            
            logger.info(f"✅ Extracted {len(candidates)} candidate facts from text")
            return candidates
            
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            return []
    
    def _map_fact_type(self, type_str: str) -> FactType:
        """Map string to FactType enum"""
        type_map = {
            "preference": FactType.PREFERENCE,
            "identity": FactType.IDENTITY,
            "work": FactType.WORK,
            "relationship": FactType.RELATIONSHIP,
            "other": FactType.OTHER,
        }
        return type_map.get(type_str.lower(), FactType.OTHER)
    
    def should_store_fact(self, candidate: CandidateFact) -> bool:
        """
        Determine if a candidate fact should be stored.
        
        Args:
            candidate: CandidateFact to validate
        
        Returns:
            bool: True if fact should be stored
        """
        # Confidence threshold
        if candidate.confidence < 0.5:
            logger.debug(f"Rejected fact (low confidence): {candidate.text}")
            return False
        
        # Length check
        if len(candidate.text) < 5 or len(candidate.text) > 500:
            logger.debug(f"Rejected fact (length): {candidate.text}")
            return False
        
        # Additional transient checks
        text_lower = candidate.text.lower()
        if any(re.search(pattern, text_lower) for pattern in self.transient_patterns):
            logger.debug(f"Rejected fact (transient): {candidate.text}")
            return False
        
        return True
    
    def deduplicate_facts(
        self,
        new_candidates: List[CandidateFact],
        existing_facts: List[Dict[str, Any]],
    ) -> List[CandidateFact]:
        """
        Remove duplicate facts using string similarity.
        
        Args:
            new_candidates: New candidate facts
            existing_facts: Existing facts from database
        
        Returns:
            List of unique candidate facts
        """
        if not existing_facts:
            return new_candidates
        
        unique_candidates = []
        existing_texts = [fact.get("text", "").lower() for fact in existing_facts]
        
        for candidate in new_candidates:
            candidate_text = candidate.text.lower()
            
            # Simple deduplication: exact match or high string overlap
            is_duplicate = False
            for existing_text in existing_texts:
                if candidate_text == existing_text:
                    is_duplicate = True
                    break
                
                # Check for high overlap (>80% of words in common)
                candidate_words = set(candidate_text.split())
                existing_words = set(existing_text.split())
                
                if len(candidate_words) > 0 and len(existing_words) > 0:
                    overlap = len(candidate_words & existing_words)
                    similarity = overlap / max(len(candidate_words), len(existing_words))
                    
                    if similarity > 0.8:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique_candidates.append(candidate)
            else:
                logger.debug(f"Deduplicated fact: {candidate.text}")
        
        return unique_candidates
    
    def store_facts(
        self,
        user_id: str,
        candidates: List[CandidateFact],
    ) -> int:
        """
        Store validated facts to MongoDB.
        
        Args:
            user_id: User ID
            candidates: List of candidate facts to store
        
        Returns:
            int: Number of facts stored
        """
        from .models import get_memory_facts_collection
        from uuid import uuid4
        
        facts_collection = get_memory_facts_collection()
        if facts_collection is None:
            logger.warning("Facts collection not available")
            return 0
        
        stored_count = 0
        
        for candidate in candidates:
            if not self.should_store_fact(candidate):
                continue
            
            try:
                fact_doc = {
                    "_id": str(uuid4()),
                    "user_id": user_id,
                    "text": candidate.text,
                    "type": candidate.fact_type.value,
                    "confidence": candidate.confidence,
                    "source_ref": candidate.source_ref,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "is_active": True,
                }
                
                facts_collection.insert_one(fact_doc)
                stored_count += 1
                logger.info(f"💾 Stored fact: {candidate.text} (type={candidate.fact_type.value})")
                
            except Exception as e:
                logger.error(f"Failed to store fact: {e}")
        
        return stored_count


# Singleton instance
_memory_gate: Optional[MemoryGate] = None


def get_memory_gate() -> MemoryGate:
    """Get singleton memory gate instance"""
    global _memory_gate
    if _memory_gate is None:
        _memory_gate = MemoryGate()
    return _memory_gate

