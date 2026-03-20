"""
MH1 Procedural Memory Store

Firebase-persisted procedural memory for cross-skill generalizations.

Procedural knowledge represents high-level strategies that apply across multiple skills.
Unlike episodic memory (specific experiences) or semantic memory (skill-specific patterns),
procedural knowledge captures meta-strategies validated across different skill contexts.

Examples of procedural knowledge:
- "Morning sends work better for engagement" (validated across email, social, push skills)
- "Gradual rollouts reduce risk" (validated across campaigns, features, pricing skills)
- "Personalization improves conversions" (validated across email, ads, landing page skills)

Procedural knowledge has:
- High stability (very slow decay rate of 0.995)
- Cross-skill validation requirements (minimum 3 skills by default)
- Aggregate confidence based on validating skill performance

Firebase path: system/intelligence/procedural/{knowledge_id}
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..types import Domain, ProceduralKnowledge, SemanticPattern

logger = logging.getLogger(__name__)


@dataclass
class ProceduralMemoryConfig:
    """
    Configuration for procedural memory behavior.
    
    Procedural knowledge requires validation across multiple skills before creation.
    It decays very slowly since it represents stable, cross-domain generalizations.
    
    Attributes:
        min_validating_skills: Minimum number of different skills needed to create
                               procedural knowledge. Default is 3 to ensure the
                               generalization truly applies across contexts.
        min_cross_skill_confidence: Minimum average confidence across validating skills
                                    required for the knowledge to be considered valid.
        decay_rate: Per-day decay multiplier. Very slow (0.995) because procedural
                    knowledge represents stable generalizations.
    """
    min_validating_skills: int = 3
    min_cross_skill_confidence: float = 0.6
    decay_rate: float = 0.995  # Very slow decay for stable generalizations


class ProceduralMemoryStore:
    """
    Thread-safe Firebase-backed procedural memory store.
    
    Procedural knowledge represents generalizations that apply across multiple skills.
    This is the highest level of memory abstraction in the cognitive architecture:
    
    - Working Memory: Immediate, session-scoped context
    - Episodic Memory: Specific experiences that decay over time
    - Semantic Memory: Skill-specific patterns learned from episodes
    - Procedural Memory: Cross-skill generalizations from semantic patterns
    
    Procedural knowledge is created when similar patterns are observed and validated
    across multiple different skills. For example, if timing patterns (morning sends
    perform better) are validated in email-drip, social-post, and push-notification
    skills, this can be generalized into procedural knowledge.
    
    Key characteristics:
    - Requires validation from multiple skills (min_validating_skills)
    - Has aggregate confidence based on all validating skills
    - Decays very slowly (knowledge is stable once established)
    - Can be applied to new skills that haven't validated it yet
    """
    
    _collection_base = "system/intelligence/procedural"
    
    def __init__(
        self,
        firebase_client: Any,
        config: Optional[ProceduralMemoryConfig] = None
    ):
        """
        Initialize the procedural memory store.
        
        Args:
            firebase_client: Firebase client with set_document, get_document,
                           query, update_document, delete_document, get_collection methods
            config: Configuration for validation thresholds and decay
        """
        self._firebase = firebase_client
        self._config = config or ProceduralMemoryConfig()
        self._lock = threading.RLock()
    
    def store(self, knowledge: ProceduralKnowledge) -> str:
        """
        Store procedural knowledge to Firebase.
        
        Args:
            knowledge: The ProceduralKnowledge to store
            
        Returns:
            The knowledge_id of the stored knowledge
            
        Raises:
            AttributeError: If firebase_client is missing required methods
        """
        with self._lock:
            doc_data = knowledge.to_dict()
            
            if hasattr(self._firebase, "set_document"):
                self._firebase.set_document(
                    collection=self._collection_base,
                    doc_id=knowledge.knowledge_id,
                    data=doc_data
                )
            else:
                logger.warning("Firebase client missing set_document method")
                raise AttributeError("firebase_client missing set_document method")
            
            logger.debug(
                f"Stored procedural knowledge {knowledge.knowledge_id}: "
                f"{knowledge.description[:50]}..."
            )
            return knowledge.knowledge_id
    
    def retrieve(
        self,
        skill_name: Optional[str] = None,
        domain: Optional[Domain] = None,
        min_confidence: Optional[float] = None,
        limit: int = 20
    ) -> List[ProceduralKnowledge]:
        """
        Retrieve procedural knowledge with optional filtering.
        
        Filters can be combined to find knowledge applicable to a specific
        skill and domain context with sufficient confidence.
        
        Args:
            skill_name: If provided, only return knowledge where this skill
                       is in applicable_skills
            domain: If provided, only return knowledge where this domain
                   is in applicable_domains
            min_confidence: If provided, only return knowledge with
                          cross_skill_confidence >= this value
            limit: Maximum number of results to return
            
        Returns:
            List of ProceduralKnowledge objects sorted by confidence descending
        """
        with self._lock:
            try:
                # Query all procedural knowledge
                if hasattr(self._firebase, "get_collection"):
                    docs = self._firebase.get_collection(
                        collection=self._collection_base,
                        limit=limit * 3  # Over-fetch to account for filtering
                    )
                else:
                    logger.warning("Firebase client missing get_collection method")
                    return []
                
                if not docs:
                    return []
                
                # Convert and filter
                results = []
                for doc in docs:
                    knowledge = self._doc_to_knowledge(doc)
                    if knowledge is None:
                        continue
                    
                    # Filter by skill_name if in applicable_skills
                    if skill_name is not None:
                        if skill_name not in knowledge.applicable_skills:
                            continue
                    
                    # Filter by domain if in applicable_domains
                    if domain is not None:
                        domain_value = domain.value if isinstance(domain, Domain) else domain
                        if domain_value not in knowledge.applicable_domains:
                            continue
                    
                    # Filter by cross_skill_confidence >= min_confidence
                    if min_confidence is not None:
                        if knowledge.cross_skill_confidence < min_confidence:
                            continue
                    
                    results.append(knowledge)
                
                # Sort by confidence descending
                results.sort(key=lambda k: k.cross_skill_confidence, reverse=True)
                
                # Apply limit
                return results[:limit]
                
            except Exception as e:
                logger.error(f"Error retrieving procedural knowledge: {e}")
                return []
    
    def get_knowledge(self, knowledge_id: str) -> Optional[ProceduralKnowledge]:
        """
        Get a single procedural knowledge entry by ID.
        
        Args:
            knowledge_id: The knowledge_id to retrieve
            
        Returns:
            ProceduralKnowledge or None if not found
        """
        with self._lock:
            try:
                if hasattr(self._firebase, "get_document"):
                    doc = self._firebase.get_document(
                        collection=self._collection_base,
                        doc_id=knowledge_id
                    )
                    if doc:
                        return self._doc_to_knowledge(doc)
                else:
                    logger.warning("Firebase client missing get_document method")
                
            except Exception as e:
                logger.error(f"Error getting knowledge {knowledge_id}: {e}")
            
            return None
    
    def update_validation(
        self,
        knowledge_id: str,
        skill_name: str,
        accuracy: float
    ) -> bool:
        """
        Update validation data for a procedural knowledge entry.
        
        Called when a skill validates (or invalidates) procedural knowledge
        through its execution outcomes.
        
        Args:
            knowledge_id: The knowledge entry to update
            skill_name: The skill providing validation
            accuracy: The accuracy observed (0.0 to 1.0)
            
        Returns:
            True if updated successfully, False otherwise
        """
        with self._lock:
            try:
                # Get current knowledge
                knowledge = self.get_knowledge(knowledge_id)
                if knowledge is None:
                    logger.warning(f"Knowledge {knowledge_id} not found for validation update")
                    return False
                
                # Update validating_skills[skill_name] = accuracy
                knowledge.validating_skills[skill_name] = accuracy
                
                # Recalculate cross_skill_confidence as average of all validating_skills
                if knowledge.validating_skills:
                    total_accuracy = sum(knowledge.validating_skills.values())
                    knowledge.cross_skill_confidence = total_accuracy / len(knowledge.validating_skills)
                
                # Update timestamp
                knowledge.updated_at = datetime.now(timezone.utc).isoformat()
                
                # Persist update
                if hasattr(self._firebase, "update_document"):
                    self._firebase.update_document(
                        collection=self._collection_base,
                        doc_id=knowledge_id,
                        data={
                            "validating_skills": knowledge.validating_skills,
                            "cross_skill_confidence": knowledge.cross_skill_confidence,
                            "updated_at": knowledge.updated_at
                        }
                    )
                    logger.debug(
                        f"Updated validation for {knowledge_id}: "
                        f"{skill_name}={accuracy:.2f}, "
                        f"cross_skill_confidence={knowledge.cross_skill_confidence:.2f}"
                    )
                    return True
                else:
                    logger.warning("Firebase client missing update_document method")
                    return False
                    
            except Exception as e:
                logger.error(f"Error updating validation for {knowledge_id}: {e}")
                return False
    
    def create_from_patterns(
        self,
        patterns: List[SemanticPattern],
        description: str,
        pattern_type: str
    ) -> Optional[ProceduralKnowledge]:
        """
        Create procedural knowledge from a list of semantic patterns.
        
        This method analyzes semantic patterns from multiple skills to identify
        cross-skill generalizations. It validates that patterns come from enough
        different skills before creating procedural knowledge.
        
        Args:
            patterns: List of SemanticPattern objects that share a common insight
            description: Human-readable description of the generalization
            pattern_type: Category of the pattern (e.g., "timing", "personalization")
            
        Returns:
            Created ProceduralKnowledge if validation passes, None otherwise
            
        Example:
            If patterns from email-drip, social-post, and push-notification skills
            all show that morning sends perform better, this creates procedural
            knowledge capturing that timing insight.
        """
        with self._lock:
            if not patterns:
                logger.warning("Cannot create procedural knowledge from empty patterns")
                return None
            
            # Validate at least min_validating_skills different skills
            unique_skills = set(p.skill_name for p in patterns if p.skill_name)
            
            if len(unique_skills) < self._config.min_validating_skills:
                logger.info(
                    f"Not enough unique skills ({len(unique_skills)}) to create "
                    f"procedural knowledge. Minimum required: {self._config.min_validating_skills}"
                )
                return None
            
            # Extract applicable_skills from patterns
            applicable_skills = list(unique_skills)
            
            # Extract applicable_domains from patterns
            applicable_domains = list(set(
                p.domain.value if isinstance(p.domain, Domain) else p.domain
                for p in patterns
                if p.domain
            ))
            
            # Merge knowledge from pattern recommendations
            merged_knowledge: Dict[str, Any] = {}
            for pattern in patterns:
                if pattern.recommendation:
                    # Merge recommendations, later patterns override earlier ones
                    for key, value in pattern.recommendation.items():
                        if key not in merged_knowledge:
                            merged_knowledge[key] = value
                        elif isinstance(value, dict) and isinstance(merged_knowledge[key], dict):
                            merged_knowledge[key].update(value)
                        else:
                            merged_knowledge[key] = value
            
            # Build validating_skills with pattern confidence as accuracy
            validating_skills = {}
            for pattern in patterns:
                if pattern.skill_name:
                    # Use the pattern's confidence as initial accuracy
                    validating_skills[pattern.skill_name] = pattern.confidence
            
            # Calculate initial cross_skill_confidence as average pattern confidence
            if validating_skills:
                cross_skill_confidence = sum(validating_skills.values()) / len(validating_skills)
            else:
                cross_skill_confidence = 0.5
            
            # Check minimum confidence threshold
            if cross_skill_confidence < self._config.min_cross_skill_confidence:
                logger.info(
                    f"Cross-skill confidence ({cross_skill_confidence:.2f}) below minimum "
                    f"({self._config.min_cross_skill_confidence}). Not creating procedural knowledge."
                )
                return None
            
            # Collect source pattern IDs
            source_patterns = [p.pattern_id for p in patterns if p.pattern_id]
            
            # Create and store ProceduralKnowledge
            knowledge = ProceduralKnowledge(
                description=description,
                pattern_type=pattern_type,
                knowledge=merged_knowledge,
                applicable_skills=applicable_skills,
                applicable_domains=applicable_domains,
                validating_skills=validating_skills,
                cross_skill_confidence=cross_skill_confidence,
                source_patterns=source_patterns
            )
            
            try:
                self.store(knowledge)
                logger.info(
                    f"Created procedural knowledge {knowledge.knowledge_id}: "
                    f"{description[:50]}... with {len(applicable_skills)} skills, "
                    f"confidence={cross_skill_confidence:.2f}"
                )
                return knowledge
                
            except Exception as e:
                logger.error(f"Error storing created procedural knowledge: {e}")
                return None
    
    def decay_all(self) -> int:
        """
        Apply decay to all procedural knowledge that hasn't been reinforced.
        
        Procedural knowledge decays very slowly (decay_rate=0.995 by default)
        since it represents stable generalizations. This method is typically
        run periodically (e.g., daily) to gradually reduce confidence in
        knowledge that isn't being reinforced by validation.
        
        Returns:
            Number of knowledge entries that had decay applied
        """
        with self._lock:
            decayed_count = 0
            
            try:
                # Get all procedural knowledge
                if hasattr(self._firebase, "get_collection"):
                    docs = self._firebase.get_collection(
                        collection=self._collection_base
                    )
                else:
                    logger.warning("Firebase client missing get_collection method")
                    return 0
                
                if not docs:
                    return 0
                
                now = datetime.now(timezone.utc)
                
                for doc in docs:
                    knowledge = self._doc_to_knowledge(doc)
                    if knowledge is None:
                        continue
                    
                    # Calculate days since last update
                    try:
                        updated_dt = datetime.fromisoformat(
                            knowledge.updated_at.replace("Z", "+00:00")
                        )
                        days_since_update = (now - updated_dt).total_seconds() / 86400
                    except (ValueError, AttributeError):
                        days_since_update = 1.0
                    
                    # Apply decay: confidence *= decay_rate ^ days
                    decayed_confidence = knowledge.cross_skill_confidence * (
                        self._config.decay_rate ** days_since_update
                    )
                    decayed_confidence = max(0.0, min(1.0, decayed_confidence))
                    
                    # Only update if there's meaningful change
                    if abs(decayed_confidence - knowledge.cross_skill_confidence) > 0.001:
                        if hasattr(self._firebase, "update_document"):
                            self._firebase.update_document(
                                collection=self._collection_base,
                                doc_id=knowledge.knowledge_id,
                                data={
                                    "cross_skill_confidence": decayed_confidence,
                                    "updated_at": now.isoformat()
                                }
                            )
                            decayed_count += 1
                
                if decayed_count > 0:
                    logger.info(f"Applied decay to {decayed_count} procedural knowledge entries")
                    
            except Exception as e:
                logger.error(f"Error in decay_all: {e}")
            
            return decayed_count
    
    def _doc_to_knowledge(self, doc: Dict[str, Any]) -> Optional[ProceduralKnowledge]:
        """
        Convert a Firebase document to a ProceduralKnowledge object.
        
        Args:
            doc: Firebase document dictionary
            
        Returns:
            ProceduralKnowledge object or None if conversion fails
        """
        if not doc:
            return None
        
        try:
            # Handle _id from Firebase metadata
            knowledge_id = doc.get("knowledge_id") or doc.get("_id")
            if not knowledge_id:
                logger.warning("Document missing knowledge_id")
                return None
            
            return ProceduralKnowledge(
                knowledge_id=knowledge_id,
                description=doc.get("description", ""),
                pattern_type=doc.get("pattern_type", ""),
                knowledge=doc.get("knowledge", {}),
                applicable_skills=doc.get("applicable_skills", []),
                applicable_domains=doc.get("applicable_domains", []),
                validating_skills=doc.get("validating_skills", {}),
                cross_skill_confidence=doc.get("cross_skill_confidence", 0.5),
                source_patterns=doc.get("source_patterns", []),
                created_at=doc.get("created_at", datetime.now(timezone.utc).isoformat()),
                updated_at=doc.get("updated_at", datetime.now(timezone.utc).isoformat()),
            )
            
        except Exception as e:
            logger.error(f"Error converting document to procedural knowledge: {e}")
            return None
    
    def delete_knowledge(self, knowledge_id: str) -> bool:
        """
        Delete procedural knowledge from the store.
        
        Args:
            knowledge_id: The knowledge_id to delete
            
        Returns:
            True if deleted, False otherwise
        """
        with self._lock:
            try:
                if hasattr(self._firebase, "delete_document"):
                    self._firebase.delete_document(
                        collection=self._collection_base,
                        doc_id=knowledge_id
                    )
                    logger.debug(f"Deleted procedural knowledge {knowledge_id}")
                    return True
                else:
                    logger.warning("Firebase client missing delete_document method")
                    
            except Exception as e:
                logger.error(f"Error deleting knowledge {knowledge_id}: {e}")
            
            return False
    
    def count_knowledge(self) -> int:
        """
        Count total procedural knowledge entries.
        
        Returns:
            Knowledge entry count
        """
        with self._lock:
            try:
                if hasattr(self._firebase, "get_collection"):
                    docs = self._firebase.get_collection(
                        collection=self._collection_base
                    )
                    return len(docs) if docs else 0
                    
            except Exception as e:
                logger.error(f"Error counting knowledge: {e}")
            
            return 0


__all__ = [
    "ProceduralMemoryConfig",
    "ProceduralMemoryStore",
]
