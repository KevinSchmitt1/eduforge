# LangGraph Agentic Pipeline — Conceptual Guide

**For:** Understanding the "why" and "what" before diving into implementation
**Goal:** Build mental models for state schemas, failure classification, and agentic routing

---

## What Problem Are We Solving?

**Today (linear pipeline):**
```
Planner → CodeAuthor → Executor → Student → Reviewer
                                          ↓
                         Reviser → Executor → Student/Reviewer
                            ↑              ↓
                            └── fixed retry loop
```

The current revision policy can run a bounded revise/re-run/re-critique loop. That
is real progress over a one-shot pipeline, but it is still **fixed routing**:
every unresolved problem goes through the Reviser, then the Executor, then the
critics again. It can't say "the code is broken, send it back to CodeAuthor" or
"the plan is wrong, replan."

**Tomorrow (agentic pipeline):**
```
Planner → CodeAuthor → Executor → Student → Reviser
  ↑                                           ↓
  ↓ (can route back if structure is wrong)   ↓
  
  CodeAuthor ← (code is broken)
  ↑                                    
  ↓ (can fix code)
  
  Reviser ← (teaching is unclear)
  ↑
  ↓ (can edit prose)
```

The Reviser/router layer becomes **stage-aware**: it diagnoses what went wrong
and sends the notebook back to the right stage to fix it.

---

## Concept 1: Failure Classification

### The Problem It Solves

When the Reviser looks at a notebook and sees problems, how does it decide where to send it?

**Naive approach:** Ask the LLM "what's wrong?" and let it guess where to route.
- **Problem:** The LLM might say "confidence: 0.7" that the code is broken, or "I'm not sure if it's the plan or the code." Vague, expensive, unreliable.

**Better approach:** Ask the system directly — "Is the code broken? Is the plan wrong? Is the teaching unclear?"
- The system (executor, parser) already knows these answers from running the notebook.
- We don't need the LLM to guess — we can just *ask the facts*.

### How It Works

Failure classification reads **concrete signals** and maps them to **explicit categories**:

```
Signals we can observe:
  ├─ Executor report: "cell 3 raised NameError"  → CODE_QUALITY
  ├─ Executor report: "all cells ran OK"         → not code quality
  ├─ Finding: "[BLOCKER] scope:plan — lesson teaches X before Y"  → BLOCKER_STRUCTURE
  ├─ Finding: "[CONFUSING] — example is unclear"  → CONTENT_QUALITY
  └─ Quality score: 92 / 100                      → probably ACCEPTABLE

Classification: Priority cascade (first match wins)
  ├─ "Is there a plan-scope BLOCKER?" → BLOCKER_STRUCTURE
  ├─ "Did any cell fail?" → CODE_QUALITY
  ├─ "Do findings say output is wrong?" → TEST_FAILURE
  ├─ "Is quality score < minimum?" → CONTENT_QUALITY
  ├─ "Everything good?" → ACCEPTABLE
  └─ "Can't figure it out?" → UNCLASSIFIABLE (hand to human)
```

### Why This Matters

- **Deterministic**: Same signals → same classification every time. No LLM variance.
- **Auditable**: "The code failed, so we routed to CodeAuthor." You can trace why.
- **Testable**: Write a unit test: "given these signals, expect this category."
- **Efficient**: No extra LLM calls to decide routing — just read what the executor already told us.

---

## Concept 2: State Schema

### The Problem It Solves

When a notebook bounces between stages (Planner → CodeAuthor → Executor → Reviser → back to CodeAuthor → ...), we need to track:

- **Where is it right now?** (current stage)
- **What has it produced?** (each stage's output)
- **How many times have we sent it back to CodeAuthor?** (iteration budgets)
- **What routing decisions got made, and why?** (audit trail + evidence)

**Without a schema:** Nodes would have to guess what information is available. Routing logic would be scattered. Bugs would be hard to trace.

**With a schema:** There's one place that defines "this is what flows through the pipeline." Every node knows what's available.

### How It Works (Simple Example)

Imagine a "state" object that carries:

```
{
  run_id: "20260608-abc123",
  current_stage: "reviser",
  total_iterations: 3,
  
  outputs: [
    {stage: "planner", artifact: "lesson-v1.md", iter: 0},
    {stage: "code_author", artifact: "lesson-v2.ipynb", iter: 1},
    {stage: "student", artifact: "lesson-v2-graded.json", iter: 2},
  ],
  
  stage_attempts: {
    "planner": 1,
    "code_author": 2,
    "student": 1,
  },
  
  routing_log: [
    {
      iter: 0,
      from_stage: "reviser",
      classification: "code_quality",
      routed_to: "code_author",
      reason: "The code example no longer matches the requested hash-map topic.",
      evidence: [
        {
          source: "reviewer_feedback",
          severity: "BLOCKER",
          scope: "code",
          location: {
            type: "cell",
            cell_index: 5,
            label: "lookup example"
          },
          text: "Cell 5 demonstrates list sorting instead of hash-map lookup."
        }
      ]
    },
    {
      iter: 1,
      from_stage: "reviser",
      classification: "blocker_structure",
      routed_to: "planner",
      reason: "The lesson teaches collision handling before defining hashing.",
      evidence: [
        {
          source: "student_feedback",
          severity: "BLOCKER",
          scope: "plan",
          location: {
            type: "lesson_structure",
            label: "concept ordering"
          },
          text: "Collision handling appears before the learner knows what a hash function is."
        }
      ]
    },
  ]
}
```

Notice that `location` is flexible. Some problems are anchored to a notebook cell,
but others belong to a section, an artifact, the lesson structure, or the whole
notebook. The schema should not pretend every issue has a `cell`; it should store
the best available anchor:

```
location: {type: "cell", cell_index: 5, label: "lookup example"}
location: {type: "section", label: "Complexity discussion"}
location: {type: "lesson_structure", label: "concept ordering"}
location: {type: "artifact", label: "lesson_plan"}
location: {type: "global"}
```

At each step:
- Planner reads: "I'm stage 0, outputs contains my input, iteration count is 0"
- CodeAuthor reads: "I've been called twice already (`stage_attempts["code_author"] = 2`), if I fail again, the budget is exhausted"
- Reviser reads: "The routing log shows what happened before me, why it was routed there, and what evidence has already been acted on"

### Why This Matters

- **Budget tracking**: "We can safely route to CodeAuthor 1 more time (cap is 3, we've tried 2)"
- **Audit trail**: Reviewers can see the full journey and the evidence behind it:
  "The reviewer flagged a topic mismatch in the lookup example, so we routed to
  CodeAuthor; later the student flagged concept ordering, so we routed to Planner"
- **Immutability**: Each node doesn't mutate the state; it produces a new one. This is safer and easier to debug.

---

## Concept 3: How They Work Together

### The Journey of a Notebook

```
Step 1: Pipeline starts
  state = {current_stage: "planner", stage_attempts: {}}

Step 2: Planner runs
  → produces lesson-v1.ipynb
  → adds to state.outputs
  → state = {current_stage: "code_author", ...}

Step 3: CodeAuthor runs
  → produces lesson-v2.ipynb
  → state = {current_stage: "executor", ...}

Step 4: Executor runs
  → runs the notebook
  → report: {ok: false, failed_cells: 1}  ← SIGNAL
  → state = {current_stage: "student", ...}

Step 5: Student grades
  → finds: [BLOCKER] lesson structure — collision handling appears too early  ← SIGNAL
  → state = {current_stage: "reviser", ...}

Step 6: Reviser (the router) runs
  → Reads state, execution report, findings
  → Calls classify(report, findings, ...)
    ├─ "Is there a plan-scope BLOCKER?" → YES ← match!
    └─ Classification: BLOCKER_STRUCTURE
  
  → Calls route(state, BLOCKER_STRUCTURE)
    ├─ "Not acceptable" → continue
    ├─ "Not unclassifiable" → continue
    ├─ "Target stage: Planner"
    ├─ "Can we route there?" → state.stage_attempts["planner"] = 1 < 2 → YES
    └─ Return: {current_stage: "planner", stage_attempts: {"planner": 2}}
  
  → Adds routing decision plus evidence to state.routing_log
  → state = {current_stage: "planner", stage_attempts: {...}, routing_log: [decision]}

Step 7: Planner runs again
  → reads state: "The previous plan introduced collision handling too early"
  → revises the concept order
  → produces lesson-plan-v2.md
  → state = {current_stage: "code_author", ...}

... loop continues until ACCEPTABLE or budget exhausted ...
```

### The Three Pieces in Concert

| Piece | Role |
|-------|------|
| **Failure Classification** | Diagnoses "what went wrong" from concrete signals (deterministic, auditable) |
| **State Schema** | Carries information between stages + tracks budgets (what's available, how much budget left) |
| **Routing Logic** | Uses classification + state to decide the next stage (deterministic, testable) |

---

## Why LangGraph?

LangGraph is a library for building stateful, multi-step agent workflows. It provides:

1. **State passing**: Pass the state object between nodes automatically
2. **Conditional edges**: Based on state, route to different nodes ("if classification is CODE_QUALITY, go to CodeAuthor")
3. **Checkpointing**: Save state at each step (for resume/audit)
4. **Visualization**: See the flow visually

Without LangGraph, we'd have to write our own loop: "while not done, check state, route, repeat." LangGraph gives us the framework so we can focus on the business logic (classification, routing) instead of the plumbing.

---

## Key Insight: Why Deterministic Routing Matters

In the linear pipeline, the Reviser is like a human editor with a vague checklist:

> "Is this good?" — "No, I'm not happy with the quality."
> 
> OK but *why*? And where should it go?

In the agentic pipeline, the Reviser is more like a diagnostician:

> "Executor says: cell 3 raised NameError. → CODE_QUALITY → Route to CodeAuthor."

This is:
- **Predictable**: The same error always goes to the same stage
- **Auditable**: The log shows exactly why each routing decision was made
- **Efficient**: No wasted LLM calls to debate where to route
- **Safe**: Iteration budgets prevent infinite loops

---

## Next: Implementation

When you're ready to build, the steps are:

1. **Create the state schema** (`state.py`) — define the object that flows through the graph
2. **Implement classification** (`router.py`) — the deterministic "read signals, output category" logic
3. **Implement routing** (`router.py`) — "category + budget → next stage"
4. **Wire LangGraph** (`graph.py`) — nodes + edges that use the routing logic

All three pieces are testable in isolation before you wire them together in LangGraph.
