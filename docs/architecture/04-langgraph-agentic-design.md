# LangGraph Agentic Pipeline — Architecture Design

**Status:** Design phase (not yet implemented)
**Date:** 2026-06-08
**Context:** Migrating from linear orchestration to agentic routing with explicit failure classification

---

## Overview

This document captures the detailed architecture design for forged's LangGraph agentic pipeline. The design addresses three core questions:

1. **How does the Reviser decide where to send feedback?** → Failure Classification System
2. **What information flows through the pipeline?** → PipelineState Schema
3. **What are the routing rules?** → Routing Logic

---

## Design Sections

### 1. Failure Classification System

The Reviser examines notebook output and classifies **what went wrong** using explicit categories:

- `BLOCKER_STRUCTURE` — plan is fundamentally broken (structure/scope wrong)
- `CODE_QUALITY` — code won't run (syntax, runtime error, etc.)
- `TEST_FAILURE` — code runs but produces wrong output
- `CONTENT_QUALITY` — code is correct but teaching is below bar (confusing prose, weak examples)
- `ACCEPTABLE` — output is good enough to ship
- `UNCLASSIFIABLE` — can't diagnose (hand to human)

Each category routes back to a specific earlier stage (or ends the pipeline).

**Why not "confidence"?** Confidence is vague and model-dependent. Classification is deterministic: given the same signals (executor report, parsed findings), the same class always results. This makes the router auditable and testable offline.

### 2. PipelineState Schema

The state object that flows through LangGraph, carrying:

- **Where we are**: `current_stage`, `total_iterations`
- **What we produced**: `outputs` (artifact names, not content)
- **Budget tracking**: `stage_attempts` (how many times we re-entered each stage)
- **Audit trail**: `routing_log` (every routing decision with machine-readable
  evidence and a human-readable reason)
- **Terminal conditions**: `needs_human`, `human_reason`

**Why a schema?** LangGraph nodes pass state between each other. The schema defines the "contract" — what information is available at each node, how to check budgets, how to record decisions. Without it, nodes would have to guess about what's in memory and routing would be unpredictable.

Evidence should use a flexible `location` object, not a required `cell` field.
Some findings are anchored to a cell, but others belong to a section, the lesson
plan, the concept order, an artifact, or the whole notebook.

### 3. Routing Logic

Two pure functions that make routing deterministic:

- **`classify()`** — reads signals (executor report, findings, quality score) → outputs a `FailureClass`
- **`route()`** — takes a `FailureClass` + current budget → outputs the next `Stage` (or escalates if capped)

**Why pure functions?** Testable offline, reproducible, immune to LLM phrasing drift. The LLM Reviser *explains why*; the router *decides where* based on facts.

---

## Decide-Later Items

The design flags 5 items to refine during implementation:

1. **Scope tagging source** — Should critics emit `scope:plan` tags, or infer them from signals?
2. **State representation** — Frozen dataclass vs. LangGraph reducers?
3. **HUMAN_REVIEW terminal behavior** — Write SUMMARY + exit, or interactive checkpoint?
4. **Keep-best across replans** — Does the gate still work when candidates diverge?
5. **Executor re-run idempotency** — Cap at 1 re-run for deterministic cells?

---

## Next Steps

1. **Understand the concepts** — Read `docs/architecture/04-conceptual-guide.md` to understand what state schemas and failure classification are really for
2. **Implement incrementally** — Convert `orchestrator.py` → `orchestrator/` package, build one piece at a time
3. **Refine decide-later items** — Make calls on scope tagging, state representation, etc. during implementation

---

## Reference Files

- Current linear orchestrator: `forged/orchestrator.py` (lines 205–273 for the revision loop)
- Gate rules: `forged/gate.py` (lines 58–80, 131–151)
- Findings parser: `forged/ledger.py` (line 31 for `_FINDING_LINE`)
- Executor report: `forged/executor.py` (lines 94–101)

Future home for agentic code:
```
forged/orchestrator/
├── __init__.py
├── base.py           # shared agent interface
├── linear/
│   ├── __init__.py
│   └── orchestrator.py
└── agentic/
    ├── __init__.py
    ├── state.py      # PipelineState schema
    ├── router.py     # Failure classification + routing logic
    ├── nodes.py      # Agent node wrappers
    ├── graph.py      # LangGraph definition
    └── integration.py  # Langfuse instrumentation
```
