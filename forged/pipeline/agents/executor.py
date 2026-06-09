"""ExecutorAgent — runs the notebook and captures a structured execution report.

Persona: none (deterministic execution; no LLM needed)
Input artifacts: lesson_notebook_v{N}.ipynb  (reads latest from outputs)
Output artifact: execution_report_v{iteration}.json  (kind=json)
Next stage: STUDENT

In Phase 5 the execution is mocked (always succeeds).  Phase 6 replaces
_mock_execute() with the real forged.executor logic that runs nbclient.
"""

from __future__ import annotations

import json

from forged.artifacts import Artifact, ArtifactStore
from forged.pipeline.state import PipelineStage, PipelineState, StageOutput

from . import Agent, AgentOutput


class ExecutorAgent(Agent[AgentOutput]):
    """Executes the lesson notebook and produces a structured execution report.

    No LLM persona is required — execution is deterministic.  The persona
    attribute is set to an empty string via _load_persona().
    """

    def _load_persona(self) -> str:
        return ""

    def next_stage(self) -> PipelineStage:
        return PipelineStage.STUDENT

    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        notebook_name = self._latest_notebook_name(state)
        notebook_content = store.get(notebook_name).content if store.has(notebook_name) else "[]"
        report = self._mock_execute(notebook_content)
        artifact_name = f"execution_report_v{state.iteration}"
        store.put(Artifact(name=artifact_name, kind="json", content=json.dumps(report)))
        output = StageOutput(
            stage=PipelineStage.EXECUTOR,
            artifact_name=artifact_name,
            iteration=state.iteration,
        )
        return state.with_output(output).with_current_stage(self.next_stage())

    def _latest_notebook_name(self, state: PipelineState) -> str:
        for output in reversed(state.outputs):
            if output.stage == PipelineStage.CODE_AUTHOR:
                return output.artifact_name
        return f"lesson_notebook_v{state.iteration}"

    def _mock_execute(self, notebook_content: str) -> dict:
        return {
            "ok": True,
            "failed_cells": [],
            "error_summary": None,
        }
