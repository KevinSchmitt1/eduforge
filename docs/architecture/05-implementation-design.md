# Eduforge Agentic Pipeline — Implementation Design

**For:** Building the core pipeline modules with clean architecture, testability, and maintainability in mind.

---

## Overview

This document specifies:
1. **Module structure** — where files live and their boundaries
2. **Type definitions** — state schema, failure classifications, routing decisions
3. **Dependency graph** — how modules import each other (zero circular imports)
4. **Agent interface** — standardized input/output contracts
5. **Testability patterns** — unit tests that don't need LangGraph or LLMs

---

## 1. File Structure

```
forged/
├── pipeline/
│   ├── __init__.py           # Public exports: State, classify(), route(), etc.
│   ├── state.py              # PipelineState schema + builders
│   ├── failure.py            # Failure classification types + classifier logic
│   ├── router.py             # Routing decisions + budget enforcement
│   ├── agents/
│   │   ├── __init__.py       # Agent protocol + base classes
│   │   ├── planner.py        # PlannerAgent
│   │   ├── code_author.py    # CodeAuthorAgent
│   │   ├── executor.py       # ExecutorAgent (wrapper around ExecutorStage)
│   │   ├── student.py        # StudentAgent (grader/reviewer)
│   │   └── reviser.py        # RevisorAgent (router + decision maker)
│   └── graph.py              # LangGraph assembly: nodes + conditional edges
└── (existing modules unchanged)
```

**Key principle:** `pipeline/` is a new package that encapsulates state, classification, routing, and agent contracts. It does NOT modify existing modules; it wraps them.

---

## 2. State Schema (`pipeline/state.py`)

### Core Types

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal
from enum import Enum
import uuid

# ─── Enums ───────────────────────────────────────────────────────

class PipelineStage(str, Enum):
    """Stages in the pipeline."""
    PLANNER = "planner"
    CODE_AUTHOR = "code_author"
    EXECUTOR = "executor"
    STUDENT = "student"
    REVISER = "reviser"


class LocationType(str, Enum):
    """Where a finding/issue is anchored."""
    CELL = "cell"
    SECTION = "section"
    LESSON_STRUCTURE = "lesson_structure"
    ARTIFACT = "artifact"
    GLOBAL = "global"


# ─── Value Objects ───────────────────────────────────────────────

@dataclass(frozen=True)
class Location:
    """Flexible anchor for an issue or finding.
    
    Examples:
      Location(type=LocationType.CELL, cell_index=5, label="lookup example")
      Location(type=LocationType.SECTION, label="Complexity discussion")
      Location(type=LocationType.GLOBAL)
    """
    type: LocationType
    cell_index: int | None = None
    label: str | None = None
    
    def __post_init__(self) -> None:
        """Validate that cell_index is only set for CELL types."""
        if self.type == LocationType.CELL and self.cell_index is None:
            raise ValueError("CELL location must have cell_index")
        if self.type != LocationType.CELL and self.cell_index is not None:
            raise ValueError(f"{self.type} location should not have cell_index")


@dataclass(frozen=True)
class Evidence:
    """A concrete signal that informed routing decisions.
    
    Immutable. Severity and scope let downstream agents understand the impact.
    """
    source: str  # "executor_report", "student_feedback", "reviewer_feedback", etc.
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW"]
    scope: Literal["plan", "code", "content", "structure", "unknown"]
    location: Location
    text: str  # The actual feedback or error message


@dataclass(frozen=True)
class RoutingDecision:
    """A single routing event in the audit trail.
    
    Immutable. Fully documents why and how a routing decision was made.
    """
    iteration: int
    from_stage: PipelineStage
    to_stage: PipelineStage | None  # None means "ACCEPTABLE" or "UNCLASSIFIABLE"
    classification: str  # "code_quality", "blocker_structure", "acceptable", etc.
    reason: str  # Human-readable explanation
    evidence: list[Evidence] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: str(uuid.uuid4()))  # Unique ID


@dataclass(frozen=True)
class StageOutput:
    """One stage's contribution to the pipeline.
    
    Immutable. Tracks what was produced and when.
    """
    stage: PipelineStage
    artifact_name: str  # Key to retrieve from ArtifactStore
    iteration: int
    data: dict | None = None  # Optional stage-specific metadata


# ─── Main State ──────────────────────────────────────────────────

@dataclass
class PipelineState:
    """
    The state object that flows through the LangGraph.
    
    INVARIANTS (enforced by builders, not constructors):
      - stage_attempts[s] >= 1 for any stage that has run
      - current_stage must be a valid PipelineStage
      - iteration >= 0
      - outputs must be chronologically ordered
      - no cycles in routing_log (no stage appears twice in immediate succession)
    
    MUTATION RULE:
      Never mutate this dataclass. Use `with_*` builders to create new instances.
    """
    run_id: str
    current_stage: PipelineStage
    iteration: int
    
    # Outputs from each stage
    outputs: list[StageOutput] = field(default_factory=list)
    
    # Budget tracking: stage_name -> attempt count
    stage_attempts: dict[str, int] = field(default_factory=dict)
    
    # Audit trail
    routing_log: list[RoutingDecision] = field(default_factory=list)
    
    # Exit condition
    is_terminal: bool = False
    terminal_reason: str | None = None
    
    def __post_init__(self) -> None:
        """Validate invariants."""
        if not isinstance(self.current_stage, PipelineStage):
            raise TypeError(f"current_stage must be PipelineStage, got {type(self.current_stage)}")
        if self.iteration < 0:
            raise ValueError(f"iteration must be >= 0, got {self.iteration}")

    # ─── Immutable builders ──────────────────────────────────

    def with_current_stage(self, stage: PipelineStage) -> PipelineState:
        """Return a new state with a different current stage."""
        return replace(self, current_stage=stage)

    def with_output(self, output: StageOutput) -> PipelineState:
        """Return a new state with an additional output.
        
        Preserves immutability; returns a fresh list.
        """
        new_outputs = self.outputs + [output]
        return replace(self, outputs=new_outputs)

    def with_routing_decision(self, decision: RoutingDecision) -> PipelineState:
        """Return a new state with a routing decision appended."""
        new_log = self.routing_log + [decision]
        new_iteration = self.iteration + 1
        return replace(self, routing_log=new_log, iteration=new_iteration)

    def with_attempt(self, stage: PipelineStage) -> PipelineState:
        """Increment the attempt count for a stage.
        
        Returns a new state with updated stage_attempts.
        """
        new_attempts = {**self.stage_attempts}
        new_attempts[stage.value] = new_attempts.get(stage.value, 0) + 1
        return replace(self, stage_attempts=new_attempts)

    def with_terminal(self, reason: str) -> PipelineState:
        """Mark this state as terminal (pipeline complete).
        
        Args:
            reason: One of "acceptable", "budget_exhausted", "unclassifiable"
        """
        return replace(self, is_terminal=True, terminal_reason=reason)

    def get_stage_attempt_count(self, stage: PipelineStage) -> int:
        """How many times has this stage been attempted?"""
        return self.stage_attempts.get(stage.value, 0)

    def last_routing_to_stage(self, stage: PipelineStage) -> RoutingDecision | None:
        """The most recent routing decision that sent it to this stage."""
        for decision in reversed(self.routing_log):
            if decision.to_stage == stage:
                return decision
        return None


# ─── Initialization ──────────────────────────────────────────────

def create_initial_state(run_id: str | None = None) -> PipelineState:
    """Create a fresh pipeline state.
    
    Args:
        run_id: Unique run identifier. If None, generates a UUID.
    
    Returns:
        A new PipelineState ready for the Planner to consume.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())
    
    return PipelineState(
        run_id=run_id,
        current_stage=PipelineStage.PLANNER,
        iteration=0,
    )
```

### State Schema Invariants

| Invariant | Why | Check |
|-----------|-----|-------|
| `stage_attempts[s] >= 1` for any s in routing_log | Budget tracking must be consistent | Router enforces before routing |
| `current_stage` is always valid | No silent invalid stages | `__post_init__` validation |
| `iteration >= 0` | Monotonic counter | `__post_init__` validation |
| No consecutive same-stage in routing_log | Avoid tight loops | Router enforces |
| Location constraints (cell_index consistency) | Prevent nonsensical feedback | Location `__post_init__` validation |

---

## 3. Failure Classification (`pipeline/failure.py`)

### Types

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import Evidence

# ─── Classification Categories ──────────────────────────────────

class FailureCategory(str, Enum):
    """
    Deterministic categories that classify what went wrong.
    
    Ordering matters: classification logic uses priority cascade (first match wins).
    """
    BLOCKER_STRUCTURE = "blocker_structure"      # Lesson structure is wrong (replan)
    CODE_QUALITY = "code_quality"                # Code doesn't run (recode)
    TEST_FAILURE = "test_failure"                # Code runs but output wrong (recode)
    CONTENT_QUALITY = "content_quality"          # Teaching is unclear (revise prose)
    ACCEPTABLE = "acceptable"                    # Good enough
    UNCLASSIFIABLE = "unclassifiable"            # Can't determine; hand to human


# ─── Classification Result ──────────────────────────────────────

@dataclass(frozen=True)
class Classification:
    """
    The output of failure classification logic.
    
    Immutable. Always includes the category and reasoning.
    """
    category: FailureCategory
    reason: str  # Why this category was chosen
    matched_signals: list[str] = field(default_factory=list)  # Debug: which signals matched


# ─── Signals (Input to Classification) ───────────────────────

@dataclass(frozen=True)
class ExecutionReport:
    """Structured output from the Executor stage."""
    ok: bool
    failed_cells: list[int] = field(default_factory=list)
    error_summary: str | None = None


@dataclass(frozen=True)
class GradeReport:
    """Structured output from the Student (grader) stage."""
    quality_score: float  # 0..100
    blockers: list[str] = field(default_factory=list)
    findings: list[Evidence] = field(default_factory=list)


# ─── Classifier Logic ────────────────────────────────────────

def classify(
    execution_report: ExecutionReport | None,
    grade_report: GradeReport | None,
    quality_threshold: float = 80.0,
) -> Classification:
    """
    Deterministic classification of what went wrong.
    
    Args:
        execution_report: Result of running the notebook (may be None if executor hasn't run)
        grade_report: Result of student grading (may be None)
        quality_threshold: Minimum quality_score to be ACCEPTABLE
    
    Returns:
        A Classification with category and reasoning.
    
    CLASSIFICATION LOGIC (Priority Cascade):
        1. Plan-scope BLOCKER? → BLOCKER_STRUCTURE
        2. Code failed to run? → CODE_QUALITY
        3. Output/test failed? → TEST_FAILURE
        4. Quality score too low? → CONTENT_QUALITY
        5. All good? → ACCEPTABLE
        6. Can't figure it out? → UNCLASSIFIABLE
    
    IMPORTANT: This is deterministic. Same inputs → same output, every time.
               No LLM variance, no randomness.
    """
    signals_matched: list[str] = []
    
    # Check 1: Plan-scope BLOCKER in findings
    if grade_report is not None:
        for finding in grade_report.findings:
            if (finding.severity == "BLOCKER" and 
                finding.scope in ("plan", "structure")):
                signals_matched.append(f"BLOCKER in findings: {finding.text[:50]}")
                return Classification(
                    category=FailureCategory.BLOCKER_STRUCTURE,
                    reason="Lesson structure has a blocker-level issue (concept ordering, prerequisites, etc.)",
                    matched_signals=signals_matched,
                )
    
    # Check 2: Code failed to run
    if execution_report is not None and not execution_report.ok:
        signals_matched.append(f"Execution failed: {execution_report.failed_cells}")
        return Classification(
            category=FailureCategory.CODE_QUALITY,
            reason=f"Code failed to run. Cells {execution_report.failed_cells} raised errors.",
            matched_signals=signals_matched,
        )
    
    # Check 3: Output/test failure (code runs but produces wrong result)
    if grade_report is not None:
        for finding in grade_report.findings:
            if finding.scope == "code" and finding.severity in ("HIGH", "BLOCKER"):
                signals_matched.append(f"High-severity code finding: {finding.text[:50]}")
                return Classification(
                    category=FailureCategory.TEST_FAILURE,
                    reason="Code runs but produces incorrect output.",
                    matched_signals=signals_matched,
                )
    
    # Check 4: Quality score too low
    if grade_report is not None:
        if grade_report.quality_score < quality_threshold:
            signals_matched.append(f"Quality score {grade_report.quality_score} < {quality_threshold}")
            return Classification(
                category=FailureCategory.CONTENT_QUALITY,
                reason=f"Quality score {grade_report.quality_score:.0f} is below threshold {quality_threshold}.",
                matched_signals=signals_matched,
            )
    
    # Check 5: All good
    if execution_report is not None and execution_report.ok:
        if grade_report is None or grade_report.quality_score >= quality_threshold:
            signals_matched.append("Execution OK and quality acceptable")
            return Classification(
                category=FailureCategory.ACCEPTABLE,
                reason="Code executed successfully and quality is acceptable.",
                matched_signals=signals_matched,
            )
    
    # Check 6: Can't figure it out
    signals_matched.append("No clear signals matched")
    return Classification(
        category=FailureCategory.UNCLASSIFIABLE,
        reason="Unable to classify the failure. Manual review required.",
        matched_signals=signals_matched,
    )
```

### Classification Logic Diagram

```
Input signals (execution_report, grade_report)
    ↓
[1] BLOCKER in plan/structure? → BLOCKER_STRUCTURE
    ↓ (no)
[2] Code didn't run? → CODE_QUALITY
    ↓ (no)
[3] Output wrong (code runs, result wrong)? → TEST_FAILURE
    ↓ (no)
[4] Quality score too low? → CONTENT_QUALITY
    ↓ (no)
[5] All good? → ACCEPTABLE
    ↓ (no)
[6] Default → UNCLASSIFIABLE
```

---

## 4. Routing Logic (`pipeline/router.py`)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .failure import FailureCategory, Classification
from .state import PipelineState, PipelineStage, RoutingDecision, Evidence

if TYPE_CHECKING:
    pass

# ─── Budget Configuration ────────────────────────────────────

@dataclass(frozen=True)
class RoutingBudget:
    """
    How many times we allow routing to each stage.
    
    Prevents infinite loops. ADJUST BASED ON REAL EXPERIENCE.
    """
    planner: int = 2           # Replan at most 2 times
    code_author: int = 3       # Recode at most 3 times
    student: int = 1           # Grade once (deterministic)
    reviser: int = 1           # Revise prose at most 1 time
    
    def can_route_to(self, stage: PipelineStage) -> bool:
        """Can we route to this stage given the budget?"""
        budget_map = {
            PipelineStage.PLANNER: self.planner,
            PipelineStage.CODE_AUTHOR: self.code_author,
            PipelineStage.STUDENT: self.student,
            PipelineStage.REVISER: self.reviser,
            PipelineStage.EXECUTOR: 999,  # Executor has no budget (always runs after code changes)
        }
        return budget_map.get(stage, 0) > 0


# ─── Routing Decision ────────────────────────────────────────

@dataclass(frozen=True)
class RoutingRequest:
    """
    Input to the router. Encapsulates what we know about the current state.
    """
    state: PipelineState
    classification: Classification
    evidence: list[Evidence]


@dataclass(frozen=True)
class RoutingResult:
    """
    Output of the router. Where to go next and why.
    """
    next_stage: PipelineStage | None  # None means pipeline complete
    should_terminate: bool
    reason: str
    routing_decision: RoutingDecision | None  # Audit trail entry (if routed)


# ─── Router Logic ────────────────────────────────────────────

class Router:
    """
    Deterministic routing: classification + budget → next stage.
    
    INVARIANTS:
      - Same state + classification → same result every time
      - Routing respects budgets (never sends to a stage that's exhausted)
      - Always returns a valid result
    """
    
    def __init__(self, budget: RoutingBudget | None = None):
        self.budget = budget or RoutingBudget()
    
    def route(self, request: RoutingRequest) -> RoutingResult:
        """
        Route a notebook based on its classification.
        
        Args:
            request: Current state + classification + evidence
        
        Returns:
            A RoutingResult describing the next stage (or termination).
        
        ROUTING TABLE:
            ACCEPTABLE → TERMINATE (done)
            UNCLASSIFIABLE → TERMINATE (manual review needed)
            BLOCKER_STRUCTURE → PLANNER (if budget allows, else TERMINATE)
            CODE_QUALITY → CODE_AUTHOR (if budget allows, else TERMINATE)
            TEST_FAILURE → CODE_AUTHOR (if budget allows, else TERMINATE)
            CONTENT_QUALITY → REVISER (if budget allows, else TERMINATE)
        """
        classification = request.classification
        state = request.state
        
        # Terminal cases (no more routing)
        if classification.category == FailureCategory.ACCEPTABLE:
            return RoutingResult(
                next_stage=None,
                should_terminate=True,
                reason=f"Notebook is acceptable. {classification.reason}",
                routing_decision=None,
            )
        
        if classification.category == FailureCategory.UNCLASSIFIABLE:
            return RoutingResult(
                next_stage=None,
                should_terminate=True,
                reason=f"Unable to classify the issue. Manual review required.",
                routing_decision=None,
            )
        
        # Non-terminal cases: determine target stage and check budget
        target_stage: PipelineStage | None = None
        reason_if_cant_route: str | None = None
        
        if classification.category == FailureCategory.BLOCKER_STRUCTURE:
            target_stage = PipelineStage.PLANNER
            reason_if_cant_route = "Lesson structure needs revision (replan), but planner budget exhausted."
        
        elif classification.category == FailureCategory.CODE_QUALITY:
            target_stage = PipelineStage.CODE_AUTHOR
            reason_if_cant_route = "Code needs fixing, but code author budget exhausted."
        
        elif classification.category == FailureCategory.TEST_FAILURE:
            target_stage = PipelineStage.CODE_AUTHOR
            reason_if_cant_route = "Code output is wrong, but code author budget exhausted."
        
        elif classification.category == FailureCategory.CONTENT_QUALITY:
            target_stage = PipelineStage.REVISER
            reason_if_cant_route = "Content needs revision, but reviser budget exhausted."
        
        # Check if we can route to target
        assert target_stage is not None, f"Unhandled classification: {classification.category}"
        
        attempt_count = state.get_stage_attempt_count(target_stage)
        budget_for_stage = getattr(self.budget, target_stage.value)
        
        if attempt_count >= budget_for_stage:
            # Budget exhausted; terminate
            return RoutingResult(
                next_stage=None,
                should_terminate=True,
                reason=reason_if_cant_route or f"Budget exhausted for {target_stage.value}.",
                routing_decision=None,
            )
        
        # Can route; build the decision
        decision = RoutingDecision(
            iteration=state.iteration,
            from_stage=state.current_stage,
            to_stage=target_stage,
            classification=classification.category.value,
            reason=classification.reason,
            evidence=request.evidence,
        )
        
        return RoutingResult(
            next_stage=target_stage,
            should_terminate=False,
            reason=f"Routing to {target_stage.value}: {classification.reason}",
            routing_decision=decision,
        )
```

---

## 5. Agent Interface (`pipeline/agents/__init__.py`)

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

from ..state import PipelineState

if TYPE_CHECKING:
    from ..artifacts import ArtifactStore

# ─── Agent Protocol ─────────────────────────────────────────

T = TypeVar("T")  # Output type


class Agent(ABC, Generic[T]):
    """
    Base class for all pipeline agents.
    
    CONTRACT:
      - Agent is initialized with configuration including personas_dir
      - Agent loads its persona from personas/*.md during __init__
      - Agent.run(state, store) is called by LangGraph
      - Agent MUST NOT mutate state
      - Agent MUST return a new state with outputs added
      - Agent MUST handle errors gracefully (catch, log, update state)
    
    IMPORTANT: Agents are pure functions in LangGraph terms.
               Input (state) → processing → Output (new state).
               No side effects except artifact writes.
    
    PERSONA INTEGRATION:
      - Each agent loads a persona file (e.g., personas/planner.md)
      - Persona becomes the system message for LLM calls
      - Agent constructs user message from current state
      - LLM sees: [system: persona], [user: context from state]
    """
    
    def __init__(self, personas_dir: Path | None = None):
        """
        Initialize agent with persona loading.
        
        Args:
            personas_dir: Path to personas directory. If None, defaults to "personas".
        """
        if personas_dir is None:
            personas_dir = Path("personas")
        self.personas_dir = Path(personas_dir)
        self.persona = self._load_persona()
    
    @abstractmethod
    def _load_persona(self) -> str:
        """
        Load this agent's persona from file.
        
        Each concrete agent implements this to load personas/{name}.md.
        Returns the full text of the persona file.
        
        Example:
            def _load_persona(self) -> str:
                path = self.personas_dir / "planner.md"
                return path.read_text()
        """
        pass
    
    @abstractmethod
    async def run(
        self,
        state: PipelineState,
        store: ArtifactStore,
    ) -> PipelineState:
        """
        Run this agent and return the updated state.
        
        Args:
            state: Current pipeline state (READ ONLY)
            store: Artifact store for reading/writing (side effects OK here)
        
        Returns:
            A new PipelineState with this agent's output added.
        
        CONTRACT: Never mutate the input state. Always return a new state.
                 Use state.with_output(), state.with_current_stage(), etc.
        
        PATTERN:
            1. Build user message from state context
            2. Call LLM with:
               - system message: self.persona
               - user message: context from state
            3. Parse response
            4. Write artifact to store
            5. Return state.with_output(StageOutput(...))
        """
        pass
    
    @abstractmethod
    def next_stage(self) -> PipelineStage | None:
        """
        What stage should follow this one?
        
        Returns None if this is a terminal stage (Reviser).
        Typically, agents return the next hardcoded stage (e.g., CodeAuthor → Executor).
        
        For Reviser, return None; LangGraph's conditional edge will handle routing.
        """
        pass


# ─── Standard Return Type ────────────────────────────────────

@dataclass(frozen=True)
class AgentOutput:
    """
    Standardized output shape for agents.
    
    Some agents (Executor, Student) produce structured reports.
    Others (Planner, CodeAuthor) produce artifacts (notebooks, markdown).
    """
    stage_name: str
    artifact_name: str  # Key to retrieve from ArtifactStore
    artifact_kind: str  # "notebook", "markdown", "json", etc.
    metadata: dict | None = None  # Stage-specific metadata
```

### Individual Agent Signatures

```python
# ─── Planner Agent ────────────────────────────────────────────

class PlannerAgent(Agent[AgentOutput]):
    """Generates a lesson plan from the topic spec.
    
    Loads persona from personas/planner.md
    """
    
    def _load_persona(self) -> str:
        """Load planner persona from file."""
        path = self.personas_dir / "planner.md"
        return path.read_text()
    
    def _build_user_prompt(self, state: PipelineState, store: ArtifactStore) -> str:
        """Construct the user message from state.
        
        Reads the topic brief and learner profile from artifacts,
        then formats them as the user message for the LLM.
        
        Returns:
            The full user prompt ready to send to LLM.
        """
        # Retrieve brief and profile from store
        # (Exact keys depend on how seed inputs are stored)
        brief = store.read("topic_brief.md")  # or similar
        profile = store.read("learner_profile.md")  # or similar
        
        return f"""
Topic Brief:
{brief}

Target Learner Profile:
{profile}

Please create a concise lesson plan following the structure in your instructions.
"""
    
    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        """
        Inputs from state:
          - Artifacts: topic brief, learner profile (from seed inputs)
        
        Process:
          - Build user message from state context
          - Call LLM with system=self.persona, user=context
          - Parse and validate the output
        
        Outputs:
          - Artifact "lesson_plan.md"
          - Update state.current_stage → CODE_AUTHOR
          - Update state.outputs → add StageOutput(stage=PLANNER, artifact_name=...)
        
        Returns:
          A new state ready for CodeAuthor.
        """
        user_message = self._build_user_prompt(state, store)
        
        # Call LLM with persona as system message
        response = await self.llm.ainvoke([
            {"role": "system", "content": self.persona},
            {"role": "user", "content": user_message},
        ])
        
        plan_text = response.content
        
        # Write artifact
        store.write("lesson_plan.md", plan_text)
        
        # Return new state with output
        output = StageOutput(
            stage=PipelineStage.PLANNER,
            artifact_name="lesson_plan.md",
            iteration=state.iteration,
        )
        
        return state.with_output(output).with_current_stage(PipelineStage.CODE_AUTHOR)
    
    def next_stage(self) -> PipelineStage:
        return PipelineStage.CODE_AUTHOR


# ─── Code Author Agent ───────────────────────────────────────

class CodeAuthorAgent(Agent[AgentOutput]):
    """Generates a Jupyter notebook from a lesson plan.
    
    Loads persona from personas/code_author.md
    """
    
    def _load_persona(self) -> str:
        """Load code author persona from file."""
        path = self.personas_dir / "code_author.md"
        return path.read_text()
    
    def _build_user_prompt(self, state: PipelineState, store: ArtifactStore) -> str:
        """Construct the user message from state.
        
        Reads the lesson plan. If re-coding (routing_log has feedback),
        includes that feedback in the prompt.
        
        Returns:
            The full user prompt ready to send to LLM.
        """
        # Read lesson plan from latest output
        plan = store.read("lesson_plan.md")
        
        prompt = f"""
Lesson Plan:
{plan}

Please write a Jupyter notebook that implements this lesson plan. 
Output the notebook as valid JSON in the correct Jupyter format.
"""
        
        # If this is a re-code (feedback from previous attempts), include it
        if len(state.routing_log) > 0:
            last_routing = state.routing_log[-1]
            if last_routing.evidence:
                feedback = "\n".join([e.text for e in last_routing.evidence])
                prompt += f"\n\nFeedback from previous attempt:\n{feedback}\n\nPlease fix these issues."
        
        return prompt
    
    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        """
        Inputs:
          - Lesson plan (previous CodeAuthor or Planner output)
          - Student feedback (if re-coding: from state.routing_log)
        
        Process:
          - Build user message (plan + feedback if re-coding)
          - Call LLM with system=self.persona, user=context
          - Parse cell JSON
          - Validate notebook structure
        
        Outputs:
          - Artifact "lesson_notebook.ipynb"
          - Update state.current_stage → EXECUTOR
        
        Returns:
          A new state ready for Executor.
        """
        user_message = self._build_user_prompt(state, store)
        
        # Call LLM with persona as system message
        response = await self.llm.ainvoke([
            {"role": "system", "content": self.persona},
            {"role": "user", "content": user_message},
        ])
        
        notebook_json = response.content
        
        # Validate and parse (or fail gracefully)
        try:
            parsed = json.loads(notebook_json)
            # TODO: validate notebook structure
        except json.JSONDecodeError as e:
            logger.error(f"CodeAuthor failed to parse notebook JSON: {e}")
            return state.with_terminal(f"CodeAuthor JSON parsing failed: {e}")
        
        # Write artifact
        store.write("lesson_notebook.ipynb", notebook_json)
        
        # Return new state with output
        output = StageOutput(
            stage=PipelineStage.CODE_AUTHOR,
            artifact_name="lesson_notebook.ipynb",
            iteration=state.iteration,
        )
        
        return state.with_output(output).with_current_stage(PipelineStage.EXECUTOR)
    
    def next_stage(self) -> PipelineStage:
        return PipelineStage.EXECUTOR


# ─── Executor Agent ──────────────────────────────────────────

class ExecutorAgent(Agent[AgentOutput]):
    """
    Wrapper around ExecutorStage. Runs the notebook.
    
    (This is mostly a thin wrapper; ExecutorStage already does the real work.)
    No persona needed; deterministic execution.
    """
    
    def _load_persona(self) -> str:
        """Executor doesn't use personas; return empty."""
        return ""
    
    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        """
        Inputs:
          - Latest notebook artifact
        
        Process:
          - Delegate to ExecutorStage.run()
          - Parse execution report
        
        Outputs:
          - Artifact "execution_report.json"
          - Store the executed notebook with outputs
          - Update state.current_stage → STUDENT
        
        Returns:
          A new state ready for Student.
        """
        # TODO: Delegate to ExecutorStage
        pass
    
    def next_stage(self) -> PipelineStage:
        return PipelineStage.STUDENT


# ─── Student Agent ───────────────────────────────────────────

class StudentAgent(Agent[AgentOutput]):
    """
    Grades the notebook: runs it, checks outputs, produces findings.
    
    Loads persona from personas/student.md
    """
    
    def _load_persona(self) -> str:
        """Load student persona from file."""
        path = self.personas_dir / "student.md"
        return path.read_text()
    
    def _build_user_prompt(self, state: PipelineState, store: ArtifactStore) -> str:
        """Construct the user message from state.
        
        Reads executed notebook and learning objectives, formats for LLM grading.
        """
        # Read executed notebook and objectives
        notebook = store.read("lesson_notebook_executed.ipynb")
        objectives = store.read("learning_objectives.md")
        
        return f"""
Learning Objectives:
{objectives}

Executed Notebook:
{notebook}

Please grade this notebook. Check if outputs demonstrate the learning objectives.
Identify any issues with clarity, completeness, or correctness.
"""
    
    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        """
        Inputs:
          - Executed notebook (with outputs)
          - Expected learning objectives
        
        Process:
          - Build user message from notebook + objectives
          - Call LLM with system=self.persona, user=context
          - Parse response to extract quality score and findings
          - Produce GradeReport
        
        Outputs:
          - Artifact "student_grade_report.json"
          - Update state.current_stage → REVISER
        
        Returns:
          A new state ready for Reviser (the router).
        """
        user_message = self._build_user_prompt(state, store)
        
        # Call LLM with persona as system message
        response = await self.llm.ainvoke([
            {"role": "system", "content": self.persona},
            {"role": "user", "content": user_message},
        ])
        
        # Parse response into GradeReport
        # (Format depends on what student.md instructs)
        grade_report = self._parse_grade_report(response.content)
        
        # Write artifact
        store.write("student_grade_report.json", json.dumps(grade_report.__dict__))
        
        # Return new state with output
        output = StageOutput(
            stage=PipelineStage.STUDENT,
            artifact_name="student_grade_report.json",
            iteration=state.iteration,
        )
        
        return state.with_output(output).with_current_stage(PipelineStage.REVISER)
    
    def next_stage(self) -> PipelineStage | None:
        return None  # Reviser will route


# ─── Reviser Agent (The Router) ──────────────────────────────

class RevisorAgent(Agent[AgentOutput]):
    """
    The intelligent router. Reads state + reports, classifies failures, routes.
    
    Loads persona from personas/reviser.md
    This is where the agentic intelligence lives: deterministic diagnosis + routing.
    """
    
    def _load_persona(self) -> str:
        """Load reviser persona from file."""
        path = self.personas_dir / "reviser.md"
        return path.read_text()
    
    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        """
        Inputs:
          - Full state (including routing_log)
          - Execution report
          - Grade report
        
        Process:
          - Read execution_report.json
          - Read student_grade_report.json
          - Call classify() to categorize the failure
          - Call route() to determine next stage
          - Build RoutingDecision with evidence
          - Update state.current_stage and routing_log
        
        Returns:
          A new state ready for the next stage (or terminal if routing_decision.next_stage is None).
        
        NOTE: Reviser doesn't produce an artifact (no notebook change).
              It only updates state.routing_log and state.current_stage.
        """
        # Read reports from store
        exec_report_json = store.read("execution_report.json")
        grade_report_json = store.read("student_grade_report.json")
        
        exec_report = json.loads(exec_report_json)
        grade_report = json.loads(grade_report_json)
        
        # Classify the failure (deterministic)
        classification = classify(
            execution_report=ExecutionReport(**exec_report),
            grade_report=GradeReport(**grade_report),
        )
        
        # Build evidence list
        evidence = [Evidence(**e) for e in grade_report.get("findings", [])]
        
        # Route (deterministic)
        router = Router()
        routing_result = router.route(RoutingRequest(
            state=state,
            classification=classification,
            evidence=evidence,
        ))
        
        # Update state with routing decision
        if routing_result.routing_decision:
            new_state = state.with_routing_decision(routing_result.routing_decision)
        else:
            # Terminal case
            new_state = state.with_terminal(routing_result.reason)
        
        return new_state
    
    def next_stage(self) -> PipelineStage | None:
        return None  # The state determines the next stage, not this agent
```

---

## 6. Persona Integration

### The Key Principle

**Personas are prompts (content). Agents are orchestrators (logic).**

- **Personas** live in `personas/*.md` files — they are the single source of truth for what each role should do, how to think, and what output format to produce. Easy to edit, no code changes needed.
- **Agents** are Python classes that load personas at init time, construct user messages from pipeline state, call the LLM, and parse responses. They orchestrate the workflow but don't repeat persona instructions.

This separation means:
1. Persona authors (domain experts) can refine instructions without touching code
2. Agents stay focused on pipeline plumbing (state management, error handling, artifact I/O)
3. The same persona can be tested, versioned, and audited independently

### Loading Flow

Each agent follows this pattern:

```
1. __init__(personas_dir)
   └─ Load persona file → self.persona (full text)

2. run(state, store)
   ├─ Build user message from state context
   │  (e.g., retrieve brief + profile for Planner)
   ├─ Call LLM with:
   │  ├─ system message: self.persona
   │  └─ user message: context from state
   ├─ Parse response
   └─ Write artifact to store
        └─ Return state.with_output(...)
```

### Example: PlannerAgent

```python
class PlannerAgent(Agent[AgentOutput]):
    def _load_persona(self) -> str:
        """Load personas/planner.md"""
        path = self.personas_dir / "planner.md"
        return path.read_text()
    
    def _build_user_prompt(self, state: PipelineState, store: ArtifactStore) -> str:
        """Format brief + profile from artifacts as user message."""
        brief = store.read("topic_brief.md")
        profile = store.read("learner_profile.md")
        return f"Topic Brief:\n{brief}\n\nLearner Profile:\n{profile}"
    
    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        """Planner's main logic."""
        user_message = self._build_user_prompt(state, store)
        
        # LLM sees the system message (persona) + user message (context)
        response = await self.llm.ainvoke([
            {"role": "system", "content": self.persona},          # From personas/planner.md
            {"role": "user", "content": user_message},            # From state/artifacts
        ])
        
        plan_text = response.content
        store.write("lesson_plan.md", plan_text)
        
        output = StageOutput(
            stage=PipelineStage.PLANNER,
            artifact_name="lesson_plan.md",
            iteration=state.iteration,
        )
        return state.with_output(output).with_current_stage(PipelineStage.CODE_AUTHOR)
```

### Persona Contract

Each persona file should state:

1. **Role and constraints** (e.g., "You are the Lesson Planner. Read the profile first — it is the ONLY source of who this lesson is for.")
2. **Inputs** (what to read/expect from the user message)
3. **Output format** (exact structure, markdown sections, JSON schema, etc.)
4. **Tone and style** (e.g., "be concrete", "avoid assumptions")

**Personas are NOT executable code.** They are instructions. Agents parse the responses and handle edge cases.

### File Structure

```
personas/
├── planner.md          # "Generates a lesson plan"
├── code_author.md      # "Writes a Jupyter notebook"
├── student.md          # "Grades the notebook"
├── reviser.md          # "Routes to next stage (deterministic diagnosis)"
└── reviewer.md         # Optional: additional feedback loop (not yet in pipeline)
```

### Testing Personas

Because personas are separate from code:

1. **Manual testing**: Paste persona + context into Claude, check output quality
2. **Automated testing**: Mock LLM responses, verify agent parsing is correct
3. **Versioning**: Keep old personas in a `personas/archive/` if experimentation happens
4. **A/B testing**: Swap personas at init time to compare agent behavior

---

## 7. LangGraph Wiring (`pipeline/graph.py`)

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import StateGraph, START, END

from .state import PipelineState, PipelineStage
from .agents.planner import PlannerAgent
from .agents.code_author import CodeAuthorAgent
from .agents.executor import ExecutorAgent
from .agents.student import StudentAgent
from .agents.reviser import RevisorAgent

if TYPE_CHECKING:
    from .artifacts import ArtifactStore


def build_pipeline_graph(store: ArtifactStore, personas_dir: Path | None = None) -> StateGraph:
    """
    Assemble the LangGraph workflow.
    
    Args:
        store: ArtifactStore for reading/writing artifacts
        personas_dir: Path to personas directory. If None, defaults to "personas".
    
    Nodes:
      - START → planner
      - planner → code_author
      - code_author → executor
      - executor → student
      - student → reviser
      - reviser → (routing decision: back to planner/code_author/reviser, or END)
    
    Conditional edges:
      - reviser routes based on routing_decision.next_stage
      - If routing_decision.next_stage is None → END
      - Else → the specified stage
    
    PERSONAS:
      - Each agent loads its persona from personas_dir at initialization.
      - Personas are passed as system messages to the LLM.
    """
    
    if personas_dir is None:
        personas_dir = Path("personas")
    
    graph = StateGraph(PipelineState)
    
    # Initialize agents with personas_dir
    # Each agent loads its persona during __init__
    planner = PlannerAgent(personas_dir=personas_dir)
    code_author = CodeAuthorAgent(personas_dir=personas_dir)
    executor = ExecutorAgent(personas_dir=personas_dir)
    student = StudentAgent(personas_dir=personas_dir)
    revisor = RevisorAgent(personas_dir=personas_dir)
    
    # ─── Define nodes ───────────────────────────────────────
    
    # Each node wraps the agent and passes store
    async def planner_node(state: PipelineState) -> PipelineState:
        return await planner.run(state, store)
    
    async def code_author_node(state: PipelineState) -> PipelineState:
        return await code_author.run(state, store)
    
    async def executor_node(state: PipelineState) -> PipelineState:
        return await executor.run(state, store)
    
    async def student_node(state: PipelineState) -> PipelineState:
        return await student.run(state, store)
    
    async def revisor_node(state: PipelineState) -> PipelineState:
        return await revisor.run(state, store)
    
    # Add nodes to graph
    graph.add_node("planner", planner_node)
    graph.add_node("code_author", code_author_node)
    graph.add_node("executor", executor_node)
    graph.add_node("student", student_node)
    graph.add_node("revisor", revisor_node)
    
    # ─── Define edges (routing) ──────────────────────────────
    
    # Linear path until reviser
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "code_author")
    graph.add_edge("code_author", "executor")
    graph.add_edge("executor", "student")
    graph.add_edge("student", "revisor")
    
    # Reviser routes conditionally
    def revisor_route(state: PipelineState) -> str:
        """
        Determine which node to go to next based on routing decision.
        
        Returns:
          - "planner", "code_author", "reviser" → route back
          - "__end__" → terminate pipeline
        """
        if state.is_terminal:
            return END
        
        # Check routing_log to see where reviser routed us
        if not state.routing_log:
            return END  # No routing log? Terminal
        
        last_routing = state.routing_log[-1]
        
        if last_routing.to_stage is None:
            return END
        
        return last_routing.to_stage.value
    
    graph.add_conditional_edges(
        "revisor",
        revisor_route,
        {
            "planner": "planner",
            "code_author": "code_author",
            "reviser": "revisor",
            END: END,
        }
    )
    
    return graph.compile()
```

---

## 8. Dependencies and Imports Strategy

### Dependency Graph (Acyclic)

```
stdlib, pydantic, langgraph
    ↓
state.py                      (schemas, immutable data)
    ↓
failure.py, router.py         (classification & routing logic)
    ↓
agents/__init__.py            (abstract base)
    ↓
agents/planner.py
agents/code_author.py
agents/executor.py
agents/student.py
agents/reviser.py             (concrete agents)
    ↓
graph.py                       (LangGraph assembly)
    ↓
orchestrator                   (existing, uses pipeline)
```

**Key principle:** Lower levels never import higher levels. State is at the bottom (no dependencies except stdlib). Graph is at the top (imports everything).

### Runtime Dependencies: Personas Directory

The `personas/` directory is **loaded at runtime**, not imported as Python modules:

```python
# agents/__init__.py
def _load_persona(self) -> str:
    """Load persona from file at runtime."""
    path = self.personas_dir / "planner.md"
    return path.read_text()  # ← File I/O, not import
```

This means:
- Personas are **content files**, not code
- They can be edited without touching Python
- Path must be correct at runtime (see `build_pipeline_graph(personas_dir=...)`).
- Missing persona files will raise `FileNotFoundError` at agent init time (fail fast)

### Import Hygiene

```python
# GOOD
from .state import PipelineState, PipelineStage
from .failure import FailureCategory, classify
from .router import Router, RoutingRequest

# BAD (circular)
from .graph import build_pipeline_graph  # Don't do this in lower modules

# ALSO BAD (overly specific)
from forged.pipeline.state import PipelineState, PipelineStage, StageOutput, Location
# Instead:
from forged.pipeline.state import PipelineState, PipelineStage
from forged.pipeline import Location, StageOutput  # Via __init__.py
```

### Public Exports (`pipeline/__init__.py`)

```python
"""
The pipeline package: state, classification, routing, and agents for the agentic workflow.

Public API:
  - PipelineState, PipelineStage: State schema
  - FailureCategory: Failure classifications
  - classify(), route(): Core logic
  - Agent: Base class for all agents
  - build_pipeline_graph(): LangGraph wiring
"""

from .state import (
    PipelineState,
    PipelineStage,
    Location,
    LocationType,
    Evidence,
    RoutingDecision,
    StageOutput,
    create_initial_state,
)
from .failure import (
    FailureCategory,
    Classification,
    ExecutionReport,
    GradeReport,
    classify,
)
from .router import (
    Router,
    RoutingBudget,
    RoutingRequest,
    RoutingResult,
)
from .agents import Agent, AgentOutput
from .graph import build_pipeline_graph

__all__ = [
    # State
    "PipelineState",
    "PipelineStage",
    "Location",
    "LocationType",
    "Evidence",
    "RoutingDecision",
    "StageOutput",
    "create_initial_state",
    # Classification
    "FailureCategory",
    "Classification",
    "ExecutionReport",
    "GradeReport",
    "classify",
    # Routing
    "Router",
    "RoutingBudget",
    "RoutingRequest",
    "RoutingResult",
    # Agents
    "Agent",
    "AgentOutput",
    # Graph
    "build_pipeline_graph",
]
```

---

## 9. Pitfalls to Avoid

### 1. **Mutation Creeping In**

**BAD:**
```python
def revise(state: PipelineState) -> None:
    state.routing_log.append(decision)  # Mutating!
    state.current_stage = PipelineStage.PLANNER  # Mutating!
```

**GOOD:**
```python
def revise(state: PipelineState) -> PipelineState:
    new_state = state.with_routing_decision(decision)
    return new_state.with_current_stage(PipelineStage.PLANNER)
```

### 2. **Circular Imports**

**BAD:**
```python
# state.py
from .router import Router  # ← state.py importing router

# router.py
from .state import PipelineState  # ← router importing state
# NOW IT'S CIRCULAR
```

**GOOD:**
```python
# state.py → no imports of router, graph, or agents

# router.py → imports from state only
# graph.py → imports from state, failure, router, agents

# Ordering: state → failure, router → agents → graph
```

### 3. **LLM Variance Creeping Into Classification**

**BAD:**
```python
def classify(execution_report, grade_report):
    # Don't call an LLM here!
    # response = llm.invoke("what went wrong?")
    # This would break determinism and audit trails.
    pass
```

**GOOD:**
```python
def classify(execution_report, grade_report):
    # Read concrete signals only.
    # If execution_report.ok is False, it's CODE_QUALITY.
    # No guessing, no LLM calls.
    pass
```

### 4. **Deep Nesting in Classification Logic**

**BAD:**
```python
def classify(execution_report, grade_report):
    if execution_report is not None:
        if not execution_report.ok:
            if execution_report.failed_cells:
                if len(execution_report.failed_cells) > 1:
                    return ...  # Too many levels
```

**GOOD:**
```python
def classify(execution_report, grade_report):
    # Flat priority cascade using early returns
    if execution_report is not None and not execution_report.ok:
        return Classification(category=FailureCategory.CODE_QUALITY, ...)
    # Continue to next check
```

### 5. **Forgetting Budget Enforcement**

**BAD:**
```python
def route(state: PipelineState, classification: Classification) -> PipelineStage:
    if classification.category == FailureCategory.CODE_QUALITY:
        return PipelineStage.CODE_AUTHOR  # What if budget is exhausted?
```

**GOOD:**
```python
def route(state: PipelineState, classification: Classification) -> RoutingResult:
    target = PipelineStage.CODE_AUTHOR
    if state.get_stage_attempt_count(target) >= self.budget.code_author:
        return RoutingResult(next_stage=None, should_terminate=True, reason="Budget exhausted")
    return RoutingResult(next_stage=target, should_terminate=False, ...)
```

### 6. **Loose Evidence Tracking**

**BAD:**
```python
# Routing decision made, but evidence is a string. Hard to audit.
routing_decision = {
    "to_stage": "code_author",
    "reason": "code is bad",  # ← Vague
}
```

**GOOD:**
```python
# Evidence is structured, traceable, and scope-labeled
routing_decision = RoutingDecision(
    to_stage=PipelineStage.CODE_AUTHOR,
    evidence=[
        Evidence(
            source="executor_report",
            severity="BLOCKER",
            scope="code",
            location=Location(type=LocationType.CELL, cell_index=3),
            text="Cell 3 raised NameError: name 'x' is not defined",
        ),
    ],
    reason="Code execution failed; cells [3] raised errors.",
)
```

### 7. **Async/Await Confusion in Agents**

**BAD:**
```python
class PlannerAgent(Agent):
    async def run(self, state, store):
        # But then you call sync functions without await
        response = self.llm.invoke(prompt)  # Might hang or fail silently
```

**GOOD:**
```python
class PlannerAgent(Agent):
    async def run(self, state, store):
        response = await self.llm.ainvoke(prompt)  # Async all the way
        return state.with_output(StageOutput(...))
```

### 8. **Missing Error Handling in Agents**

**BAD:**
```python
async def run(self, state, store):
    response = await self.llm.ainvoke(prompt)
    parsed = json.loads(response.content)  # What if it fails?
    return state.with_output(...)
```

**GOOD:**
```python
async def run(self, state, store):
    try:
        response = await self.llm.ainvoke(prompt)
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Agent failed: {e}")
        return state.with_terminal(f"Agent error: {e}")
    
    return state.with_output(...)
```

### 9. **Persona Mismatch: Hardcoding Prompts in Code**

**BAD:**
```python
class PlannerAgent(Agent):
    async def run(self, state, store):
        # Prompt is hardcoded in Python — can't edit without code changes!
        prompt = """You are a lesson planner. Write a plan for..."""
        response = await self.llm.ainvoke(prompt)
        return state.with_output(...)
```

**GOOD:**
```python
class PlannerAgent(Agent):
    def _load_persona(self) -> str:
        """Load personas/planner.md at init time."""
        path = self.personas_dir / "planner.md"
        return path.read_text()
    
    async def run(self, state, store):
        # Persona is loaded from file; user message from state context
        user_message = self._build_user_prompt(state, store)
        response = await self.llm.ainvoke([
            {"role": "system", "content": self.persona},
            {"role": "user", "content": user_message},
        ])
        return state.with_output(...)
```

**Why:** Personas are content, not code. They should be editable without touching Python.

### 10. **Missing Persona File**

**BAD:**
```python
# If personas/planner.md doesn't exist, this fails at runtime (during run()).
class PlannerAgent(Agent):
    async def run(self, state, store):
        # self.persona might be uninitialized or empty
        response = await self.llm.ainvoke([{"role": "system", "content": self.persona}])
```

**GOOD:**
```python
# Fail fast at __init__ time if the persona file is missing.
class PlannerAgent(Agent):
    def __init__(self, personas_dir: Path | None = None):
        if personas_dir is None:
            personas_dir = Path("personas")
        self.personas_dir = Path(personas_dir)
        self.persona = self._load_persona()  # ← Raises FileNotFoundError immediately
    
    def _load_persona(self) -> str:
        path = self.personas_dir / "planner.md"
        if not path.exists():
            raise FileNotFoundError(f"Persona file not found: {path}")
        return path.read_text()
```

**Why:** Early failure (init time) is better than silent failure (run time).

---

## 10. Testability Approach

### Unit Tests: Classification

```python
# tests/pipeline/test_failure.py

import pytest
from forged.pipeline.failure import (
    FailureCategory, classify, ExecutionReport, GradeReport
)
from forged.pipeline.state import Evidence, Location, LocationType


@pytest.mark.unit
def test_classify_blocker_structure():
    """BLOCKER in plan/structure → BLOCKER_STRUCTURE"""
    grade = GradeReport(
        quality_score=85,
        findings=[
            Evidence(
                source="student_feedback",
                severity="BLOCKER",
                scope="structure",
                location=Location(type=LocationType.GLOBAL),
                text="Collision handling before hash function definition",
            ),
        ],
    )
    result = classify(execution_report=None, grade_report=grade)
    assert result.category == FailureCategory.BLOCKER_STRUCTURE


@pytest.mark.unit
def test_classify_code_quality_when_execution_fails():
    """Failed execution → CODE_QUALITY"""
    exec_report = ExecutionReport(ok=False, failed_cells=[2, 5])
    result = classify(execution_report=exec_report, grade_report=None)
    assert result.category == FailureCategory.CODE_QUALITY


@pytest.mark.unit
def test_classify_acceptable():
    """Execution OK + quality >= threshold → ACCEPTABLE"""
    exec_report = ExecutionReport(ok=True)
    grade = GradeReport(quality_score=92)
    result = classify(execution_report=exec_report, grade_report=grade)
    assert result.category == FailureCategory.ACCEPTABLE


@pytest.mark.unit
def test_classify_unclassifiable():
    """No signals match → UNCLASSIFIABLE"""
    result = classify(execution_report=None, grade_report=None)
    assert result.category == FailureCategory.UNCLASSIFIABLE
```

### Unit Tests: Routing

```python
# tests/pipeline/test_router.py

import pytest
from forged.pipeline.router import Router, RoutingRequest, RoutingBudget
from forged.pipeline.state import (
    PipelineState, PipelineStage, create_initial_state
)
from forged.pipeline.failure import FailureCategory, Classification


@pytest.mark.unit
def test_route_acceptable_terminates():
    """ACCEPTABLE classification → terminate"""
    router = Router()
    state = create_initial_state()
    classification = Classification(
        category=FailureCategory.ACCEPTABLE,
        reason="Good enough",
    )
    
    result = router.route(RoutingRequest(state, classification, []))
    
    assert result.should_terminate is True
    assert result.next_stage is None


@pytest.mark.unit
def test_route_code_quality_to_code_author():
    """CODE_QUALITY → route to CODE_AUTHOR"""
    router = Router()
    state = create_initial_state()
    classification = Classification(
        category=FailureCategory.CODE_QUALITY,
        reason="Code failed",
    )
    
    result = router.route(RoutingRequest(state, classification, []))
    
    assert result.next_stage == PipelineStage.CODE_AUTHOR
    assert result.routing_decision is not None


@pytest.mark.unit
def test_route_respects_budget():
    """If budget exhausted, terminate instead of routing"""
    budget = RoutingBudget(code_author=1)
    router = Router(budget=budget)
    
    # Simulate state where CODE_AUTHOR has been tried once already
    state = create_initial_state().with_attempt(PipelineStage.CODE_AUTHOR)
    
    classification = Classification(
        category=FailureCategory.CODE_QUALITY,
        reason="Code failed again",
    )
    
    result = router.route(RoutingRequest(state, classification, []))
    
    assert result.should_terminate is True
    assert "budget" in result.reason.lower()
```

### Unit Tests: State Schema

```python
# tests/pipeline/test_state.py

import pytest
from forged.pipeline.state import (
    PipelineState, PipelineStage, Location, LocationType,
    StageOutput, create_initial_state
)


@pytest.mark.unit
def test_create_initial_state():
    state = create_initial_state()
    assert state.current_stage == PipelineStage.PLANNER
    assert state.iteration == 0
    assert state.outputs == []


@pytest.mark.unit
def test_with_current_stage_is_immutable():
    state = create_initial_state()
    new_state = state.with_current_stage(PipelineStage.CODE_AUTHOR)
    
    # Original unchanged
    assert state.current_stage == PipelineStage.PLANNER
    # New state updated
    assert new_state.current_stage == PipelineStage.CODE_AUTHOR


@pytest.mark.unit
def test_with_attempt_increments_counter():
    state = create_initial_state()
    state = state.with_attempt(PipelineStage.CODE_AUTHOR)
    state = state.with_attempt(PipelineStage.CODE_AUTHOR)
    
    assert state.get_stage_attempt_count(PipelineStage.CODE_AUTHOR) == 2


@pytest.mark.unit
def test_location_validation():
    """CELL location must have cell_index"""
    with pytest.raises(ValueError):
        Location(type=LocationType.CELL)  # Missing cell_index


@pytest.mark.unit
def test_state_validation():
    """iteration must be >= 0"""
    with pytest.raises(ValueError):
        PipelineState(
            run_id="test",
            current_stage=PipelineStage.PLANNER,
            iteration=-1,
        )
```

### Integration Tests

```python
# tests/pipeline/test_integration.py

import pytest
from forged.pipeline import (
    PipelineState, PipelineStage, create_initial_state,
    classify, route, Router, RoutingRequest
)
from forged.pipeline.failure import ExecutionReport, GradeReport
from forged.pipeline.state import Evidence, Location, LocationType


@pytest.mark.integration
async def test_full_routing_flow():
    """
    Simulate: execution fails → classify CODE_QUALITY → route to CodeAuthor → budget OK.
    """
    # Initial state
    state = create_initial_state()
    state = state.with_current_stage(PipelineStage.REVISER)
    
    # Execution failed
    exec_report = ExecutionReport(ok=False, failed_cells=[2])
    
    # Classify
    classification = classify(execution_report=exec_report, grade_report=None)
    assert classification.category.value == "code_quality"
    
    # Build evidence
    evidence = [
        Evidence(
            source="executor_report",
            severity="BLOCKER",
            scope="code",
            location=Location(type=LocationType.CELL, cell_index=2),
            text="Cell 2 raised NameError",
        ),
    ]
    
    # Route
    router = Router()
    result = router.route(RoutingRequest(state, classification, evidence))
    
    assert result.next_stage == PipelineStage.CODE_AUTHOR
    assert result.routing_decision is not None
    
    # Update state
    new_state = state.with_routing_decision(result.routing_decision)
    assert new_state.routing_log[0].to_stage == PipelineStage.CODE_AUTHOR
    assert new_state.iteration == 1
```

---

## 11. Example: Putting It Together

Here's a minimal example of how the pieces fit together:

```python
# __main__.py (simplified orchestrator)

import asyncio
from pathlib import Path

from forged.pipeline import (
    create_initial_state,
    classify,
    route,
    Router,
    RoutingRequest,
    build_pipeline_graph,
)
from forged.artifacts import ArtifactStore


async def main():
    # 1. Create initial state
    state = create_initial_state(run_id="lesson-20260609-001")
    
    # 2. Build the LangGraph
    store = ArtifactStore(Path("./runs/lesson-20260609-001"))
    graph = build_pipeline_graph(store)
    
    # 3. Run the pipeline
    # (LangGraph handles all the state passing and routing)
    final_state = await graph.ainvoke(
        input={"...": state},  # Exact input shape depends on LangGraph version
        config={"configurable": {"store": store}},
    )
    
    # 4. Inspect the result
    print(f"Final state: {final_state.current_stage}")
    print(f"Iterations: {final_state.iteration}")
    print(f"Routing log: {final_state.routing_log}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Summary

This design provides:

1. **Clean separation of concerns**: state, classification, routing, agents, graph are distinct modules with clear boundaries
2. **Persona integration**: agents load prompts from `personas/*.md` files at init time; personas are the single source of truth for role instructions
3. **Zero circular imports**: strict ordering ensures dependency flow is acyclic
4. **Immutability**: PipelineState and all key types use `frozen=True` or `replace()`; builders ensure clean state transitions
5. **Deterministic routing**: classification reads concrete signals, no LLM variance; routing respects budgets; every decision is auditable
6. **Testability**: each module can be tested in isolation (no LangGraph, no LLM calls in unit tests)
7. **Type safety**: comprehensive type hints and validation catch bugs early
8. **Production-ready error handling**: agents handle failures gracefully, state tracks terminal conditions
9. **Extensibility**: new agents follow the Agent protocol; new failure categories extend FailureCategory enum; personas are easy to edit and version

### Key Pattern

```
Agent loads persona from file at init:
  self.persona = (personas_dir / "agent_name.md").read_text()

Agent constructs user message from state:
  user_message = self._build_user_prompt(state, store)

Agent calls LLM with both:
  response = await llm.ainvoke([
    {"role": "system", "content": self.persona},
    {"role": "user", "content": user_message},
  ])

Agent parses response and updates state:
  return state.with_output(StageOutput(...))
```

**Personas are content (easy to edit). Agents are orchestrators (manage state and I/O).**

Implementation order:
1. **state.py** — define the schema
2. **failure.py** — implement classification logic
3. **router.py** — implement routing logic
4. **agents/__init__.py** — define the protocol with persona loading
5. **agents/*.py** — implement each agent with _load_persona() and _build_user_prompt()
6. **graph.py** — wire the graph with personas_dir parameter
7. **tests/** — write unit and integration tests throughout
