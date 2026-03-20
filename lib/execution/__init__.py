"""
MH1 Execution Engine

A deterministic execution engine that reads plan.json and executes nodes
according to the DAG, with state persistence, dependency resolution, and
executor abstraction.

Components:
- ExecutionEngine: Main orchestrator for plan execution
- ExecutionState: State management with persistence
- ContextLoader: Client context loading and filtering
- Executors: Pluggable execution backends (Claude, Sandbox)
- Validators: Output validation against schemas and expected files

Usage:
    from lib.execution import ExecutionEngine
    
    engine = ExecutionEngine()
    result = engine.execute("modules/my-module/plan.json")
    
    # Or resume a previous run
    result = engine.resume("modules/my-module/runs/run-20260203-143022")
"""

# Core state management
from lib.execution.state import ExecutionState, NodeState, DependencyResolver

# Context loading
from lib.execution.context import ContextLoader, NodeContext

# Validators
from lib.execution.output_validation import OutputValidator, PhaseManifestBuilder

# Retry and checkpoint
from lib.execution.retry import RetryPolicy, RetryExecutor, AdaptiveRetryPolicy
from lib.execution.checkpoint import CheckpointManager, CheckpointState

# Context validation
from lib.execution.context_validator import validate_required_context, ValidationResult

# Correction loop (AUTO_REFINE)
from lib.execution.correction_loop import (
    correction_loop,
    should_attempt_correction,
    CorrectionConfig,
    CorrectionResult,
)

# Executors
from lib.execution.executors.base import BaseExecutor, ExecutionResult
from lib.execution.executors.claude import ClaudeExecutor

# Main engine (import last to avoid circular imports)
from lib.execution.engine import ExecutionEngine, generate_run_id

__all__ = [
    # Engine
    "ExecutionEngine",
    "generate_run_id",
    # State
    "ExecutionState", 
    "NodeState",
    "DependencyResolver",
    # Context
    "ContextLoader",
    "NodeContext",
    # Validators
    "OutputValidator",
    "PhaseManifestBuilder",
    # Retry/Checkpoint
    "RetryPolicy",
    "RetryExecutor",
    "AdaptiveRetryPolicy",
    "CheckpointManager",
    "CheckpointState",
    # Context Validation
    "validate_required_context",
    "ValidationResult",
    # Correction Loop
    "correction_loop",
    "should_attempt_correction",
    "CorrectionConfig",
    "CorrectionResult",
    # Executors
    "BaseExecutor",
    "ExecutionResult",
    "ClaudeExecutor",
]

__version__ = "1.0.0"
