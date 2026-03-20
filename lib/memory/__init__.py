"""Memory module compatibility layer.

The actual implementation is at lib/intelligence/memory/.
This module provides convenient imports.
"""

# Re-export from intelligence.memory using relative imports
from lib.intelligence.memory.semantic import (
    SemanticMemoryStore,
    SemanticMemoryConfig,
    SemanticSimilarityConfig,
    SemanticMemory,
)
from lib.intelligence.memory.episodic import (
    EpisodicMemoryStore,
    EpisodicMemoryConfig,
)
from lib.intelligence.memory.working import (
    WorkingMemory,
    WorkingMemoryConfig,
)
from lib.intelligence.memory.procedural import (
    ProceduralMemoryStore,
    ProceduralMemoryConfig,
)
from lib.intelligence.memory.consolidation import (
    MemoryConsolidationManager,
    ConsolidationConfig,
)

# Alias for backwards compatibility
MemoryConsolidator = MemoryConsolidationManager

__all__ = [
    # Semantic
    'SemanticMemoryStore',
    'SemanticMemoryConfig',
    'SemanticSimilarityConfig',
    'SemanticMemory',
    # Episodic
    'EpisodicMemoryStore',
    'EpisodicMemoryConfig',
    # Working
    'WorkingMemory',
    'WorkingMemoryConfig',
    # Procedural
    'ProceduralMemoryStore',
    'ProceduralMemoryConfig',
    # Consolidation
    'MemoryConsolidationManager',
    'MemoryConsolidator',  # Alias
    'ConsolidationConfig',
]
