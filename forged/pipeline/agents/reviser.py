"""RevisorAgent — classifies quality and routes the pipeline to the next stage.

Persona: personas/reviser.md
Input artifacts: execution_report_v{N}.json, student_grade_report_v{N}.json
Output: state update only (routing_log entry or is_terminal flag; no artifact)
Next stage: None (state.routing_log[-1].to_stage determines routing)

This agent is the only one that modifies routing_log.  It delegates to the
deterministic classify() + Router.route() stack — no LLM calls needed here.
A RoutingBudget can be injected at construction for testing.
"""

from __future__ import annotations

import json
import logging

from forged.artifacts import ArtifactStore
from forged.pipeline.failure import ExecutionReport, GradeReport, classify
from forged.pipeline.router import Router, RoutingBudget, RoutingRequest
from forged.pipeline.state import Evidence, Location, LocationType, PipelineStage, PipelineState, StageOutput

from . import Agent, AgentOutput

_LOG = logging.getLogger(__name__)


class RevisorAgent(Agent[AgentOutput]):
    """Reads signals from executor + student and routes the pipeline.

    Uses classify() and Router.route() deterministically — no LLM.
    A custom RoutingBudget can be injected to override defaults (useful in tests).
    """

    def __init__(self, personas_dir=None, llm_client=None, budget: RoutingBudget | None = None) -> None:
        super().__init__(personas_dir=personas_dir, llm_client=llm_client)
        self._router = Router(budget=budget)

    def _load_persona(self) -> str:
        path = self.personas_dir / "reviser.md"
        return path.read_text(encoding="utf-8")

    def next_stage(self) -> PipelineStage | None:
        return None

    async def run(self, state: PipelineState, store: ArtifactStore) -> PipelineState:
        exec_report = self._read_execution_report(state, store)
        grade_report = self._read_grade_report(state, store)
        classification = classify(exec_report, grade_report)
        request = RoutingRequest(
            state=state,
            classification=classification,
            evidence=list(grade_report.findings) if grade_report else [],
        )
        result = self._router.route(request)
        if result.should_terminate:
            return state.with_terminal(result.reason)
        if result.routing_decision is None:
            raise RuntimeError("Router returned non-terminal result with no routing_decision")
        if result.next_stage is None:
            raise RuntimeError("Router returned non-terminal result with no next_stage")
        new_state = state.with_routing_decision(result.routing_decision)
        new_state = new_state.with_attempt(result.next_stage)
        return new_state.with_current_stage(result.next_stage)

    def _read_execution_report(
        self, state: PipelineState, store: ArtifactStore
    ) -> ExecutionReport | None:
        name = self._latest_artifact_name(state, PipelineStage.EXECUTOR, "execution_report")
        if not store.has(name):
            return None
        try:
            raw = json.loads(store.get(name).content)
        except json.JSONDecodeError:
            _LOG.warning("RevisorAgent: invalid execution report JSON in %s", name)
            return None
        return ExecutionReport(
            ok=raw.get("ok", True),
            failed_cells=raw.get("failed_cells", []),
            error_summary=raw.get("error_summary"),
        )

    def _read_grade_report(
        self, state: PipelineState, store: ArtifactStore
    ) -> GradeReport | None:
        name = self._latest_artifact_name(state, PipelineStage.STUDENT, "student_grade_report")
        if not store.has(name):
            return None
        try:
            raw = json.loads(store.get(name).content)
        except json.JSONDecodeError:
            _LOG.warning("RevisorAgent: invalid grade report JSON in %s", name)
            return None
        findings = [
            Evidence(
                source=f["source"],
                severity=f["severity"],
                scope=f["scope"],
                location=Location(
                    type=self._coerce_location_type(f["location"].get("type")),
                    cell_index=(
                        f["location"].get("cell_index")
                        if self._coerce_location_type(f["location"].get("type"))
                        == LocationType.CELL
                        else None
                    ),
                    label=f["location"].get("label"),
                ),
                text=f["text"],
            )
            for f in raw.get("findings", [])
        ]
        return GradeReport(
            quality_score=raw.get("quality_score", 0.0),
            blockers=raw.get("blockers", []),
            findings=findings,
        )

    def _latest_artifact_name(
        self, state: PipelineState, stage: PipelineStage, fallback_prefix: str
    ) -> str:
        for output in reversed(state.outputs):
            if output.stage == stage:
                return output.artifact_name
        return f"{fallback_prefix}_v{state.iteration}"

    def _coerce_location_type(self, raw_type: str | None) -> LocationType:
        """Accept slightly looser external labels from LLM output.

        Real model responses sometimes emit notebook-level findings using
        `notebook` instead of the internal `artifact` enum label. Preserve the
        intent rather than crashing the revision loop on otherwise usable
        feedback.
        """
        mapping = {
            "cell": LocationType.CELL,
            "section": LocationType.SECTION,
            "lesson_structure": LocationType.LESSON_STRUCTURE,
            "artifact": LocationType.ARTIFACT,
            "notebook": LocationType.ARTIFACT,
            "global": LocationType.GLOBAL,
            "lesson": LocationType.GLOBAL,
        }
        return mapping.get((raw_type or "").strip().lower(), LocationType.GLOBAL)
