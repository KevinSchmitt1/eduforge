# forgeducation Agentic Pipeline — Implementation Plan

**Status:** COMPLETE (Phases 1–6, as of 2026-06-09)  
**Target:** 6 phases, 80%+ test coverage, end-to-end pipeline execution  
**Effort estimate:** 5–7 days (competent Python developer with LangGraph experience)

---

## Completion Status

Phases 1–6 are complete. All checklist items below were satisfied on 2026-06-09.

| Phase | Description | Status | Tests |
|---|---|---|---|
| 1 | State schema, immutable builders, validation | COMPLETE | `test_state.py` |
| 2 | Failure classification (6 categories) | COMPLETE | `test_failure.py` |
| 3 | Routing logic, budget enforcement | COMPLETE | `test_router.py` |
| 4 | Agent protocol, persona loading | COMPLETE | `test_agents.py` |
| 5 | Concrete agents (Planner, CodeAuthor, Executor, Student, Reviser) | COMPLETE | `test_agents_*.py` |
| 6 | LangGraph assembly, end-to-end integration | COMPLETE | `test_graph_integration.py` |

**Test count:** 285 total (216 pipeline-specific), all passing.  
**Coverage:** 88% overall; `state.py`, `failure.py`, `router.py` at 100%.  
**OpenAI integration:** both linear and agentic paths tested end-to-end with a real API key.

Known limitations of the current state are documented in
[07-agentic-pipeline-status.md](./07-agentic-pipeline-status.md).

---

## Overview

We are building the agentic pipeline: a deterministic, auditable multi-stage workflow using LangGraph that automatically routes lessons between planning, coding, execution, grading, and revision stages.

**What we're building:**
- Immutable state schema (PipelineState) that flows through LangGraph nodes
- Deterministic failure classification (ExecutionReport + GradeReport → FailureCategory)
- Deterministic routing logic (FailureCategory + budget → next stage)
- Five specialized agents (Planner, CodeAuthor, Executor, Student, Reviser)
- LangGraph assembly that orchestrates the whole flow
- Comprehensive unit + integration tests (no LLM mocking required for classification/routing tests)

**Why phases matter:**
- Each phase has hard dependencies (state before classification, classification before routing, etc.)
- Phases can be tested in isolation before wiring the graph
- Clear checkpoints prevent rework and enable parallel code review

**Success criteria:**
1. All unit tests pass (state, classification, routing, schema validation)
2. All integration tests pass (classification + routing + state together)
3. Full pipeline runs end-to-end with mock agents or real LLM calls
4. Zero circular imports; acyclic dependency graph
5. Code is <800 lines per file, functions <50 lines
6. 80%+ coverage on state, classification, routing modules

---

## Phase Breakdown

### Phase 1: State Schema & Immutability Tests

**Goal:** Define the core PipelineState, all supporting types, and builder methods. Establish immutability as the foundation.

**Files to create:**
```
forged/pipeline/
├── __init__.py                 (will export public API; stub for now)
├── state.py                    (PipelineState, Location, Evidence, RoutingDecision, etc.)

tests/pipeline/
├── __init__.py                 (pytest marker definitions)
├── test_state.py               (immutability, builders, validation, schema)
```

**Tasks:**

1. **Create `forged/pipeline/state.py`**
   - Define enums: `PipelineStage` (PLANNER, CODE_AUTHOR, EXECUTOR, STUDENT, REVISER)
   - Define enums: `LocationType` (CELL, SECTION, LESSON_STRUCTURE, ARTIFACT, GLOBAL)
   - Define frozen dataclasses: `Location`, `Evidence`, `RoutingDecision`, `StageOutput`
   - Define main dataclass: `PipelineState` (run_id, current_stage, iteration, outputs, stage_attempts, routing_log, is_terminal, terminal_reason)
   - Implement `__post_init__` validation for Location (cell_index consistency) and PipelineState (iteration >= 0, current_stage type)
   - Implement builder methods: `with_current_stage()`, `with_output()`, `with_routing_decision()`, `with_attempt()`, `with_terminal()`
   - Implement query methods: `get_stage_attempt_count()`, `last_routing_to_stage()`
   - Implement `create_initial_state(run_id=None)` factory
   - **LOC estimate:** ~300 lines
   - **Implementation time:** 2 hours

2. **Create `forged/pipeline/__init__.py`** (stub)
   - Placeholder exports (to be filled in Phase 2)
   - **LOC estimate:** 10 lines
   - **Implementation time:** 15 min

3. **Create `tests/pipeline/__init__.py`**
   - Define pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`
   - **LOC estimate:** 5 lines
   - **Implementation time:** 10 min

4. **Create `tests/pipeline/test_state.py`**
   - Test state initialization: `test_create_initial_state()` checks defaults
   - Test immutability: `test_with_current_stage_is_immutable()` verifies original unchanged
   - Test builders: `test_with_output_appends()`, `test_with_attempt_increments()`, `test_with_routing_decision_appends_and_increments_iteration()`
   - Test validation: `test_location_cell_requires_index()`, `test_location_non_cell_rejects_index()`, `test_state_rejects_negative_iteration()`
   - Test query methods: `test_get_stage_attempt_count()`, `test_last_routing_to_stage()`
   - Test terminal: `test_with_terminal_marks_final()`
   - **LOC estimate:** 200 lines, 15–20 test cases
   - **Implementation time:** 3 hours

**Dependencies:** None (only stdlib + dataclasses)

**Success criteria:**
- All 20 tests pass
- Zero mutations detected (run tests with and without builder methods)
- Type hints compile with mypy (no errors)
- Coverage: state.py at 95%+

---

### Phase 2: Failure Classification & Determinism Tests

**Goal:** Implement deterministic classification logic that reads concrete signals and outputs failure categories. Verify 100% determinism with property-based tests.

**Files to create:**
```
forged/pipeline/
├── failure.py                  (FailureCategory, Classification, ExecutionReport, GradeReport, classify())

tests/pipeline/
├── test_failure.py             (classification logic, all 6 categories covered)
```

**Tasks:**

1. **Create `forged/pipeline/failure.py`**
   - Define enum: `FailureCategory` (BLOCKER_STRUCTURE, CODE_QUALITY, TEST_FAILURE, CONTENT_QUALITY, ACCEPTABLE, UNCLASSIFIABLE)
   - Define frozen dataclass: `ExecutionReport` (ok: bool, failed_cells: list[int], error_summary: str | None)
   - Define frozen dataclass: `GradeReport` (quality_score: float, blockers: list[str], findings: list[Evidence])
   - Define frozen dataclass: `Classification` (category, reason, matched_signals)
   - Implement `classify(execution_report, grade_report, quality_threshold=80.0) -> Classification`
     - Check 1: Plan-scope BLOCKER in findings → BLOCKER_STRUCTURE
     - Check 2: Code failed to run (execution_report.ok is False) → CODE_QUALITY
     - Check 3: Output/test failure (code runs but high-severity code finding) → TEST_FAILURE
     - Check 4: Quality score < threshold → CONTENT_QUALITY
     - Check 5: All good (execution OK + quality acceptable) → ACCEPTABLE
     - Check 6: Can't figure it out → UNCLASSIFIABLE
   - Use early returns (flat priority cascade, no nesting)
   - Track matched_signals for auditability
   - **LOC estimate:** 150 lines
   - **Implementation time:** 2.5 hours

2. **Create `tests/pipeline/test_failure.py`**
   - **Test coverage by category:**
     - `test_classify_blocker_structure()` — BLOCKER finding in plan scope
     - `test_classify_code_quality_when_execution_fails()` — execution_report.ok = False
     - `test_classify_test_failure_when_output_wrong()` — code runs, high-severity finding on output
     - `test_classify_content_quality_when_score_low()` — quality_score < 80
     - `test_classify_acceptable()` — execution OK, quality >= threshold
     - `test_classify_unclassifiable()` — no signals (both None)
   - **Test edge cases:**
     - `test_classify_multiple_findings_takes_first_blocker()` — priority matters
     - `test_classify_respects_quality_threshold()` — parameterized (60, 80, 100)
     - `test_classify_when_execution_fails_and_quality_low()` — execution failure takes priority
     - `test_classify_determinism()` — same input → same output (run 10x)
   - **Test signals tracking:**
     - `test_matched_signals_contains_reason_text()` — debug info is there
   - **LOC estimate:** 250 lines, 25+ test cases
   - **Implementation time:** 4 hours

**Dependencies:** phase1 (state.py, for Evidence/Location types)

**Success criteria:**
- All 25 tests pass
- Classification is 100% deterministic (property-based test: same inputs → same output, always)
- All 6 FailureCategory values are tested
- Coverage: failure.py at 98%+

---

### Phase 3: Routing Logic & Budget Enforcement Tests

**Goal:** Implement deterministic routing that respects budgets and produces auditable RoutingDecision entries. Verify no budget bypass.

**Files to create:**
```
forged/pipeline/
├── router.py                   (RoutingBudget, Router, RoutingRequest, RoutingResult)

tests/pipeline/
├── test_router.py              (routing logic, budget enforcement, edge cases)
```

**Tasks:**

1. **Create `forged/pipeline/router.py`**
   - Define frozen dataclass: `RoutingBudget` (planner=2, code_author=3, student=1, reviser=1, executor=unlimited)
   - Add method `can_route_to(stage) -> bool` to RoutingBudget
   - Define frozen dataclass: `RoutingRequest` (state, classification, evidence)
   - Define frozen dataclass: `RoutingResult` (next_stage: PipelineStage | None, should_terminate: bool, reason: str, routing_decision: RoutingDecision | None)
   - Implement `Router` class with:
     - `__init__(budget: RoutingBudget | None = None)`
     - `route(request: RoutingRequest) -> RoutingResult`
       - Terminal cases: ACCEPTABLE → None, UNCLASSIFIABLE → None
       - Non-terminal cases: map classification to target stage, check budget, build RoutingDecision
       - If budget exhausted → terminate with reason
       - If budget available → route and record decision
   - Use early returns (no nesting)
   - **LOC estimate:** 140 lines
   - **Implementation time:** 2.5 hours

2. **Create `tests/pipeline/test_router.py`**
   - **Test routing by category:**
     - `test_route_acceptable_terminates()` — ACCEPTABLE → None, should_terminate=True
     - `test_route_unclassifiable_terminates()` — UNCLASSIFIABLE → None, should_terminate=True
     - `test_route_blocker_structure_to_planner()` — BLOCKER_STRUCTURE → PLANNER
     - `test_route_code_quality_to_code_author()` — CODE_QUALITY → CODE_AUTHOR
     - `test_route_test_failure_to_code_author()` — TEST_FAILURE → CODE_AUTHOR
     - `test_route_content_quality_to_reviser()` — CONTENT_QUALITY → REVISER
   - **Test budget enforcement:**
     - `test_route_respects_planner_budget()` — if planner attempts >= 2, terminate
     - `test_route_respects_code_author_budget()` — if code_author attempts >= 3, terminate
     - `test_route_respects_student_budget()` — if student attempts >= 1, terminate
     - `test_route_respects_reviser_budget()` — if reviser attempts >= 1, terminate
     - `test_route_no_budget_bypass()` — parameterized: all stages with exhausted budget
   - **Test RoutingDecision building:**
     - `test_routing_decision_has_evidence()` — decision.evidence matches request.evidence
     - `test_routing_decision_has_classification()` — decision.classification set correctly
     - `test_routing_decision_has_timestamp()` — unique ID generated
   - **Test edge cases:**
     - `test_route_with_no_budget_at_all()` — RoutingBudget(planner=0, ...) terminates immediately
     - `test_route_with_unlimited_executor_budget()` — executor can always route
   - **LOC estimate:** 280 lines, 20+ test cases
   - **Implementation time:** 4 hours

**Dependencies:** Phase 1 (state.py) + Phase 2 (failure.py)

**Success criteria:**
- All 20 tests pass
- Budget enforcement is guaranteed: `test_route_no_budget_bypass()` covers all stages
- RoutingDecision is built correctly with evidence and audit info
- Coverage: router.py at 98%+

---

### Phase 4: Agent Protocol & Persona Loading

**Goal:** Define the abstract Agent base class and protocol. Verify persona file loading is fail-fast.

**Files to create:**
```
forged/pipeline/agents/
├── __init__.py                 (Agent ABC, AgentOutput dataclass, protocol definitions)

tests/pipeline/
├── test_agents.py              (persona loading, protocol compliance)
```

**Tasks:**

1. **Create `forged/pipeline/agents/__init__.py`**
   - Define enum/types for artifact kinds (notebook, markdown, json, etc.)
   - Define frozen dataclass: `AgentOutput` (stage_name, artifact_name, artifact_kind, metadata)
   - Define abstract base class `Agent[T]`:
     - `__init__(personas_dir: Path | None = None)` — loads persona immediately (fail-fast)
     - Abstract method `_load_persona() -> str` — subclasses implement to load from personas_dir/{name}.md
     - Abstract async method `run(state: PipelineState, store: ArtifactStore) -> PipelineState` — main entry point
     - Abstract method `next_stage() -> PipelineStage | None` — what stage follows this one
     - Property `persona: str` — the loaded persona text
   - Raise `FileNotFoundError` immediately if persona file missing
   - **LOC estimate:** 120 lines
   - **Implementation time:** 1.5 hours

2. **Create `tests/pipeline/test_agents.py`**
   - Create a minimal mock agent: `MockAgent(Agent)` that loads `personas/mock.md`
   - Test persona loading:
     - `test_agent_loads_persona_at_init()` — persona is loaded in __init__
     - `test_agent_fails_fast_if_persona_missing()` — FileNotFoundError at __init__, not later
   - Test protocol compliance:
     - `test_agent_run_returns_new_state()` — run() returns PipelineState (immutability)
     - `test_agent_next_stage_returns_valid_stage_or_none()` — next_stage() respects protocol
   - Create `tests/personas/mock.md` fixture with minimal content
   - **LOC estimate:** 150 lines, 8–10 test cases
   - **Implementation time:** 2 hours

**Dependencies:** Phase 1 (state.py)

**Success criteria:**
- Agent protocol is clear and testable
- Persona loading fails fast (FileNotFoundError at init)
- Mock agent can be instantiated and run safely
- Coverage: agents/__init__.py at 90%+

---

### Phase 5: Concrete Agents (Planner, CodeAuthor, Executor, Student, Reviser)

**Goal:** Implement all five agents with persona loading, user prompt building, and state transitions. Mock LLM calls for testing.

**Files to create:**
```
forged/pipeline/agents/
├── planner.py                  (PlannerAgent)
├── code_author.py              (CodeAuthorAgent)
├── executor.py                 (ExecutorAgent wrapper)
├── student.py                  (StudentAgent)
├── reviser.py                  (RevisorAgent — the router)

tests/pipeline/
├── test_agents_planner.py      (PlannerAgent tests)
├── test_agents_code_author.py  (CodeAuthorAgent tests)
├── test_agents_executor.py     (ExecutorAgent tests)
├── test_agents_student.py      (StudentAgent tests)
├── test_agents_reviser.py      (RevisorAgent tests)
```

**Tasks:**

1. **Create `forged/pipeline/agents/planner.py`**
   - Implement `PlannerAgent(Agent[AgentOutput])`
   - `_load_persona()` → loads `personas/planner.md`
   - `_build_user_prompt(state, store) -> str` → reads topic brief + learner profile from store, formats as user message
   - `async run(state, store) -> PipelineState`:
     - Build user message
     - Call LLM with system=self.persona, user=user_message
     - Write artifact: `lesson_plan_v{iteration}.md`
     - Return `state.with_output(...).with_current_stage(CODE_AUTHOR)`
   - `next_stage() -> PipelineStage` → return CODE_AUTHOR
   - Error handling: catch LLM errors, log, return terminal state
   - **LOC estimate:** 100 lines
   - **Implementation time:** 2 hours

2. **Create `forged/pipeline/agents/code_author.py`**
   - Implement `CodeAuthorAgent(Agent[AgentOutput])`
   - `_load_persona()` → loads `personas/code_author.md`
   - `_build_user_prompt(state, store) -> str` → reads lesson plan + feedback (if re-coding from routing_log)
   - `async run(state, store) -> PipelineState`:
     - Build user message
     - Call LLM with system=self.persona, user=user_message
     - Parse response (validate JSON notebook structure)
     - Write artifact: `lesson_notebook_v{iteration}.ipynb`
     - Return `state.with_output(...).with_current_stage(EXECUTOR)`
   - `next_stage() -> PipelineStage` → return EXECUTOR
   - **LOC estimate:** 120 lines
   - **Implementation time:** 2.5 hours

3. **Create `forged/pipeline/agents/executor.py`**
   - Implement `ExecutorAgent(Agent[AgentOutput])`
   - Wrapper around existing `forged.executor.ExecutorStage`
   - `_load_persona()` → return "" (no persona needed, deterministic)
   - `async run(state, store) -> PipelineState`:
     - Delegate to ExecutorStage.run(notebook)
     - Parse execution report (ExecutionReport)
     - Write artifact: `execution_report_v{iteration}.json`
     - Return `state.with_output(...).with_current_stage(STUDENT)`
   - `next_stage() -> PipelineStage` → return STUDENT
   - **LOC estimate:** 80 lines
   - **Implementation time:** 1.5 hours

4. **Create `forged/pipeline/agents/student.py`**
   - Implement `StudentAgent(Agent[AgentOutput])`
   - `_load_persona()` → loads `personas/student.md`
   - `_build_user_prompt(state, store) -> str` → reads executed notebook + learning objectives
   - `async run(state, store) -> PipelineState`:
     - Build user message
     - Call LLM with system=self.persona, user=user_message
     - Parse response into GradeReport (quality_score, findings)
     - Write artifact: `student_grade_report_v{iteration}.json`
     - Return `state.with_output(...).with_current_stage(REVISER)`
   - `next_stage() -> PipelineStage | None` → return None (reviser decides next)
   - **LOC estimate:** 110 lines
   - **Implementation time:** 2 hours

5. **Create `forged/pipeline/agents/reviser.py`**
   - Implement `RevisorAgent(Agent[AgentOutput])`
   - `_load_persona()` → loads `personas/reviser.md` (or empty; routing is deterministic)
   - `async run(state, store) -> PipelineState`:
     - Read execution_report.json and student_grade_report.json from store
     - Call `classify(exec_report, grade_report)` → Classification
     - Build evidence list from findings
     - Call `Router().route(RoutingRequest(state, classification, evidence))` → RoutingResult
     - If routing_decision: `state.with_routing_decision(decision)`, update current_stage
     - If terminal: `state.with_terminal(reason)`
     - Do NOT produce an artifact (just state updates)
     - Return new state
   - `next_stage() -> PipelineStage | None` → return None (state determines routing)
   - **LOC estimate:** 90 lines
   - **Implementation time:** 2 hours

6. **Create `tests/pipeline/test_agents_*.py`** (for each agent)
   - Mock LLM responses using `unittest.mock.AsyncMock`
   - For each agent:
     - `test_agent_loads_persona()` — persona is loaded
     - `test_agent_run_returns_new_state()` — immutability
     - `test_agent_writes_artifact()` — output is stored
     - `test_agent_handles_llm_error()` — gracefully fails
     - (Agent-specific tests, e.g., CodeAuthor: `test_code_author_includes_feedback_on_recode()`)
   - Reviser specific:
     - `test_reviser_calls_classify()` — integrates with classification
     - `test_reviser_calls_route()` — integrates with routing
     - `test_reviser_updates_routing_log()` — state tracks decision
     - `test_reviser_terminal_when_acceptable()` — terminal state when classification is ACCEPTABLE
   - **LOC estimate per agent:** 120 lines, 8–10 test cases
   - **Total for all 5 agents:** ~600 lines, 50 test cases
   - **Implementation time:** 10 hours total (2 hours per agent)

**Dependencies:** Phase 1–3 (state, failure, router) + existing forged.executor, forged.artifacts

**Success criteria:**
- All 50 tests pass
- All agents load personas correctly
- All agents update state immutably
- Reviser integrates classification + routing correctly
- Coverage: agents/*.py at 85%+ each

---

### Phase 6: LangGraph Assembly & End-to-End Tests

**Goal:** Wire the LangGraph workflow. Verify full pipeline runs end-to-end. Test conditional routing works.

**Files to create:**
```
forged/pipeline/
├── graph.py                    (build_pipeline_graph, node definitions, conditional edges)

tests/pipeline/
├── test_integration.py         (full pipeline E2E, conditional routing, loop termination)
├── conftest.py                 (fixtures: initial state, mock store, mock agents)
```

**Tasks:**

1. **Create `forged/pipeline/graph.py`**
   - Define `build_pipeline_graph(store: ArtifactStore, personas_dir: Path | None = None) -> StateGraph`
   - Initialize agents with personas_dir (PlannerAgent, CodeAuthorAgent, ExecutorAgent, StudentAgent, RevisorAgent)
   - Define async node wrappers:
     - `async def planner_node(state) -> PipelineState`: `await planner.run(state, store)`
     - (Similar for code_author, executor, student, revisor)
   - Add nodes: "planner", "code_author", "executor", "student", "revisor"
   - Add edges:
     - `START → planner`
     - `planner → code_author`
     - `code_author → executor`
     - `executor → student`
     - `student → revisor`
   - Add conditional edge from revisor:
     - `revisor_route(state) -> str`:
       - If `state.is_terminal` → END
       - Else read `state.routing_log[-1].to_stage` → return that stage
       - If no to_stage → END
     - Mapping: "planner" → "planner", "code_author" → "code_author", "reviser" → "revisor", END → END
   - Return `graph.compile()`
   - **LOC estimate:** 120 lines
   - **Implementation time:** 2.5 hours

2. **Create `tests/pipeline/conftest.py`**
   - Fixture `initial_state()` → `create_initial_state()`
   - Fixture `mock_artifact_store()` → in-memory ArtifactStore for testing
   - Fixture `mock_llm_response()` → parameterized LLM response (plan, notebook, grade, etc.)
   - Fixture `personas_dir()` → path to test personas
   - **LOC estimate:** 80 lines
   - **Implementation time:** 1.5 hours

3. **Create `tests/pipeline/test_integration.py`**
   - **Test full pipeline flow:**
     - `async test_full_pipeline_acceptable()`:
       - Start with initial_state
       - Mock all agents to succeed (planner → code_author → executor → student → reviser)
       - Reviser returns ACCEPTABLE classification
       - Assert final state is terminal with reason "acceptable"
     - `async test_full_pipeline_code_quality_loop()`:
       - Start with initial_state
       - CodeAuthor runs, Executor reports failure (ExecutionReport.ok = False)
       - Student grades it, Reviser classifies as CODE_QUALITY
       - Router routes back to CodeAuthor (attempt 2)
       - CodeAuthor runs again, Executor succeeds
       - Student grades as ACCEPTABLE
       - Final state is terminal
       - Assert routing_log has 2 entries: one failed CodeAuthor, one re-routed CodeAuthor
     - `async test_full_pipeline_blocker_structure()`:
       - Student finds BLOCKER in plan scope
       - Reviser classifies as BLOCKER_STRUCTURE
       - Router routes to Planner (attempt 2)
       - Planner revises, then restart
       - Assert routing_log shows planner routed
   - **Test budget exhaustion:**
     - `async test_pipeline_terminates_when_code_author_budget_exhausted()`:
       - CodeAuthor tries 3 times, all fail
       - Fourth time, Reviser sees budget exhausted, terminates
       - Assert final state terminal with reason "budget exhausted"
   - **Test conditional routing:**
     - `async test_reviser_routing_to_planner()`:
       - State with BLOCKER_STRUCTURE classification
       - Reviser routes to planner
       - Graph conditional edge should route to "planner" node
       - Next execution goes to Planner
     - `async test_reviser_routing_to_code_author()`:
       - State with CODE_QUALITY classification
       - Reviser routes to code_author
       - Graph conditional edge should route to "code_author" node
     - `async test_reviser_routing_to_end()`:
       - State with ACCEPTABLE classification
       - Reviser terminates
       - Graph conditional edge should route to END
   - **Test audit trail:**
     - `async test_routing_log_has_evidence()`:
       - After a re-route, assert routing_log[0].evidence has location info
       - Assert location.type, location.label, location.cell_index are set correctly
   - **LOC estimate:** 400 lines, 15+ test cases
   - **Implementation time:** 6 hours

4. **Update `forged/pipeline/__init__.py`** with full public API
   - Export: PipelineState, PipelineStage, Location, LocationType, Evidence, RoutingDecision, StageOutput, create_initial_state
   - Export: FailureCategory, Classification, ExecutionReport, GradeReport, classify
   - Export: Router, RoutingBudget, RoutingRequest, RoutingResult
   - Export: Agent, AgentOutput
   - Export: build_pipeline_graph
   - **LOC estimate:** 40 lines
   - **Implementation time:** 30 min

**Dependencies:** Phase 1–5 + LangGraph library (add to pyproject.toml)

**Success criteria:**
- All 15+ integration tests pass
- Full pipeline runs end-to-end without errors
- Conditional routing works: same classification always routes to same stage
- Budget enforcement prevents infinite loops
- Audit trail is complete (routing_log tracks all decisions + evidence)
- Coverage: graph.py at 85%+, test_integration.py proves correctness

---

## Implementation Order (Strict Sequence)

```
Phase 1: State Schema
  └─ Phase 2: Classification (depends on state.py)
     └─ Phase 3: Routing (depends on state.py + failure.py)
        └─ Phase 4: Agent Protocol (depends on state.py)
           └─ Phase 5: Concrete Agents (depends on 1–4)
              └─ Phase 6: LangGraph + E2E Tests (depends on 1–5)
```

**Why this order:**
- State is the foundation; everything flows through it
- Classification depends on state types (Evidence, Location)
- Routing depends on both state and classification
- Agents need the protocol + persona loading framework
- Concrete agents implement the protocol
- LangGraph wires everything together

**Parallelization:** 
- Phase 1 can be coded solo
- Phase 2 and 3 can be coded in parallel (both independent of agents)
- Phase 4 can start once Phase 1 is done
- Phase 5 can start once Phase 4 is done (5 agents can be coded in parallel)
- Phase 6 can start once Phase 5 is complete

**Estimated wall-clock time with 1 developer:**
- Phase 1: 1 day
- Phase 2–3: 1.5 days (can overlap code review)
- Phase 4: 0.5 days
- Phase 5: 2 days
- Phase 6: 1.5 days
- **Total: 6.5 days**

---

## Testing Strategy

### Unit Tests (No LLM, No LangGraph)

**Phase 1: State schema tests** (20 tests)
- Create state, verify immutability, builders work, validation catches errors

**Phase 2: Classification tests** (25 tests)
- Input (ExecutionReport, GradeReport) → Classification, verify all 6 categories, determinism property

**Phase 3: Routing tests** (20 tests)
- Input (state, classification) → RoutingResult, verify budget enforcement, no bypass, all routes

**Phase 4: Agent protocol tests** (10 tests)
- Persona loading, fail-fast on missing file, protocol compliance

**Phase 5: Concrete agent tests** (50 tests, 10 per agent)
- Mock LLM responses, verify persona loads, user prompt built, artifact written, state immutable

**Total unit tests: 125 tests, all <100ms, run in <5 seconds**

### Integration Tests (No LLM if mocked, Yes LangGraph)

**Phase 6: Full pipeline tests** (15 tests)
- Mock agents → run full pipeline → verify state transitions, conditional routing, budget, audit trail
- All LLM calls can be mocked; classification and routing are deterministic

**Total integration tests: 15 tests, all <1s, run in <20 seconds**

### E2E Test (Real LLM, Optional)

Once integration tests pass:
- Write a single E2E test with real LLM calls (or skip for now, add later)
- Use claude-3-5-haiku or gpt-4-turbo
- Verify agents actually generate sensible content
- This is optional for Phase 6 delivery

### Coverage Target

| Module | Target | Priority |
|--------|--------|----------|
| state.py | 95%+ | CRITICAL |
| failure.py | 98%+ | CRITICAL |
| router.py | 98%+ | CRITICAL |
| agents/__init__.py | 90%+ | HIGH |
| agents/planner.py | 85%+ | HIGH |
| agents/code_author.py | 85%+ | HIGH |
| agents/executor.py | 85%+ | HIGH |
| agents/student.py | 85%+ | HIGH |
| agents/reviser.py | 85%+ | HIGH |
| graph.py | 85%+ | HIGH |
| **Overall** | **80%+** | **GATE** |

Run coverage with: `pytest --cov=forged.pipeline tests/pipeline/ --cov-report=term-missing`

---

## Checkpoints & Verification

### After Phase 1: State Schema
- [ ] All 20 state tests pass
- [ ] mypy reports zero errors on state.py
- [ ] No mutations detected: original state unchanged after calling `with_*` builders
- [ ] All validation rules in `__post_init__` trigger as expected

### After Phase 2: Classification
- [ ] All 25 classification tests pass
- [ ] All 6 FailureCategory values have at least one test case
- [ ] Determinism test: same input 10x → same output 10x
- [ ] matched_signals list is non-empty and helpful for debugging

### After Phase 3: Routing
- [ ] All 20 routing tests pass
- [ ] Budget enforcement verified: no stage can be routed to after budget exhausted
- [ ] RoutingDecision has timestamp (unique ID) and evidence list
- [ ] All 6 mapping paths tested (BLOCKER_STRUCTURE→PLANNER, CODE_QUALITY→CODE_AUTHOR, etc.)

### After Phase 4: Agent Protocol
- [ ] Persona loading fails fast (FileNotFoundError at __init__)
- [ ] Mock agent instantiates and runs without error
- [ ] next_stage() returns valid PipelineStage or None
- [ ] run() returns new state (immutability verified)

### After Phase 5: Concrete Agents
- [ ] All 50 agent tests pass
- [ ] Each agent loads its persona from file
- [ ] Each agent builds user prompt from state context
- [ ] Each agent writes artifact to store
- [ ] Each agent returns new state (no mutations)
- [ ] Reviser integrates classification + routing (end-to-end verify)

### After Phase 6: LangGraph Assembly
- [ ] All 15 integration tests pass
- [ ] Full pipeline runs without error (Planner → CodeAuthor → Executor → Student → Reviser → END)
- [ ] Conditional routing works: classify as BLOCKER_STRUCTURE, reviser routes to PLANNER, graph goes to planner node
- [ ] Budget exhaustion terminates pipeline
- [ ] Audit trail is complete: routing_log has 1+ entries, each with classification, reason, evidence
- [ ] `build_pipeline_graph()` compiles without error
- [ ] mypy reports zero errors on entire pipeline package

---

## Rollback & Risk Mitigation

### Critical Risks

| Risk | Symptom | Recovery |
|------|---------|----------|
| **Circular imports** | `ImportError: circular import detected` | Check dependency graph in [Design Doc](./05-implementation-design.md#8-dependencies-and-imports-strategy). Ensure state.py imports nothing from lower modules. |
| **State mutation** | Tests fail: `state.outputs is state2.outputs` (same list object) | Use `dataclasses.replace()` and ensure builders create new lists (`self.outputs + [item]`). |
| **Classification non-determinism** | Same input, different output on re-run | Remove any RNG or LLM calls from `classify()`. Use only concrete signal matching. |
| **Budget bypass** | Router allows routing even when budget=0 | Add explicit check: `if attempt_count >= budget for_stage: return terminate`. Add test case. |
| **Missing persona file** | FileNotFoundError at runtime (late) | Load personas in `__init__()`, not in `run()`. Fail fast. |
| **LLM integration issues** | Agent can't call LLM | Mock LLM responses in tests. Real calls are added in Phase 7 (post-implementation). |

### If Phase N Fails

**Phase 1 fails:** State schema has bugs
- Go back, re-read design doc section 2
- Verify immutability: all builders use `replace()`
- Add missing validation in `__post_init__()`
- Re-run tests

**Phase 2 fails:** Classification doesn't cover all 6 categories
- Verify signal matching logic is correct
- Check test cases cover all branches
- Use branch coverage tool: `pytest-cov --cov=forged.pipeline.failure`

**Phase 3 fails:** Router allows budget bypass
- Verify budget check is done before returning RoutingResult
- Test all 5 stages with budget=1 and attempt=1
- Add explicit assertion in router code

**Phase 4 fails:** Agent protocol is unclear
- Simplify: make one concrete mock agent, test it
- If persona loading breaks, check file path is correct

**Phase 5 fails:** Agents don't integrate with state/classification/router
- Test each agent in isolation first (mock dependencies)
- Test Reviser last (it integrates everything)
- Use a simpler mock state if needed (hardcoded values)

**Phase 6 fails:** Graph doesn't compile or routing breaks
- Verify conditional edge function returns valid node names
- Check all node names match edge definitions
- Test conditional edge in isolation with hardcoded state

---

## Effort Estimate

| Phase | Tasks | LOC | Hours | Days |
|-------|-------|-----|-------|------|
| 1 | State schema + tests | 300 + 200 | 5 | 1 |
| 2 | Classification + tests | 150 + 250 | 6.5 | 1 |
| 3 | Routing + tests | 140 + 280 | 6.5 | 1 |
| 4 | Agent protocol + tests | 120 + 150 | 3.5 | 0.5 |
| 5 | 5 Concrete agents + tests | 500 + 600 | 12 | 1.5 |
| 6 | LangGraph + E2E tests | 120 + 400 | 8.5 | 1 |
| **Total** | 6 phases | **~2,500 LOC** | **42 hours** | **6–7 days** |

**Breakdown:**
- Implementation: 2,500 LOC, ~25 hours
- Testing: 1,200 LOC, ~15 hours
- Code review + fixes: ~2 hours
- Debugging unforeseen issues: ~3 hours

**With code review between phases: +1 day**

---

## Artifacts & Output

After all phases:

```
forged/
└── pipeline/
    ├── __init__.py                          (public API exports)
    ├── state.py                             (state schema, immutable)
    ├── failure.py                           (classification logic)
    ├── router.py                            (routing logic, budget enforcement)
    ├── graph.py                             (LangGraph assembly)
    └── agents/
        ├── __init__.py                      (Agent ABC, protocol)
        ├── planner.py                       (PlannerAgent)
        ├── code_author.py                   (CodeAuthorAgent)
        ├── executor.py                      (ExecutorAgent wrapper)
        ├── student.py                       (StudentAgent)
        └── reviser.py                       (RevisorAgent router)

tests/pipeline/
├── conftest.py                              (fixtures, personas)
├── test_state.py                            (20 tests, immutability)
├── test_failure.py                          (25 tests, classification)
├── test_router.py                           (20 tests, routing + budget)
├── test_agents.py                           (10 tests, protocol)
├── test_agents_planner.py                   (10 tests)
├── test_agents_code_author.py               (10 tests)
├── test_agents_executor.py                  (10 tests)
├── test_agents_student.py                   (10 tests)
├── test_agents_reviser.py                   (10 tests)
├── test_integration.py                      (15 tests, E2E)
└── personas/
    └── mock.md                              (test fixture persona)

docs/architecture/
├── 04-conceptual-guide.md                   (WHY — already exists)
├── 05-implementation-design.md              (WHAT — already exists)
└── 06-implementation-plan.md                (HOW — this document)
```

**Total production code:** ~2,500 LOC  
**Total test code:** ~1,200 LOC  
**Overall:** ~3,700 LOC

---

## Next Steps After Implementation

### Phase 7: Integration with Existing Orchestrator (Post-Implementation)

Once the pipeline is complete:

1. **Integrate with `forged.orchestrator`**
   - Orchestrator calls `build_pipeline_graph()` to create the LangGraph
   - Pass ArtifactStore and personas_dir to graph builder
   - Run pipeline with LangGraph's async executor

2. **Update `forged.cli`** to support pipeline mode
   - Add flag: `--pipeline` or `--agent-mode`
   - If set, use new agentic pipeline instead of linear pipeline

3. **Update `forged/config.py`** to support pipeline budgets
   - Add config section: `[pipeline.budgets]` with planner, code_author, student, reviser limits
   - Load budgets and pass to Router during graph assembly

4. **Documentation**
   - Add "Agentic Pipeline" section to README.md
   - Document routing decisions, failure categories, budget configuration
   - Update troubleshooting guide with common issues

5. **Testing**
   - Write integration tests between orchestrator and pipeline
   - Verify orchestrator correctly initializes graph
   - Verify orchestrator correctly reads final state

### Phase 8: E2E Testing with Real LLMs (Post-Implementation)

Once integration tests pass:

1. Write E2E test with real LLM calls (claude-3-5-haiku or gpt-4-turbo)
2. Test with small lesson (10–20 cells, simple topic)
3. Verify agents actually generate sensible content
4. Check artifact quality

### Phase 9: Optimization & Tuning (Post-Implementation)

1. Measure performance: time per agent, total pipeline time
2. Identify slow agents (usually LLM calls or notebook execution)
3. Consider caching, parallelization, or model selection
4. Update budget defaults based on real run data

---

## Code Review Checklist

Before merging each phase:

### Code Quality
- [ ] No mutations to state (use builders)
- [ ] No circular imports
- [ ] Functions <50 lines
- [ ] Files <800 lines
- [ ] Deep nesting <4 levels
- [ ] Type hints on all public APIs

### Testing
- [ ] All tests pass locally
- [ ] Coverage >= target (95%+ state, 98%+ classification/routing)
- [ ] No hardcoded test data (use fixtures)
- [ ] Test names describe behavior, not implementation

### Documentation
- [ ] Docstrings on classes and key methods
- [ ] Comments on complex logic (e.g., priority cascade in classify())
- [ ] README updated with examples

### Determinism
- [ ] Classification: same input → same output (verified with determinism test)
- [ ] Routing: same state + classification → same routing (verified with parameterized tests)
- [ ] No randomness, no LLM calls in logic modules

---

## Summary

This plan provides a clear, phased approach to building the agentic pipeline:

1. **Phase 1–3:** Foundation (state, classification, routing) — mostly deterministic logic, heavy test coverage
2. **Phase 4–5:** Orchestration (agents) — persona loading, state transitions, LLM integration
3. **Phase 6:** Assembly (LangGraph) — wire it all together, verify end-to-end

Each phase is testable in isolation. All critical logic (classification, routing, budget enforcement) is deterministic and auditable. The implementation follows the design spec exactly; no surprises.

**Ready to execute.**

---

## Phase 7–9 Roadmap

Phases 1–6 delivered the complete agentic pipeline as a Python API. The next three
phases close the remaining gaps. Full details are in
[07-agentic-pipeline-status.md](./07-agentic-pipeline-status.md).

### Phase 7 — Wire the Real Executor

Replace `ExecutorAgent._mock_execute()` with a real call to `forged.executor.ExecutorStage`
so the agentic path actually runs notebooks and detects execution failures.

### Phase 8 — Reviser Rewriting

When the Reviser reroutes to CodeAuthor or Planner, those agents should receive structured
feedback from the routing decision and grade report. Currently they re-run from the original
brief. Phase 8 wires the feedback artifact into each agent's `_build_user_prompt()`.

### Phase 9 — CLI Exposure

Add `forged build --agentic` (or a separate subcommand) so users can invoke the agentic
pipeline without writing Python. This requires reading the final artifact from
`state.outputs`, writing it to the run directory, and generating a `SUMMARY.md` equivalent
from `state.routing_log`.
