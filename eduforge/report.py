"""Human-readable run summary.

The per-stage JSON reports are agent-to-agent plumbing — useless to read raw. This
module distils a whole run into one SUMMARY.md a person actually wants: what each
stage did, whether the code really ran, which cells failed, and the narrative
outputs (plan, feedback) inline. After this is written, the raw intermediates are
pruned (see ArtifactStore.finalize).
"""

from __future__ import annotations

import json

from .artifacts import ArtifactStore
from .config import PipelineConfig, StageType


def build_summary(
    pipeline: PipelineConfig,
    store: ArtifactStore,
    brief: str,
    profile_label: str,
) -> str:
    """Render a Markdown summary of the completed run."""
    lines: list[str] = [
        f"# Run summary — {pipeline.name}",
        "",
        f"- **Topic:** {brief.strip()}",
        f"- **Learner profile:** {profile_label}",
        "",
        _overall_line(pipeline, store),
        "",
        "## Stages",
        "",
        "| # | stage | type | result |",
        "|---|-------|------|--------|",
    ]
    for index, stage in enumerate(pipeline.stages, start=1):
        lines.append(
            f"| {index} | {stage.name} | {stage.type.value} | "
            f"{_stage_result(stage, store)} |"
        )

    lines += _execution_details(pipeline, store)
    lines += _narrative_outputs(pipeline, store)
    return "\n".join(lines).rstrip() + "\n"


def _overall_line(pipeline: PipelineConfig, store: ArtifactStore) -> str:
    failures = _execution_failures(pipeline, store)
    if not failures:
        return "**Result: ✓ all generated code executed cleanly.**"
    total = sum(f["failed_cell_count"] for f in failures)
    return f"**Result: ✗ {total} cell(s) failed across {len(failures)} execution(s).**"


def _stage_result(stage, store: ArtifactStore) -> str:
    if not store.has(stage.output):
        return "—"
    artifact = store.get(stage.output)
    if stage.type is StageType.EXECUTOR:
        report = json.loads(artifact.content)
        if report.get("ok"):
            return f"✓ {report['code_cell_count']} cells ran"
        return f"✗ {report['failed_cell_count']}/{report['code_cell_count']} cells failed"
    if artifact.kind == "notebook":
        return "notebook assembled"
    return f"{len(artifact.content.split())} words"


def _execution_failures(pipeline: PipelineConfig, store: ArtifactStore) -> list[dict]:
    """Collect reports from executor stages that had at least one failed cell."""
    reports = []
    for stage in pipeline.stages:
        if stage.type is StageType.EXECUTOR and store.has(stage.output):
            report = json.loads(store.get(stage.output).content)
            if not report.get("ok"):
                reports.append(report)
    return reports


def _execution_details(pipeline: PipelineConfig, store: ArtifactStore) -> list[str]:
    failures = _execution_failures(pipeline, store)
    if not failures:
        return []
    lines = ["", "## Execution failures", ""]
    for report in failures:
        for cell in report["cells"]:
            if cell["status"] == "error":
                lines.append(f"- **cell {cell['cell_index']}** — {cell['error']}")
                lines.append(f"  ```\n  {cell['source_preview']}\n  ```")
    return lines


def _narrative_outputs(pipeline: PipelineConfig, store: ArtifactStore) -> list[str]:
    """Inline the text outputs (plan, feedback) so the dropped files lose nothing."""
    lines: list[str] = []
    for stage in pipeline.stages:
        if stage.type is StageType.LLM and stage.output_kind == "text":
            if store.has(stage.output):
                lines += ["", f"## {stage.name}", "", store.get(stage.output).content]
    return lines
