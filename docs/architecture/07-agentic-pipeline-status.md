# Agentic Pipeline — Implementation Status

**As of:** 2026-06-09  
**Phases complete:** 1–6 (state, classification, routing, agent protocol, concrete agents, LangGraph assembly)  
**Tests:** 285 total (216 pipeline-specific); all passing  
**Coverage:** 88% overall; pipeline modules at 92–100%

---

## What the Agentic Pipeline Is

The agentic pipeline is a LangGraph-based multi-stage workflow that routes a lesson between
specialised agents deterministically. Unlike the linear pipeline — which runs a fixed
sequence — the agentic pipeline classifies failures, decides which agent can fix them, and
routes back to that agent with the failure context attached.

**Why it exists:**

The linear pipeline runs every stage once in sequence. If the executor finds a failing cell
or the student finds a content gap, the run either retries blindly or stops. The agentic
pipeline replaces that with:

1. A deterministic classifier that maps concrete signals to six failure categories.
2. A budget-aware router that prevents infinite loops.
3. Auditable `RoutingDecision` entries so every reroute is traceable in `state.routing_log`.

This is the foundation for the curriculum planner (Phase 2) and for step-7 comparative
testing (linear vs. agentic quality).

---

## Implementation Summary

### Phase 1 — State Schema (`forged/pipeline/state.py`)

Defines the immutable `PipelineState` dataclass and all supporting types:
`PipelineStage`, `LocationType`, `Location`, `Evidence`, `RoutingDecision`, `StageOutput`.

All builder methods (`with_current_stage`, `with_output`, `with_routing_decision`,
`with_attempt`, `with_terminal`) return new instances via `dataclasses.replace()` — never
mutate in place. `create_initial_state()` is the only public factory.

Coverage: 100%. Tests: `tests/pipeline/test_state.py`.

### Phase 2 — Failure Classification (`forged/pipeline/failure.py`)

Implements `classify(execution_report, grade_report) -> Classification`.

Six categories in priority order:
- `BLOCKER_STRUCTURE` — a BLOCKER finding scoped to lesson structure → reroute to Planner
- `CODE_QUALITY` — execution failed (notebook did not run) → reroute to CodeAuthor
- `TEST_FAILURE` — code runs but a HIGH severity code finding exists → reroute to CodeAuthor
- `CONTENT_QUALITY` — quality score below threshold (default 80.0) → reroute to Reviser
- `ACCEPTABLE` — execution OK, quality at or above threshold → terminate (success)
- `UNCLASSIFIABLE` — no signals available → terminate (human review needed)

Classification is fully deterministic: no LLM calls, no randomness.
Coverage: 100%. Tests: `tests/pipeline/test_failure.py`.

### Phase 3 — Routing & Budget (`forged/pipeline/router.py`)

Implements `Router.route(request) -> RoutingResult`.

Default `RoutingBudget`: Planner ×2, CodeAuthor ×3, Student ×1, Reviser ×1, Executor
unlimited. When a stage's budget is exhausted, the router terminates the pipeline with
`reason="budget exhausted for <stage>"` rather than looping.

Each non-terminal routing decision produces a `RoutingDecision` with timestamp, evidence
list, classification, and `to_stage`.

Coverage: 100%. Tests: `tests/pipeline/test_router.py`.

### Phase 4 — Agent Protocol (`forged/pipeline/agents/__init__.py`)

Defines the `Agent[T]` abstract base class. Persona files are loaded at `__init__` time —
construction fails immediately with `FileNotFoundError` if the file is missing, so broken
deploys surface at startup rather than mid-run.

All concrete agents implement `_load_persona() -> str`, `next_stage()`, and
`async run(state, store) -> PipelineState`.

Coverage: 100%. Tests: `tests/pipeline/test_agents.py`.

### Phase 5 — Concrete Agents

| Agent | File | LLM | Persona file |
|---|---|---|---|
| PlannerAgent | `agents/planner.py` | Yes | `personas/planner.md` |
| CodeAuthorAgent | `agents/code_author.py` | Yes | `personas/code_author.md` |
| ExecutorAgent | `agents/executor.py` | No (mocked) | none |
| StudentAgent | `agents/student.py` | Yes | `personas/student.md` |
| RevisorAgent | `agents/reviser.py` | No (deterministic) | `personas/reviser.md` |

Agents with LLM calls degrade gracefully on errors: they log the failure and return a
terminal state rather than raising. CodeAuthor strips ` ```json ` fences and validates that
the response is a JSON array before writing a notebook artifact. Student parses a structured
grade report JSON and falls back to a zero-score report on parse failure.

`RevisorAgent` calls `classify()` and `Router.route()` with no LLM — routing is purely
deterministic. Its `_coerce_location_type()` method accepts loose labels from real LLM
output (e.g., `"notebook"` → `LocationType.ARTIFACT`) to avoid crashing on valid feedback.

Coverage: 92–96% per agent. Tests: `tests/pipeline/test_agents_concrete.py`,
`tests/pipeline/test_agents_llm.py`.

### Phase 6 — LangGraph Assembly (`forged/pipeline/graph.py`)

`build_pipeline_graph(store, personas_dir)` wires five nodes into a `StateGraph`:

```
START → planner → code_author → executor → student → revisor
                     ↑               ↑                   │
                     └───────────────┴───── conditional ──┘
                                              (or END)
```

The conditional edge function `revisor_route(state)` reads `state.routing_log[-1].to_stage`
to determine the next node name, or returns `END` if the state is terminal or the log is
empty.

`run_pipeline(initial_state, store, personas_dir)` is the public entry point. It calls
`graph.ainvoke(initial_state)` and reconstructs a typed `PipelineState` from the returned
dict.

Coverage: 96%. Tests: `tests/pipeline/test_graph_integration.py` (20 tests covering graph
compilation, node membership, conditional routing, full pipeline runs, budget exhaustion,
and error handling).

---

## Real-World Validation

Both execution paths were tested end-to-end with a valid `OPENAI_API_KEY`:

**Linear pipeline (`forged build`):** runs the full plan → code_author → executor →
student → reviser sequence, produces `lesson.ipynb` with real cell outputs, and writes
`SUMMARY.md` with the acceptance verdict.

**Agentic pipeline (`run_pipeline`):** the gate parser (`forged/gate.py`) had a bug where
a `94/100` verdict string was not parsed correctly. That was fixed. The pipeline ran
end-to-end, classified the result as `ACCEPTABLE`, and terminated cleanly. The routing log
had one entry; `state.is_terminal` was `True`.

---

## Current Capabilities

- Deterministic failure classification across 6 categories with auditable matched signals.
- Budget-aware routing that prevents infinite loops without relying on LLM judgment.
- Five real LLM agents (Planner, CodeAuthor, Student) with graceful degradation on
  error; Reviser and Executor are deterministic (no LLM).
- Full LangGraph graph that compiles, runs, and routes correctly.
- Complete immutable state trail: every routing decision is recorded in
  `state.routing_log` with classification, evidence, and timestamp.
- 285 tests passing (216 pipeline-specific), 88% overall coverage.

---

## Known Limitations

### ExecutorAgent is mocked

`ExecutorAgent._mock_execute()` always returns `{"ok": True, "failed_cells": [], "error_summary": null}`.
This means the agentic path never detects real notebook execution failures. The linear
pipeline's `ExecutorStage` runs actual notebooks via nbclient; that code exists but has not
yet been wired into `ExecutorAgent`. See Phase 7 below.

### RevisorAgent does not rewrite notebooks

`RevisorAgent` classifies the failure and records a routing decision. It does not produce
an artifact. When the pipeline reroutes to CodeAuthor or Planner, those agents see the same
brief they used the first time — they do not receive structured feedback about what
specifically failed. The routing decision is in `state.routing_log` but the agents do not
yet read it. See Phase 8 below.

### Budget exhaustion terminates without a deliverable

If a stage hits its budget before the pipeline reaches `ACCEPTABLE`, the run terminates
with `is_terminal=True` and a `"budget exhausted"` reason. No notebook is written to
the final output location. A human must inspect `state.outputs` to retrieve the last
artifact produced.

### No CLI command

The agentic pipeline is callable as `await run_pipeline(state, store, personas_dir)` from
Python. There is no `forged build --agentic` flag yet. See Phase 9 below.

---

## Architectural Roadmap

### Phase 7 — Wire the Real Executor

Replace `ExecutorAgent._mock_execute()` with a call to `forged.executor.ExecutorStage`.
The stage already exists and is tested; this is a wiring task, not a reimplementation.

Expected changes:
- `forged/pipeline/agents/executor.py`: call `ExecutorStage.run(notebook)`, parse the
  result into `ExecutionReport`.
- Add integration test that confirms a notebook with a failing cell produces
  `classification=CODE_QUALITY`.
- Update this document.

### Phase 8 — Add Reviser Rewriting

When the Reviser reroutes to CodeAuthor, CodeAuthor should receive structured feedback:
which cells failed, what the student found, what the routing decision was. Two options:

1. CodeAuthor reads the latest `student_grade_report_v{N}.json` and
   `execution_report_v{N}.json` from the store and includes findings in its prompt.
2. RevisorAgent writes a `revision_brief_v{N}.md` artifact with the synthesised feedback;
   CodeAuthor reads that artifact.

Option 2 keeps the agents decoupled and auditable. Whichever approach is chosen, the
`_build_user_prompt()` method in CodeAuthor and PlannerAgent needs updating.

### Phase 9 — Expose via CLI

Add `forged build --agentic` (or a separate subcommand) that:
1. Creates an `ArtifactStore` for the run.
2. Calls `run_pipeline(create_initial_state(), store, personas_dir)`.
3. Writes the final notebook from `state.outputs` to the run directory.
4. Writes a `SUMMARY.md` equivalent from `state.routing_log`.

This requires reading `state.outputs` to find the latest CodeAuthor artifact and
renaming/copying it to `lesson.ipynb` in the run directory. The `manifest.json` format
should be extended with `routing_log` entries for auditability.

---

## File Structure

```
forged/pipeline/
├── __init__.py                  # Public API exports
├── state.py                     # PipelineState and all supporting types
├── failure.py                   # classify() — 6 failure categories
├── router.py                    # Router, RoutingBudget, budget enforcement
├── graph.py                     # build_pipeline_graph(), run_pipeline()
└── agents/
    ├── __init__.py              # Agent ABC, AgentOutput
    ├── planner.py               # PlannerAgent (LLM)
    ├── code_author.py           # CodeAuthorAgent (LLM)
    ├── executor.py              # ExecutorAgent (mocked)
    ├── student.py               # StudentAgent (LLM)
    └── reviser.py               # RevisorAgent (deterministic)

tests/pipeline/
├── test_state.py                # Immutability, builders, validation
├── test_failure.py              # All 6 categories, determinism
├── test_router.py               # Budget enforcement, routing logic
├── test_agents.py               # Protocol: persona loading, fail-fast
├── test_agents_concrete.py      # Concrete agents: state transitions, artifacts
├── test_agents_llm.py           # LLM-wired agents: mock client, error handling
└── test_graph_integration.py    # Full graph: compilation, routing, E2E runs
```

---

## How to Extend

### Add a new failure category

1. Add the new value to `FailureCategory` in `forged/pipeline/failure.py`.
2. Add a matching priority check in `classify()` (early-return style, before ACCEPTABLE).
3. Add a routing rule in `Router.route()` in `forged/pipeline/router.py`.
4. Add a test in `tests/pipeline/test_failure.py` and `tests/pipeline/test_router.py`.

### Add a new agent

1. Create `forged/pipeline/agents/your_agent.py`; subclass `Agent[AgentOutput]`.
2. Implement `_load_persona()`, `next_stage()`, and `async run(state, store)`.
3. Add a persona file at `personas/your_agent.md`.
4. Wire the new node into `build_pipeline_graph()` in `graph.py`.
5. Add edge(s) and update the conditional routing mapping if needed.
6. Write tests in `tests/pipeline/test_agents_*.py`.

### Change routing budgets

Pass a custom `RoutingBudget` to `build_pipeline_graph()` (or to `RevisorAgent` directly in
tests). Default values are in `RoutingBudget` in `forged/pipeline/router.py`.
