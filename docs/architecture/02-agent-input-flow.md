# Agent Input Flow — Step 2 Design

**Status:** Step 2 of input layer redesign
**Purpose:** Map how structured inputs (learner profile, topic spec, assessment approach) flow through agents
**Previous:** [01-input-specification.md](01-input-specification.md) — defines what data users provide

---

## Overview

Currently, the orchestrator passes a simple brief to agents. With structured inputs, each agent gets richer context and uses it differently:

```
User Input (Profile + Topic + Assessment)
    ↓
Orchestrator.run() receives structured inputs
    ↓
┌─────────────────────────────────────────┐
│ Stage 1: Planner (LLMAgent)             │
│ Input: learner profile + topic spec     │
│ Output: lesson_plan.md                  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Stage 2: Code Author (LLMAgent)         │
│ Input: lesson plan + topic spec + prof  │
│ Output: notebook.ipynb                  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Stage 3: Executor (ExecutorStage)       │
│ Input: notebook                         │
│ Output: execution_report.json           │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Stage 4: Student (LLMAgent)             │
│ Input: notebook + execution report      │
│ Output: student_feedback.md             │
└─────────────────────────────────────────┘
    ↓
[Optional Revision Loop]
    ↓
┌─────────────────────────────────────────┐
│ Stage 5: Assessment (NEW)               │
│ Input: notebook + assessment_approach   │
│ Output: project_spec.md OR test.py      │
└─────────────────────────────────────────┘
```

---

## Detailed Agent-by-Agent Flow

### Stage 1: Planner

**Input Data:**
```python
{
    "learner_profile": LearnerProfile,
    "topic_spec": TopicSpecification,
    "brief": str,  # The original brief
    "material_density": str  # dense, standard, rich
}
```

**Current Prompt (simplified):**
```
Topic: {brief}
Generate a lesson plan that covers the essential learning objectives.
```

**Enhanced Prompt:**

```
You are an expert educator designing a lesson plan.

## Learner Context
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}
- Environment: {environment}
- Background: {background_context}

## Topic & Scope
- Title: {topic_title}
- Scope: {scope}  (fundamentals / implementation / optimization / usage)
- Learning Objectives (MANDATORY, do not reduce):
  {learning_objectives as bullet list}
- Prerequisites: {prerequisites}
- Constraints: {constraints}
- Focus Areas (priority order): {focus_areas}

## Delivery Style
- Material Density: {material_density}
  - If "dense": terse explanations, 1 canonical example per concept
  - If "standard": balanced explanations, 2-3 examples per concept
  - If "rich": elaborate explanations, multiple examples, extension ideas
- Tailor explanation depth to: {prior_knowledge}

## Task
Create a lesson plan (markdown) that:
1. Lists learning objectives (unchanged from input)
2. Breaks objectives into logical sections
3. For each section, specify:
   - What concept to introduce (with explanation density guidance)
   - What examples to include (quantity based on material_density)
   - Key code snippets or pseudocode
   - Depth of math/theory (if applicable)
4. Respect the constraints: {constraints}
5. Emphasize focus_areas in priority order
6. Estimate lines of code and explanation per section
7. Include assessment guidance: hint at how each objective will be validated

## Output Format
Markdown with clear sections and subsections. Include metadata:
- Total estimated notebook length
- Assessment hook (what will validate each objective)
```

**Output Artifacts:**
- `lesson_plan.md` — detailed structure with section guidance

**How This Feeds Forward:**
- Code Author uses section structure and example count guidance
- Assessment stage uses "assessment hook" notes to validate objectives

---

### Stage 2: Code Author

**Input Data:**
```python
{
    "lesson_plan": str,  # from Planner
    "learner_profile": LearnerProfile,
    "topic_spec": TopicSpecification,
    "material_density": str,
    "environment": str  # jupyter_notebook, colab, etc.
}
```

**Current Prompt (simplified):**
```
Based on this lesson plan, write a Jupyter notebook.
Include explanations and code cells.
```

**Enhanced Prompt:**

```
You are an expert code educator writing a Jupyter notebook.

## Learner Context
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}
- Environment: {environment}

## Content Structure
See lesson plan: {lesson_plan}

## Coding Style & Explanation
- Material Density: {material_density}
  - If "dense": minimal comments, terse markdown, assumes reader can infer
  - If "standard": helpful comments, markdown explanations after code
  - If "rich": detailed comments, walkthrough explanations, multiple runs of same concept
- Code complexity: {scope determines this}
  - fundamentals → simple, readable code
  - implementation → working implementation with comments
  - optimization → includes performance considerations
- Comment style: tailored to {prior_knowledge}
  - Beginner: explain what each line does
  - Intermediate: explain why each line is there
  - Advanced: focus on non-obvious decisions

## Notebook Structure
- Cell 0: Title + learning objectives
- Cell 1-N: One section per lesson plan section
  - Markdown cell: explanation (density: {material_density})
  - Code cell: example (with comments per {material_density})
  - [Optional] Code cell: interactive variant for hands-on learners
- Final cells: Summary + what to do next

## Task
1. Convert lesson plan into notebook cells
2. Write code that runs without errors
3. Add comments/explanations matching {material_density}
4. Use examples from lesson plan (quantity: {material_density})
5. Avoid hardcoding outputs; all code must execute
6. Preserve assessment hooks (e.g., "After running this, student should understand...")

## Output Format
Valid Jupyter notebook (`.ipynb`) with clear cell metadata and outputs.
```

**Output Artifacts:**
- `notebook.ipynb` — executable notebook with explanations

**How This Feeds Forward:**
- Executor runs the notebook and generates execution report
- Student reviews the notebook + execution report
- Assessment stage validates objectives using code execution results

---

### Stage 3: Executor

**Input Data:**
```python
{
    "notebook": str,  # notebook.ipynb content
    "environment": str
}
```

**Current Behavior:**
Runs notebook kernel, captures outputs, errors, execution time.

**Enhanced Behavior:**
Same execution, but:
- Track which cells validate which learning objectives (from assessment hooks in lesson plan)
- Capture both stdout/stderr AND structured outputs (e.g., test results)
- Time per cell, not just per notebook

**Output Artifacts:**
- `execution_report.json` — execution results with objective mapping

**Data Produced for Assessment:**
```json
{
  "total_runtime": 45.2,
  "cells": [
    {
      "cell_index": 0,
      "type": "markdown",
      "output": null
    },
    {
      "cell_index": 1,
      "type": "code",
      "assessment_hook": "Understand hash functions",
      "executed": true,
      "output": "...",
      "error": null,
      "runtime": 0.5
    }
  ]
}
```

---

### Stage 4: Student

**Input Data:**
```python
{
    "notebook": str,  # notebook.ipynb (with outputs)
    "execution_report": dict,
    "learner_profile": LearnerProfile,
    "topic_spec": TopicSpecification,
    "material_density": str
}
```

**Current Prompt (simplified):**
```
Review this notebook. Is it clear? Are the learning objectives met?
```

**Enhanced Prompt:**

```
You are an expert learner reviewing this educational material.

## Your Perspective
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}
- Background: {background_context}

## Material Evaluation
Review the notebook against these non-negotiable learning objectives:
{learning_objectives as numbered list}

For each objective, assess:
1. **Clarity**: Is the explanation understandable to {prior_knowledge} level?
2. **Completeness**: Is the objective fully addressed?
3. **Execution**: Did the code run successfully? ({execution_report})
4. **Pedagogical Soundness**: Does the explanation match {learning_style}?

## Density Appropriateness
Material density is set to: {material_density}
- If "dense": Is it too terse? Are important steps skipped?
- If "standard": Is the balance right? Too much/little explanation?
- If "rich": Is it too verbose? Does it maintain engagement?

## Scope Appropriateness
Scope is: {scope}
- fundamentals: Does it explain concepts without overwhelming with code?
- implementation: Does it teach writing code from scratch?
- optimization: Does it address performance appropriately?

## Task
Provide structured feedback (markdown):
1. Objective-by-objective assessment (met / partially met / not met)
2. Clarity issues (specific paragraphs/cells to improve)
3. Code issues (does it actually work? Edge cases missed?)
4. Pedagogical gaps (what a {prior_knowledge} learner might struggle with)
5. Density feedback (too much/too little explanation)
6. Overall verdict: 0-100 quality score

Focus on SUBSTANCE, not formatting. Don't suggest cutting content to hit density targets;
instead, suggest rephrasing or reorganizing to improve clarity.
```

**Output Artifacts:**
- `student_feedback.md` — detailed review with objective-by-objective assessment

**Assessment Criteria for Gate:**
The gate evaluates student feedback to decide: "Is this notebook good enough?"

---

### Stage 5: Assessment (NEW)

**Input Data:**
```python
{
    "notebook": str,  # executed notebook with outputs
    "execution_report": dict,
    "learner_profile": LearnerProfile,
    "topic_spec": TopicSpecification,
    "assessment_approach": AssessmentApproach,
    "student_feedback": str  # from Stage 4
}
```

**Purpose:** Generate a validation exercise (project spec OR knowledge test) that lets the learner prove they've met the learning objectives.

**Two Paths:**

#### Path A: Project-Based Assessment

**Prompt:**

```
You are designing a project that validates learning.

## Learning Objectives (must all be validated)
{learning_objectives as numbered list}

## Learner Context
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}

## Project Approach
{assessment_approach.project.description}

## Task
Create a project specification (markdown) that:
1. Clearly states the goal (e.g., "Implement a hash map class")
2. Provides starter code or skeleton (function signatures + docstrings)
3. Lists 5-10 test cases the learner must pass
4. Maps each test case to a learning objective
5. Includes hints (not solutions) for tricky parts
6. Provides estimated time to complete (based on {material_density} and {prior_knowledge})
7. Includes extension/bonus challenges for deeper mastery

## Structure
- Overview (what learner will build)
- Starter code (copy-pasteable, with TODO comments)
- Test cases (in Python, runnable)
- Hints by test (if helpful)
- Bonus challenges (optional depth)

## Difficulty Calibration
Difficulty: {assessment_difficulty}
- "matches_topic": should be achievable in 30-60 min with the notebook
- "slightly_harder": requires synthesizing concepts
- "significantly_harder": requires research or creative problem-solving
```

**Output Artifacts:**
- `project_spec.md` — project description
- `project_starter.py` — starter code with TODOs
- `project_tests.py` — test suite to validate

---

#### Path B: Knowledge Test

**Prompt:**

```
You are designing a knowledge test.

## Learning Objectives (must all be tested)
{learning_objectives}

## Test Format
{assessment_approach.knowledge_test.format}

## Task
Create {assessment_approach.knowledge_test.count} test items:
1. Each should validate ONE learning objective
2. Include model solutions or answer keys
3. Difficulty: {assessment_difficulty}
4. Tailor language to {prior_knowledge}
5. Avoid trick questions; test understanding, not memorization

## Test Item Structure
For each item:
- Question (clear, unambiguous)
- Answer key (with explanation of why it's correct)
- Difficulty rating (1-5)
- Which objective it validates
```

**Output Artifacts:**
- `knowledge_test.md` — test questions and answer keys

---

## Input Flow through Orchestrator

The orchestrator needs to be modified to:

```python
class Orchestrator:
    def run(
        self,
        brief: str,
        learner_profile: LearnerProfile,
        topic_spec: TopicSpecification,
        assessment_approach: AssessmentApproach,
        on_stage=None,
    ) -> ArtifactStore:
        """Execute pipeline with structured inputs."""
        store = ArtifactStore.create(self._runs_root, self._pipeline.name)
        
        # Seed store with all input context
        store.put(Artifact("learner_profile", "json", serialize(learner_profile)))
        store.put(Artifact("topic_spec", "json", serialize(topic_spec)))
        store.put(Artifact("assessment_approach", "json", serialize(assessment_approach)))
        
        # Run each stage with richer context
        for stage in self._pipeline.stages:
            _run_stage(
                stage,
                store,
                context={  # NEW: pass structured context
                    "learner_profile": learner_profile,
                    "topic_spec": topic_spec,
                    "assessment_approach": assessment_approach,
                    "material_density": learner_profile.material_density,
                },
                on_stage,
            )
        
        # Optionally run assessment stage
        if assessment_approach is not None:
            _run_assessment_stage(store, assessment_approach, learner_profile, topic_spec)
```

---

## Summary: How Inputs Shape Each Stage

| Stage | Input Used | How It Changes Behavior |
|-------|-----------|------------------------|
| **Planner** | profile + topic_spec + material_density | Section structure, explanation depth, example count guidance |
| **Code Author** | profile + topic_spec + material_density + lesson plan | Code comments, explanation length, example quantity, complexity level |
| **Executor** | (unchanged) | Same execution, but tracks objective-by-objective |
| **Student** | profile + topic_spec + material_density + notebook + exec report | Evaluation rubric tailored to learner level and density expectations |
| **Assessment** (NEW) | profile + topic_spec + assessment_approach + notebook | Type of assessment (project vs. test), difficulty calibration, objective validation |

---

## Key Changes to Existing Code

### 1. Orchestrator.run() signature
```python
# OLD
def run(self, brief: str, profile: str, ...) -> ArtifactStore:

# NEW
def run(
    self,
    brief: str,
    learner_profile: LearnerProfile,
    topic_spec: TopicSpecification,
    assessment_approach: AssessmentApproach,
    ...
) -> ArtifactStore:
```

### 2. LLMAgent prompt construction
```python
# OLD
prompt = f"Topic: {brief}. Write a lesson plan."

# NEW
prompt = self._render_prompt_with_context(
    stage_name="planner",
    context={
        "learner_profile": learner_profile,
        "topic_spec": topic_spec,
        "material_density": material_density,
    }
)
```

### 3. Executor output enrichment
```python
# OLD
return {"cells": [...], "total_runtime": X}

# NEW
return {
    "cells": [...],
    "total_runtime": X,
    "objective_coverage": {  # Maps objectives to executed cells
        "objective_1": {"cells": [1, 3], "validated": True},
        "objective_2": {"cells": [5], "validated": True},
    }
}
```

### 4. New Assessment Stage
```python
# NEW
class AssessmentStage:
    def run(self, store: ArtifactStore, context: dict) -> Artifact:
        assessment_approach = context["assessment_approach"]
        if assessment_approach.type == "project":
            return self._generate_project(store, context)
        elif assessment_approach.type == "knowledge_test":
            return self._generate_test(store, context)
```

---

## Next Steps (After Approval of Step 2)

1. **Step 3:** Sketch the assessment stage implementation details
2. **Step 4:** Write code changes (modify orchestrator, agent prompts, executor)
3. **Step 5:** Update CLI to accept structured input (profile YAML)
4. **Step 6:** Document with examples and test

---

## Questions for Review

1. Does the flow through each agent make sense pedagogically?
2. Should the Student stage also see material_density expectations, or just evaluate output?
3. Should Executor track "which cells validate which objectives" automatically, or should Planner annotate cells with assessment hooks?
4. For Assessment stage, should we generate BOTH project AND test, or let user choose?
5. Any missing context that agents would need to do their job well?
