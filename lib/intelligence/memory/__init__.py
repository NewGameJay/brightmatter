"""
Memory subsystem for MH1 Intelligence.

Provides different memory layers:
- Working Memory: Fast, session-scoped, volatile storage
- Episodic Memory: Persistent storage for prediction outcomes (Firebase-backed)
- Semantic Memory: Long-term pattern and knowledge storage (Firebase-backed, Bayesian learning)
- Procedural Memory: Cross-skill generalizations (Firebase-backed)

Semantic Memory also provides similarity search:
- SemanticMemoryStore: Firebase-backed with token-based and LLM-based similarity
- SemanticMemory: Lightweight local file storage for standalone usage
"""

from .episodic import EpisodicMemoryStore, EpisodicMemoryConfig
from .procedural import ProceduralMemoryStore, ProceduralMemoryConfig
from .semantic import (
    SemanticMemoryStore,
    SemanticMemoryConfig,
    SemanticSimilarityConfig,
    SemanticMemory,
)

__all__ = [
    "EpisodicMemoryStore",
    "EpisodicMemoryConfig",
    "ProceduralMemoryStore",
    "ProceduralMemoryConfig",
    "SemanticMemoryStore",
    "SemanticMemoryConfig",
    "SemanticSimilarityConfig",
    "SemanticMemory",
]
