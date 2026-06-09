"""Assessment stage: generates project specs or knowledge tests."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .artifacts import Artifact, ArtifactStore
from .llm import LLMClient
from .models import AssessmentApproach
from .prompts import ASSESSMENT_PROMPTS


class AssessmentStage:
    """Generates assessment artifacts (projects or tests) after the pipeline completes."""

    def __init__(self, model: str):
        """Initialize with an LLM model."""
        self._client = LLMClient(model)

    def run(
        self,
        store: ArtifactStore,
        assessment_approach: AssessmentApproach,
        context: dict,
    ) -> None:
        """Generate assessment based on approach.

        Saves artifacts to store:
        - project_spec.md (if project type)
        - knowledge_test.md (if knowledge_test type)
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

        response = self._client.complete(
            system_prompt="You are an expert course designer creating project assignments.",
            user_prompt=prompt,
        )

        store.put(Artifact(
            name="project_spec",
            kind="text",
            content=response.strip(),
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

        response = self._client.complete(
            system_prompt="You are an expert educator creating assessments.",
            user_prompt=prompt,
        )

        store.put(Artifact(
            name="knowledge_test",
            kind="text",
            content=response.strip(),
        ))

    def _render_prompt(
        self,
        template_key: str,
        store: ArtifactStore,
        context: dict,
        assessment_config,
    ) -> str:
        """Render assessment prompt with context."""
        template = ASSESSMENT_PROMPTS.get(template_key)
        if not template:
            raise ValueError(f"Unknown assessment template: {template_key}")

        render_context = {}

        # Add learner/topic context
        if "learner_profile" in context and context["learner_profile"]:
            render_context.update(context["learner_profile"].to_prompt_context())

        if "topic_spec" in context and context["topic_spec"]:
            render_context.update(context["topic_spec"].to_prompt_context())

        # Add assessment-specific config
        if assessment_config:
            render_context.update(asdict(assessment_config))

        # Add assessment approach difficulty
        if "assessment_approach" in context and context["assessment_approach"]:
            render_context["assessment_difficulty"] = (
                context["assessment_approach"].assessment_difficulty
            )

        return template.format(**render_context)
