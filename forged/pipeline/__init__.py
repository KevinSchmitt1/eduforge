"""Agentic pipeline package.

Public API (Phases 1–6):
  - PipelineState, PipelineStage: Core state schema
  - Location, LocationType: Issue location anchors
  - Evidence: Structured signal for routing decisions
  - RoutingDecision: Immutable audit trail entry
  - StageOutput: One stage's contribution to the pipeline
  - create_initial_state: Factory for fresh pipeline state
  - FailureCategory: Six deterministic failure categories
  - Classification: Immutable classification result
  - ExecutionReport: Structured executor output
  - GradeReport: Structured student grader output
  - classify: Deterministic priority-cascade classifier
  - Router: Deterministic routing engine
  - RoutingBudget: Per-stage attempt limits
  - RoutingRequest: Input to Router.route()
  - RoutingResult: Output of Router.route()
  - Agent: Abstract base class for all pipeline agents
  - AgentOutput: Immutable output descriptor
  - build_pipeline_graph: Assemble the LangGraph workflow
  - run_pipeline: Build and execute the pipeline end-to-end
"""

from .agents import Agent, AgentOutput, PlannerAgent
from .failure import (
    Classification,
    ExecutionReport,
    FailureCategory,
    GradeReport,
    classify,
)
from .graph import build_pipeline_graph, run_pipeline
from .router import (
    Router,
    RoutingBudget,
    RoutingRequest,
    RoutingResult,
)
from .state import (
    Evidence,
    Location,
    LocationType,
    PipelineStage,
    PipelineState,
    RoutingDecision,
    StageOutput,
    create_initial_state,
)

__all__ = [
    # State (Phase 1)
    "Evidence",
    "Location",
    "LocationType",
    "PipelineStage",
    "PipelineState",
    "RoutingDecision",
    "StageOutput",
    "create_initial_state",
    # Classification (Phase 2)
    "Classification",
    "ExecutionReport",
    "FailureCategory",
    "GradeReport",
    "classify",
    # Routing (Phase 3)
    "Router",
    "RoutingBudget",
    "RoutingRequest",
    "RoutingResult",
    # Agent protocol (Phase 4)
    "Agent",
    "AgentOutput",
    "PlannerAgent",
    # Graph assembly (Phase 6)
    "build_pipeline_graph",
    "run_pipeline",
]
