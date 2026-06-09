"""Unit tests for the Agent base class, AgentOutput, and PlannerAgent stub.

Tests cover the persona-loading contract, ABC enforcement, immutability of
AgentOutput, and the PlannerAgent concrete stub — all without LLM calls.

TDD: these tests are written BEFORE the implementation exists (RED phase).
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

# ── Imports under test ────────────────────────────────────────────────────────
# These will fail (ImportError) until the implementation exists — that is the
# expected RED state.
from forged.pipeline.agents import Agent, AgentOutput, PlannerAgent

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def personas_dir(tmp_path: Path) -> Path:
    """A temporary personas directory with a planner.md file."""
    d = tmp_path / "personas"
    d.mkdir()
    (d / "planner.md").write_text("You are the Lesson Planner.", encoding="utf-8")
    return d


@pytest.fixture
def empty_personas_dir(tmp_path: Path) -> Path:
    """A temporary personas directory that exists but has no planner.md."""
    d = tmp_path / "personas"
    d.mkdir()
    return d


# ── Minimal concrete stub used inside tests ────────────────────────────────────


class _ConcreteAgent(Agent):  # type: ignore[type-arg]
    """Minimal concrete Agent for testing the ABC contract."""

    def __init__(self, personas_dir: Path) -> None:
        super().__init__(personas_dir=personas_dir)

    def _load_persona(self) -> str:
        path = self.personas_dir / "planner.md"
        return path.read_text(encoding="utf-8")

    async def run(self, state, store):  # type: ignore[override]
        return state

    def next_stage(self):
        from forged.pipeline.state import PipelineStage
        return PipelineStage.CODE_AUTHOR


# ── Agent.__init__ ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_agent_init_loads_persona_from_file(personas_dir: Path) -> None:
    """Agent.__init__ must call _load_persona() and store the result."""
    agent = _ConcreteAgent(personas_dir=personas_dir)
    assert agent.persona == "You are the Lesson Planner."


@pytest.mark.unit
def test_agent_requires_personas_dir(tmp_path: Path) -> None:
    """Agent defaults to Path('personas') when personas_dir is None.

    We verify this by checking that the stored attribute equals Path('personas'),
    not by actually loading a file (which would require the cwd to have a
    personas/ directory at test time).
    """
    # We cannot instantiate _ConcreteAgent without a real personas_dir because
    # _load_persona() tries to read the file immediately.  Test the default
    # resolution by inspecting __init__ source-level behaviour via a subclass
    # that overrides _load_persona to skip the real read.

    class _NullAgent(Agent):  # type: ignore[type-arg]
        def _load_persona(self) -> str:
            return "stub"

        async def run(self, state, store):  # type: ignore[override]
            return state

        def next_stage(self):
            return None

    agent = _NullAgent()  # No personas_dir supplied
    assert agent.personas_dir == Path("personas")


@pytest.mark.unit
def test_agent_fails_if_persona_missing(empty_personas_dir: Path) -> None:
    """Agent.__init__ raises FileNotFoundError when the persona file is absent."""
    with pytest.raises(FileNotFoundError):
        _ConcreteAgent(personas_dir=empty_personas_dir)


# ── Persona content ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_persona_is_string(personas_dir: Path) -> None:
    """Loaded persona must be a str instance."""
    agent = _ConcreteAgent(personas_dir=personas_dir)
    assert isinstance(agent.persona, str)


@pytest.mark.unit
def test_persona_is_not_empty(personas_dir: Path) -> None:
    """Loaded persona must contain non-whitespace content."""
    agent = _ConcreteAgent(personas_dir=personas_dir)
    assert agent.persona.strip() != ""


@pytest.mark.unit
def test_persona_matches_file_content(personas_dir: Path) -> None:
    """Persona content must exactly match what read_text() returns from disk."""
    expected = (personas_dir / "planner.md").read_text(encoding="utf-8")
    agent = _ConcreteAgent(personas_dir=personas_dir)
    assert agent.persona == expected


# ── ABC enforcement ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_agent_is_abstract() -> None:
    """Agent cannot be instantiated directly — it is an ABC."""
    with pytest.raises(TypeError):
        Agent()  # type: ignore[abstract]


@pytest.mark.unit
def test_agent_requires_run_method() -> None:
    """A subclass that omits run() cannot be instantiated."""

    class _NoRun(Agent):  # type: ignore[type-arg]
        def _load_persona(self) -> str:
            return "stub"

        def next_stage(self):
            return None

    with pytest.raises(TypeError):
        _NoRun()


@pytest.mark.unit
def test_agent_requires_load_persona_method() -> None:
    """A subclass that omits _load_persona() cannot be instantiated."""

    class _NoPersona(Agent):  # type: ignore[type-arg]
        async def run(self, state, store):  # type: ignore[override]
            return state

        def next_stage(self):
            return None

    with pytest.raises(TypeError):
        _NoPersona()


@pytest.mark.unit
def test_agent_requires_next_stage_method() -> None:
    """A subclass that omits next_stage() cannot be instantiated."""

    class _NoNextStage(Agent):  # type: ignore[type-arg]
        def _load_persona(self) -> str:
            return "stub"

        async def run(self, state, store):  # type: ignore[override]
            return state

    with pytest.raises(TypeError):
        _NoNextStage()


# ── AgentOutput ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_agent_output_is_frozen() -> None:
    """AgentOutput must be a frozen dataclass — mutation must raise."""
    output = AgentOutput(
        stage_name="planner",
        artifact_name="lesson_plan_v0.md",
        artifact_kind="text",
    )
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        output.stage_name = "hacked"  # type: ignore[misc]


@pytest.mark.unit
def test_agent_output_has_required_fields() -> None:
    """AgentOutput must have stage_name, artifact_name, artifact_kind, metadata."""
    output = AgentOutput(
        stage_name="planner",
        artifact_name="lesson_plan_v0.md",
        artifact_kind="text",
        metadata={"tokens": 512},
    )
    assert output.stage_name == "planner"
    assert output.artifact_name == "lesson_plan_v0.md"
    assert output.artifact_kind == "text"
    assert output.metadata == {"tokens": 512}


@pytest.mark.unit
def test_agent_output_metadata_defaults_to_none() -> None:
    """AgentOutput.metadata is optional and defaults to None."""
    output = AgentOutput(
        stage_name="planner",
        artifact_name="plan.md",
        artifact_kind="text",
    )
    assert output.metadata is None


# ── PlannerAgent stub ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_planner_agent_loads_planner_persona(personas_dir: Path) -> None:
    """PlannerAgent loads the planner.md file from personas_dir."""
    agent = PlannerAgent(personas_dir=personas_dir)
    assert agent.persona == (personas_dir / "planner.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_planner_agent_next_stage_is_code_author(personas_dir: Path) -> None:
    """PlannerAgent.next_stage() must return PipelineStage.CODE_AUTHOR."""
    from forged.pipeline.state import PipelineStage

    agent = PlannerAgent(personas_dir=personas_dir)
    assert agent.next_stage() == PipelineStage.CODE_AUTHOR


@pytest.mark.unit
def test_planner_agent_persona_is_not_empty(personas_dir: Path) -> None:
    """PlannerAgent.persona must contain non-whitespace content after loading."""
    agent = PlannerAgent(personas_dir=personas_dir)
    assert agent.persona.strip() != ""


# ── run() signature contract ─────────────────────────────────────────────────


@pytest.mark.unit
def test_agent_run_is_async() -> None:
    """Agent.run must be declared as an async method (coroutine function)."""
    assert inspect.iscoroutinefunction(Agent.run)


@pytest.mark.unit
def test_agent_run_receives_state_and_store() -> None:
    """Agent.run must accept (self, state, store) as parameters."""
    sig = inspect.signature(Agent.run)
    params = list(sig.parameters)
    assert "state" in params
    assert "store" in params

