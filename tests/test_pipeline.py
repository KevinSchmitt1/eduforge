"""Offline tests — no network, no API key required.

These cover the architecture's load-bearing parts:
  * pipeline config loads and validates (and rejects broken dataflow)
  * notebook assembly from the model's JSON cell format
  * the executor actually runs a notebook AND flags a failing cell

Run from the repo root:  pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eduforge.artifacts import Artifact, ArtifactStore
from eduforge.config import PipelineConfig, load_pipeline
from eduforge.executor import ExecutorStage
from eduforge.notebook import build_notebook, cells_from_json, render_indexed

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# ── Config ───────────────────────────────────────────────────────────────────

def test_skeleton_config_loads_expected_stages():
    pipeline = load_pipeline(CONFIG_DIR / "pipeline.skeleton.yaml")
    assert pipeline.name == "skeleton"
    assert [s.name for s in pipeline.stages] == [
        "planner", "code_author", "executor", "student",
    ]


def test_profile_is_a_valid_seed_input():
    # Stages may read the 'profile' seed without any stage producing it.
    config = {
        "name": "p",
        "stages": [
            {"name": "s1", "persona": "x.md", "inputs": ["brief", "profile"],
             "output": "out"},
        ],
    }
    pipeline = PipelineConfig.model_validate(config)
    assert pipeline.stages[0].inputs == ["brief", "profile"]


def test_config_rejects_stage_reading_unknown_artifact():
    broken = {
        "name": "bad",
        "stages": [
            {"name": "s1", "persona": "p.md", "inputs": ["nope"], "output": "out"},
        ],
    }
    with pytest.raises(ValueError, match="no .*earlier stage produces"):
        PipelineConfig.model_validate(broken)


def test_config_rejects_llm_stage_without_persona():
    broken = {
        "name": "bad",
        "stages": [{"name": "s1", "type": "llm", "inputs": ["brief"], "output": "o"}],
    }
    with pytest.raises(ValueError, match="must declare a persona"):
        PipelineConfig.model_validate(broken)


# ── Notebook assembly ────────────────────────────────────────────────────────

def test_cells_from_json_handles_bare_array():
    raw = '[{"type": "markdown", "source": "# Hi"}, {"type": "code", "source": "x=1"}]'
    cells = cells_from_json(raw)
    assert [c["type"] for c in cells] == ["markdown", "code"]


def test_cells_from_json_strips_code_fence():
    raw = '```json\n[{"type": "code", "source": "x=1"}]\n```'
    cells = cells_from_json(raw)
    assert cells[0]["source"] == "x=1"


def test_cells_from_json_rejects_bad_cell_type():
    with pytest.raises(ValueError, match="invalid type"):
        cells_from_json('[{"type": "sql", "source": "select 1"}]')


def test_build_notebook_produces_valid_ipynb():
    cells = [{"type": "markdown", "source": "# T"}, {"type": "code", "source": "x=1"}]
    nb_json = json.loads(build_notebook(cells))
    assert nb_json["nbformat"] == 4
    assert len(nb_json["cells"]) == 2


def test_render_indexed_labels_cells_consistently():
    # Indices in the rendering must match notebook cell positions (markdown included)
    # so agent feedback lines up with the executor's report.
    nb = build_notebook(
        [
            {"type": "markdown", "source": "# Title"},
            {"type": "code", "source": "x = 1"},
            {"type": "markdown", "source": "Done"},
        ]
    )
    rendered = render_indexed(nb)
    assert "indexed 0..2" in rendered
    assert "[cell 0 · markdown]" in rendered
    assert "[cell 1 · code]" in rendered
    assert "[cell 2 · markdown]" in rendered


def test_review_loop_config_validates():
    pipeline = load_pipeline(CONFIG_DIR / "pipeline.review-loop.yaml")
    names = [s.name for s in pipeline.stages]
    # The loop re-runs and re-checks the revised notebook.
    assert "reviser" in names
    assert names.index("executor_revised") > names.index("reviser")
    assert names.index("student_revised") > names.index("executor_revised")


# ── Executor (the anti-bug layer) ────────────────────────────────────────────

def _store_with_notebook(tmp_path: Path, sources: list[str]) -> ArtifactStore:
    store = ArtifactStore(tmp_path)
    cells = [{"type": "code", "source": s} for s in sources]
    store.put(Artifact(name="notebook", kind="notebook", content=build_notebook(cells)))
    return store


def _executor_stage():
    from eduforge.config import StageConfig

    return StageConfig(
        name="executor", type="executor", inputs=["notebook"],
        output="report", params={"timeout": 60},
    )


def test_executor_reports_success_for_clean_notebook(tmp_path):
    store = _store_with_notebook(tmp_path, ["a = 2 + 2", "print(a)"])
    report = json.loads(ExecutorStage(_executor_stage()).run(store).content)
    assert report["ok"] is True
    assert report["failed_cell_count"] == 0


def test_executor_flags_failing_cell(tmp_path):
    # A cell that raises must be caught and reported — the exact class of problem
    # that slipped through the original lesson notebook.
    store = _store_with_notebook(tmp_path, ["ok = 1", "raise ValueError('boom')"])
    report = json.loads(ExecutorStage(_executor_stage()).run(store).content)
    assert report["ok"] is False
    assert report["failed_cell_count"] == 1
    failing = [c for c in report["cells"] if c["status"] == "error"][0]
    assert "ValueError" in failing["error"]


# ── Finalize / cleanup ───────────────────────────────────────────────────────

def test_finalize_keeps_only_named_files(tmp_path):
    store = ArtifactStore(tmp_path)
    store.put(Artifact(name="execution_report", kind="json", content="{}"))
    store.put(Artifact(name="lesson_plan", kind="text", content="plan"))
    store.write_file("lesson.ipynb", "{}")
    store.write_file("SUMMARY.md", "# summary")

    removed = store.finalize({"lesson.ipynb", "SUMMARY.md", "manifest.json"})

    remaining = {p.name for p in tmp_path.iterdir()}
    assert remaining == {"lesson.ipynb", "SUMMARY.md"}
    assert "execution_report.json" in removed
    assert "lesson_plan.md" in removed


def test_build_summary_reports_execution_and_narrative(tmp_path):
    from eduforge.config import PipelineConfig
    from eduforge.report import build_summary

    pipeline = PipelineConfig.model_validate(
        {
            "name": "t",
            "stages": [
                {"name": "code", "persona": "c.md", "inputs": ["brief"],
                 "output": "nb", "output_kind": "notebook"},
                {"name": "executor", "type": "executor", "inputs": ["nb"],
                 "output": "execution_report"},
            ],
        }
    )
    store = ArtifactStore(tmp_path)
    store.put(Artifact(name="nb", kind="notebook",
                       content=build_notebook([{"type": "code", "source": "x=1"}])))
    failing_report = {
        "ok": False, "code_cell_count": 1, "failed_cell_count": 1,
        "cells": [{"cell_index": 0, "status": "error",
                   "error": "ValueError: boom", "source_preview": "raise ..."}],
    }
    store.put(Artifact(name="execution_report", kind="json",
                       content=json.dumps(failing_report)))

    summary = build_summary(pipeline, store, "My topic", "learner.md")
    assert "My topic" in summary
    assert "ValueError: boom" in summary  # failure surfaced
    assert "1/1 cells failed" in summary   # stage result column


def test_clean_keeps_newest_runs(tmp_path):
    from argparse import Namespace

    from eduforge.cli import _cmd_clean

    runs = tmp_path / "runs"
    runs.mkdir()
    for stamp in ["20260101-000000_x", "20260102-000000_x", "20260103-000000_x"]:
        (runs / stamp).mkdir()

    _cmd_clean(Namespace(keep=2, runs=str(runs)))

    remaining = sorted(p.name for p in runs.iterdir())
    assert remaining == ["20260102-000000_x", "20260103-000000_x"]
