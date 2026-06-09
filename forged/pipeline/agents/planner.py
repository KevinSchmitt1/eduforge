"""PlannerAgent — produces a lesson plan from a topic brief and learner profile.

Persona: personas/planner.md
Input artifacts: (none required; reads from state metadata or uses defaults)
Output artifact: lesson_plan_v{iteration}.md  (kind=text)
Next stage: CODE_AUTHOR
"""

from __future__ import annotations

from pathlib import Path

from forged.artifacts import Artifact, ArtifactStore
from forged.pipeline.state import PipelineStage, PipelineState, StageOutput

from . import Agent, AgentOutput


class PlannerAgent(Agent[AgentOutput]):
    """Turns a topic brief into a structured lesson plan.

    Reads personas/planner.md as the system prompt and calls the configured
    LLM backend to generate the plan.
    """

    def __init__(self, personas_dir: Path | None = None, llm_client=None) -> None:
        super().__init__(personas_dir=personas_dir, llm_client=llm_client)

    def _load_persona(self) -> str:
        path = self.personas_dir / "planner.md"
        return path.read_text(encoding="utf-8")

    def next_stage(self) -> PipelineStage:
        return PipelineStage.CODE_AUTHOR

    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        user_msg = self._build_user_message(state, store)
        try:
            response = self._call_llm(user_msg)
        except RuntimeError as exc:
            raise RuntimeError(f"PlannerAgent LLM call failed: {exc}") from exc
        artifact_name = f"lesson_plan_v{state.iteration}"
        store.put(Artifact(name=artifact_name, kind="text", content=response))
        output = StageOutput(
            stage=PipelineStage.PLANNER,
            artifact_name=artifact_name,
            iteration=state.iteration,
        )
        return state.with_output(output).with_current_stage(self.next_stage())

    def _call_llm(self, user_msg: str) -> str:
        """Call the LLM with the planner system prompt and return the text response."""
        return self._llm_client.complete(self.persona, user_msg)

    def _build_user_message(self, state: PipelineState, store: ArtifactStore) -> str:
        lines = [f"Run ID: {state.run_id}", f"Iteration: {state.iteration}"]
        if store.has("brief"):
            lines.append(f"\nBrief:\n{store.get('brief').content}")
        if store.has("profile"):
            lines.append(f"\nProfile:\n{store.get('profile').content}")
        return "\n".join(lines)
