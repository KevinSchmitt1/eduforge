# Implementation Plan — Step 3

**Status:** Technical specification for code implementation
**Purpose:** Detailed file-by-file changes to implement structured input specification and agent input flow
**Previous:** [01-input-specification.md](01-input-specification.md) (what to build) and [02-agent-input-flow.md](02-agent-input-flow.md) (how agents use it)

---

## Overview

This plan outlines concrete code changes to accept and use structured inputs (learner profile, topic spec, assessment approach) throughout the pipeline.

**Scope:**
- Data models (Pydantic dataclasses)
- CLI argument parsing (YAML files)
- Orchestrator changes (pass context to agents)
- Agent prompt rendering (context-aware prompts)
- New Assessment stage
- Backward compatibility (--topic alone still works)

---

## 1. New File: `forged/models.py`

**Purpose:** Define structured input data models

**Content:**

```python
"""Data models for structured inputs."""

from dataclasses import dataclass
from typing import Literal

@dataclass
class LearnerProfile:
    """Describes the learner and how content should be shaped."""
    name: str
    description: str
    prior_knowledge: list[str]
    environment: Literal[
        "jupyter_notebook",
        "google_colab",
        "vscode",
        "ide",
        "cli",
        "book",
    ]
    material_density: Literal["dense", "standard", "rich"]
    learning_style: Literal[
        "socratic",
        "project_based",
        "visual",
        "hands_on",
        "reference",
    ]
    background_context: str

    @classmethod
    def from_yaml(cls, path: str) -> "LearnerProfile":
        """Load from YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_prompt_context(self) -> dict:
        """Format for use in LLM prompts."""
        return {
            "name": self.name,
            "prior_knowledge": "\n  - ".join(self.prior_knowledge),
            "environment": self.environment,
            "material_density": self.material_density,
            "learning_style": self.learning_style,
            "background_context": self.background_context,
        }


@dataclass
class TopicSpecification:
    """Defines what should be learned."""
    title: str
    scope: Literal["fundamentals", "implementation", "optimization", "usage"]
    learning_objectives: list[str]
    prerequisites: list[str]
    constraints: str
    depth: Literal["beginner", "intermediate", "advanced"]
    focus_areas: list[str]

    @classmethod
    def from_yaml(cls, path: str) -> "TopicSpecification":
        """Load from YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_prompt_context(self) -> dict:
        """Format for use in LLM prompts."""
        return {
            "title": self.title,
            "scope": self.scope,
            "learning_objectives": "\n  - ".join(self.learning_objectives),
            "prerequisites": "\n  - ".join(self.prerequisites),
            "constraints": self.constraints,
            "depth": self.depth,
            "focus_areas": "\n  - ".join(self.focus_areas),
        }


@dataclass
class ProjectAssessment:
    """Project-based assessment specification."""
    description: str
    starter_context: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    time_estimate: str


@dataclass
class KnowledgeTest:
    """Knowledge test specification."""
    format: Literal[
        "multiple_choice",
        "fill_in_code",
        "conceptual_questions",
        "exercises",
    ]
    count: int
    difficulty: Literal["beginner", "intermediate", "advanced"]


@dataclass
class AssessmentApproach:
    """How learning should be validated."""
    type: Literal["project", "knowledge_test", "both"]
    project: ProjectAssessment | None = None
    knowledge_test: KnowledgeTest | None = None
    assessment_difficulty: Literal[
        "matches_topic",
        "slightly_harder",
        "significantly_harder",
    ] = "matches_topic"

    @classmethod
    def from_yaml(cls, path: str) -> "AssessmentApproach":
        """Load from YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        # Handle nested objects
        if "project" in data and data["project"]:
            data["project"] = ProjectAssessment(**data["project"])
        if "knowledge_test" in data and data["knowledge_test"]:
            data["knowledge_test"] = KnowledgeTest(**data["knowledge_test"])
        return cls(**data)
```

**Changes Summary:**
- Add Pydantic validation to ensure YAML values are valid
- Add `from_yaml()` class method for file loading
- Add `to_prompt_context()` for rendering into prompts

---

## 2. Modified: `forged/cli.py`

**Current CLI:**
```bash
forged build --topic "..." --profile profiles/default.md --config config/...
```

**Changes:**

### Add argument parsing for structured inputs

```python
import argparse
from pathlib import Path
from .models import LearnerProfile, TopicSpecification, AssessmentApproach

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="...")
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # BUILD command
    build = subparsers.add_parser("build", help="Build a lesson notebook")
    
    # Required
    build.add_argument(
        "--topic",
        required=True,
        help="Topic to teach (e.g., 'How hash maps work')",
    )
    
    # Input specification (can be file-based or minimal)
    build.add_argument(
        "--learner-profile",
        type=Path,
        help="Path to learner_profile.yaml (optional; uses defaults if omitted)",
    )
    build.add_argument(
        "--topic-spec",
        type=Path,
        help="Path to topic_specification.yaml (optional; uses defaults if omitted)",
    )
    build.add_argument(
        "--assessment",
        type=Path,
        help="Path to assessment_approach.yaml (optional; skips assessment if omitted)",
    )
    
    # Pipeline selection (existing)
    build.add_argument(
        "--config",
        type=Path,
        default=...,
        help="Pipeline config to use",
    )
    build.add_argument(
        "--runs",
        type=Path,
        default="./runs",
        help="Output directory for runs",
    )
    
    return parser


def main():
    args = _build_parser().parse_args()
    
    if args.command == "build":
        _handle_build(args)
    # ... other commands


def _handle_build(args):
    """Execute build command with structured inputs."""
    # Load structured inputs (or use defaults)
    learner_profile = (
        LearnerProfile.from_yaml(args.learner_profile)
        if args.learner_profile
        else _default_learner_profile()
    )
    
    topic_spec = (
        TopicSpecification.from_yaml(args.topic_spec)
        if args.topic_spec
        else _default_topic_spec(args.topic)
    )
    
    assessment_approach = (
        AssessmentApproach.from_yaml(args.assessment)
        if args.assessment
        else None
    )
    
    # Load pipeline and orchestrator (existing)
    config = load_pipeline_config(args.config)
    orchestrator = Orchestrator(
        pipeline=config,
        personas_dir=PERSONAS_DIR,
        runs_root=args.runs,
    )
    
    # Run with structured inputs
    try:
        store = orchestrator.run(
            brief=args.topic,
            learner_profile=learner_profile,
            topic_spec=topic_spec,
            assessment_approach=assessment_approach,
            on_stage=_progress_callback,
        )
        _report_success(store)
    except Exception as e:
        _report_error(e, store.last_run_dir if store else None)
        sys.exit(1)


def _default_learner_profile() -> LearnerProfile:
    """Sensible defaults when no profile is provided."""
    return LearnerProfile(
        name="Default Learner",
        description="Self-study for professional development",
        prior_knowledge=["Basic understanding of the topic"],
        environment="jupyter_notebook",
        material_density="standard",
        learning_style="hands_on",
        background_context="Self-directed learning; prefers practical examples",
    )


def _default_topic_spec(topic: str) -> TopicSpecification:
    """Sensible defaults when no topic spec is provided."""
    return TopicSpecification(
        title=topic,
        scope="implementation",
        learning_objectives=[f"Understand {topic}"],
        prerequisites=[],
        constraints="",
        depth="intermediate",
        focus_areas=[topic],
    )
```

**Summary of Changes:**
- Add `--learner-profile`, `--topic-spec`, `--assessment` arguments
- Parse YAML files into data models
- Provide sensible defaults if files not provided
- Pass structured inputs to orchestrator

---

## 3. Modified: `forged/orchestrator.py`

**Current signature:**
```python
def run(self, brief: str, profile: str, ...) -> ArtifactStore:
```

**New signature:**
```python
def run(
    self,
    brief: str,
    learner_profile: LearnerProfile,
    topic_spec: TopicSpecification,
    assessment_approach: AssessmentApproach | None = None,
    on_stage=None,
) -> ArtifactStore:
```

**Changes:**

```python
from .models import (
    LearnerProfile,
    TopicSpecification,
    AssessmentApproach,
)

class Orchestrator:
    def run(
        self,
        brief: str,
        learner_profile: LearnerProfile,
        topic_spec: TopicSpecification,
        assessment_approach: AssessmentApproach | None = None,
        on_stage=None,
    ) -> ArtifactStore:
        """Execute pipeline with structured inputs.
        
        Args:
            brief: Original topic string (e.g., "How hash maps work")
            learner_profile: LearnerProfile object
            topic_spec: TopicSpecification object
            assessment_approach: Optional AssessmentApproach object
            on_stage: Progress callback
        """
        store = ArtifactStore.create(self._runs_root, self._pipeline.name)
        self._last_run_dir = store.run_dir
        self._timings = {}
        
        # Seed store with context (for agents and assessor to reference)
        store.put(Artifact(
            name="learner_profile",
            kind="json",
            content=json.dumps(asdict(learner_profile)),
        ))
        store.put(Artifact(
            name="topic_spec",
            kind="json",
            content=json.dumps(asdict(topic_spec)),
        ))
        if assessment_approach:
            store.put(Artifact(
                name="assessment_approach",
                kind="json",
                content=json.dumps(asdict(assessment_approach)),
            ))
        store.put(Artifact(name="brief", kind="text", content=brief))
        
        # Build context dict for agents
        context = {
            "learner_profile": learner_profile,
            "topic_spec": topic_spec,
            "assessment_approach": assessment_approach,
            "brief": brief,
        }
        
        # Run pipeline stages with context
        for stage in self._pipeline.stages:
            _run_stage(
                stage,
                store,
                self._runner_factory,
                self._pipeline.name,
                on_stage,
                self._timings,
                context=context,  # NEW: pass context
            )
        
        # Revision loop (unchanged)
        runtime_pipeline = self._pipeline
        if self._pipeline.revision is not None:
            runtime_pipeline = self._revise_loop(store, on_stage)
        
        # Finalize (mostly unchanged, but pass context)
        self._finalize(
            store,
            brief,
            "profile",  # label for SUMMARY.md
            runtime_pipeline,
            context=context,
        )
        
        # Optional: Run assessment stage
        if assessment_approach is not None:
            _run_assessment_stage(
                store,
                assessment_approach,
                context,
                self._runner_factory,
            )
        
        return store
```

**Key changes:**
- Accept LearnerProfile, TopicSpecification, AssessmentApproach as dataclass objects
- Build context dict with all inputs
- Pass context to _run_stage() and assessment stage
- Store inputs as artifacts (for reference/debugging)

---

## 4. Modified: `forged/agent.py`

**Current:**
```python
class LLMAgent:
    def run(self, store: ArtifactStore) -> Artifact:
        """Execute an LLM stage."""
        prompt = self._build_prompt(store)
        response = call_llm(prompt)
        return self._process_response(response)
    
    def _build_prompt(self, store: ArtifactStore) -> str:
        """Generic prompt from brief."""
        brief = store.get("brief").content
        return f"Topic: {brief}\nGenerate a lesson plan."
```

**New:**
```python
class LLMAgent:
    def run(
        self,
        store: ArtifactStore,
        context: dict | None = None,
    ) -> Artifact:
        """Execute an LLM stage with optional context."""
        prompt = self._build_prompt(store, context=context)
        response = call_llm(prompt)
        return self._process_response(response)
    
    def _build_prompt(self, store: ArtifactStore, context: dict | None = None) -> str:
        """Build stage-specific prompt with context."""
        # Get the stage-specific prompt template
        template_key = f"{self._stage.name}_prompt"
        
        # Load template from a prompt library
        template = PROMPT_TEMPLATES.get(
            template_key,
            self._default_prompt_template(),
        )
        
        # Build context dict for rendering
        render_context = {
            "brief": store.get("brief").content,
            "lesson_plan": (
                store.get("lesson_plan").content
                if store.has("lesson_plan")
                else ""
            ),
        }
        
        # Add learner/topic context if available
        if context and "learner_profile" in context:
            render_context.update(
                context["learner_profile"].to_prompt_context()
            )
        
        if context and "topic_spec" in context:
            render_context.update(
                context["topic_spec"].to_prompt_context()
            )
        
        # Render template with context
        return template.format(**render_context)
    
    def _default_prompt_template(self) -> str:
        """Fallback generic prompt if no context."""
        brief = store.get("brief").content
        return f"Topic: {brief}\n\nGenerate content for this stage."
```

**New file: `forged/prompts.py`**

```python
"""Prompt templates for each agent stage."""

PROMPT_TEMPLATES = {
    "planner_prompt": """You are an expert educator designing a lesson plan.

## Learner Context
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}
- Environment: {environment}
- Background: {background_context}

## Topic & Scope
- Title: {title}
- Scope: {scope}
- Learning Objectives (MANDATORY, do not reduce):
{learning_objectives}
- Prerequisites: {prerequisites}
- Constraints: {constraints}
- Focus Areas: {focus_areas}

## Delivery Style
- Material Density: {material_density}
  - dense: terse, 1 example per concept
  - standard: balanced, 2-3 examples
  - rich: elaborate, multiple examples + extensions

## Task
Create a lesson plan that:
1. Lists learning objectives (unchanged)
2. Breaks into logical sections
3. Specifies explanation depth per section (based on material_density)
4. Respects constraints
5. Emphasizes focus_areas in priority order

Output: Markdown with clear sections, estimated code lines per section.
""",
    
    "code_author_prompt": """You are an expert code educator writing a Jupyter notebook.

## Learner Context
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}
- Environment: {environment}

## Content Structure
See lesson plan from previous stage.

## Coding Style
- Material Density: {material_density}
  - dense: minimal comments, terse markdown
  - standard: helpful comments, explanations after code
  - rich: detailed comments, walkthroughs, multiple runs
- Scope: {scope}
  - fundamentals → simple, readable code
  - implementation → working implementation with comments
  - optimization → includes performance
- Code Complexity: tailored to {depth} level

## Task
Convert lesson plan into executable Jupyter notebook:
1. Cell 0: Title + objectives
2. Cells 1-N: One section per lesson plan section
3. Comments/explanations matching material_density
4. All code must run without errors
5. Include examples (qty based on material_density)

Output: Valid .ipynb notebook.
""",
    
    "student_prompt": """You are an expert learner reviewing educational material.

## Your Perspective
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}
- Background: {background_context}

## Evaluation Criteria
Review against learning objectives:
{learning_objectives}

For each objective, assess:
1. Clarity: Is it understandable to {depth} level?
2. Completeness: Is objective fully addressed?
3. Execution: Did code run successfully?
4. Pedagogy: Does it match {learning_style}?

Material Density is set to: {material_density}
- Is it appropriate (too much/too little)?

## Task
Provide structured feedback (markdown):
1. Objective-by-objective (met / partial / not met)
2. Clarity issues (specific cells/sections to improve)
3. Code issues (does it work? Edge cases?)
4. Pedagogical gaps (what learner might struggle with)
5. Density feedback (too verbose/terse?)
6. Quality score: 0-100

Output: Detailed markdown review.
""",
}
```

**Summary of Changes:**
- Pass context dict to LLMAgent.run()
- Render stage-specific prompts with learner/topic context
- Use PROMPT_TEMPLATES dict for easy editing
- Fallback to generic prompts if no context

---

## 5. New File: `forged/assessment.py`

**Purpose:** Assessment stage (project spec or knowledge test generation)

```python
"""Assessment stage: generates project specs or knowledge tests."""

from dataclasses import asdict
from .models import AssessmentApproach
from .artifacts import Artifact, ArtifactStore
from .llm import call_llm

ASSESSMENT_PROMPTS = {
    "project_prompt": """You are designing a project that validates learning.

## Learning Objectives (must all be validated)
{learning_objectives}

## Learner Context
- Prior Knowledge: {prior_knowledge}
- Learning Style: {learning_style}

## Project Specification
{project_description}

## Task
Create a project specification (markdown) that:
1. States the goal clearly
2. Provides starter code (with TODOs)
3. Lists 5-10 test cases mapping to objectives
4. Includes hints for tricky parts
5. Estimated time: based on {material_density} and {depth}
6. Bonus challenges for deeper mastery

Output: Markdown project spec + Python starter code + test suite.
""",
    
    "test_prompt": """You are designing a knowledge test.

## Learning Objectives
{learning_objectives}

## Test Specification
Format: {test_format}
Count: {test_count} items
Difficulty: {assessment_difficulty}
Language: tailored to {prior_knowledge}

## Task
Create {test_count} test items:
1. Each validates ONE objective
2. Include answer key with explanations
3. Avoid trick questions; test understanding
4. Difficulty: {assessment_difficulty}

Output: Markdown test file with questions + answer key.
""",
}


class AssessmentStage:
    """Generates assessment artifacts (projects or tests)."""
    
    def run(
        self,
        store: ArtifactStore,
        assessment_approach: AssessmentApproach,
        context: dict,
    ) -> None:
        """Generate assessment based on approach.
        
        Saves artifacts to store:
        - project_spec.md + project_starter.py + project_tests.py (if project)
        - knowledge_test.md + test_answer_key.md (if test)
        """
        if assessment_approach.type in ("project", "both"):
            self._generate_project(store, assessment_approach, context)
        
        if assessment_approach.type in ("knowledge_test", "both"):
            self._generate_test(store, assessment_approach, context)
    
    def _generate_project(
        self,
        store: ArtifactStore,
        approach: AssessmentApproach,
        context: dict,
    ) -> None:
        """Generate project specification."""
        prompt = self._render_prompt(
            "project_prompt",
            store,
            context,
            approach.project,
        )
        
        response = call_llm(prompt)
        
        # Parse response (should include spec + starter + tests)
        # For now, save as single markdown
        store.put(Artifact(
            name="project_spec",
            kind="text",
            content=response,
        ))
    
    def _generate_test(
        self,
        store: ArtifactStore,
        approach: AssessmentApproach,
        context: dict,
    ) -> None:
        """Generate knowledge test."""
        prompt = self._render_prompt(
            "test_prompt",
            store,
            context,
            approach.knowledge_test,
        )
        
        response = call_llm(prompt)
        
        store.put(Artifact(
            name="knowledge_test",
            kind="text",
            content=response,
        ))
    
    def _render_prompt(
        self,
        template_key: str,
        store: ArtifactStore,
        context: dict,
        assessment_config,
    ) -> str:
        """Render assessment prompt with context."""
        template = ASSESSMENT_PROMPTS[template_key]
        
        render_context = {}
        
        # Add learner/topic context
        if "learner_profile" in context:
            render_context.update(
                context["learner_profile"].to_prompt_context()
            )
        
        if "topic_spec" in context:
            render_context.update(
                context["topic_spec"].to_prompt_context()
            )
        
        # Add assessment-specific config
        if assessment_config:
            render_context.update(asdict(assessment_config))
        
        # Add approach-specific difficulty
        if "assessment_approach" in context:
            render_context["assessment_difficulty"] = (
                context["assessment_approach"].assessment_difficulty
            )
        
        return template.format(**render_context)
```

**Summary:**
- New AssessmentStage class
- Generates project OR test based on assessment_approach
- Renders context-aware prompts
- Saves artifacts to store

---

## 6. Modified: `forged/_run_stage()` function

**Current:**
```python
def _run_stage(stage, store, runner_factory, pipeline_name, on_stage, timings):
    runner = runner_factory(stage)
    artifact = runner.run(store)
    store.put(artifact)
```

**New:**
```python
def _run_stage(
    stage,
    store,
    runner_factory,
    pipeline_name,
    on_stage,
    timings,
    context: dict | None = None,  # NEW
):
    """Run a pipeline stage with optional context."""
    runner = runner_factory(stage)
    
    # Time the execution
    start = time.time()
    
    # Pass context to agent if available
    if isinstance(runner, LLMAgent) and context:
        artifact = runner.run(store, context=context)
    else:
        artifact = runner.run(store)
    
    elapsed = time.time() - start
    timings[stage.name] = elapsed
    
    store.put(artifact)
    
    if on_stage:
        on_stage(stage.name, "completed", f"{elapsed:.1f}s")
```

---

## 7. Modified: `pyproject.toml`

**Add dependencies:**

```toml
[project]
dependencies = [
    "openai>=2.0",
    "pyyaml>=6.0",  # NEW: for YAML parsing
    "pydantic>=2.0",  # NEW: for data validation
    ...
]
```

---

## 8. Backward Compatibility Strategy

**Goal:** Existing code using minimal input still works.

**How:**
- If `--learner-profile` not provided, use `_default_learner_profile()`
- If `--topic-spec` not provided, use `_default_topic_spec(brief)`
- If `--assessment` not provided, skip assessment stage
- Old CLI still works: `forged build --topic "..."`

**Test Case:**
```bash
# OLD: Still works
forged build --topic "How hash maps work"

# NEW: With full context
forged build \
  --topic "How hash maps work" \
  --learner-profile templates/examples/backend-junior.yaml \
  --topic-spec templates/examples/topic-hash-maps.yaml \
  --assessment templates/examples/assess-project.yaml
```

---

## Implementation Order (Recommended)

1. **Create `forged/models.py`** — data models (no breaking changes)
2. **Create `forged/prompts.py`** — prompt templates (no breaking changes)
3. **Modify `forged/cli.py`** — add new arguments (backward compatible)
4. **Modify `forged/orchestrator.py`** — accept structured inputs
5. **Modify `forged/agent.py`** — use context in prompts
6. **Create `forged/assessment.py`** — new assessment stage
7. **Modify `pyproject.toml`** — add dependencies
8. **Create template files** — YAML examples (Step 4)
9. **Test** — ensure backward compatibility (Step 7)

---

## Key Implementation Notes

### Data Model Validation
- Use Pydantic for YAML validation (catches typos, invalid enum values)
- Example: `material_density` must be one of ["dense", "standard", "rich"]

### Prompt Templating
- Use string `.format(**context)` for simplicity
- Consider Jinja2 for complexity in future
- Keep templates in separate file for easy editing

### Context Threading
- Pass context dict through _run_stage → LLMAgent.run() → _build_prompt()
- Keep context immutable (read-only for agents)

### Assessment Stage Timing
- Run AFTER revision loop (optional stage, for final validation)
- Only run if `assessment_approach` is provided
- Can be skipped for quick testing

### Error Handling
- Validate YAML files on load (pydantic raises clear errors)
- Catch missing required fields in templates
- Provide helpful error messages if YAML format is wrong

---

## Testing Strategy (Step 7)

Will validate:
- YAML parsing (valid/invalid files)
- Backward compatibility (minimal --topic still works)
- Context threading (agents receive all context)
- Assessment stage (project and test generation)
- Quality improvement (richer input → better output)

---

## Questions / Decisions

1. **Prompt rendering:** Use `.format()` or Jinja2?
   - Recommendation: `.format()` for now (simpler, no dependencies)

2. **Assessment stage placement:** Before or after revision loop?
   - Recommendation: After (assess final notebook)

3. **Multiple assessment types:** Generate both project AND test, or let user choose?
   - Recommendation: Let user choose (assessment_approach.type = "project" | "test" | "both")

4. **Objective tracking in Executor:** Automatic or Planner-annotated?
   - Recommendation: Planner annotates cells with assessment hooks; Executor tracks execution against hooks (future refinement)

---

## Related Documents

- [01-input-specification.md](01-input-specification.md) — what users provide
- [02-agent-input-flow.md](02-agent-input-flow.md) — how agents use context
- TODO.md (root) — full task list and timeline
