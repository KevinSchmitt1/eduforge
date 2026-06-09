"""Assemble a valid .ipynb from structured cells.

We never ask the LLM for raw notebook JSON (brittle, easy to malform). Instead the
code-author agent returns a simple list of cells — {"type": "markdown"|"code",
"source": "..."} — and we build the notebook deterministically with nbformat.
This keeps the fragile JSON structure out of the model's hands.
"""

from __future__ import annotations

import json

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

VALID_CELL_TYPES = {"markdown", "code"}


def cells_from_json(raw: str) -> list[dict]:
    """Parse and validate the agent's JSON cell list.

    Accepts either a bare JSON array or an object with a top-level "cells" key,
    and tolerates a ```json fenced block around it (models often add fences).
    Raises ValueError with context on malformed output.
    """
    text = _strip_code_fence(raw).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Code-author output is not valid JSON: {exc}") from exc

    cells = data.get("cells") if isinstance(data, dict) else data
    if not isinstance(cells, list) or not cells:
        raise ValueError("Expected a non-empty JSON list of cells")

    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise ValueError(f"Cell {index} is not an object: {cell!r}")
        cell_type = cell.get("type")
        if cell_type not in VALID_CELL_TYPES:
            raise ValueError(
                f"Cell {index} has invalid type {cell_type!r}; "
                f"expected one of {sorted(VALID_CELL_TYPES)}"
            )
        if not isinstance(cell.get("source"), str):
            raise ValueError(f"Cell {index} 'source' must be a string")
    return cells


def build_notebook(cells: list[dict]) -> str:
    """Turn validated cells into serialized .ipynb JSON (nbformat v4)."""
    notebook = new_notebook()
    notebook.cells = [
        new_markdown_cell(cell["source"])
        if cell["type"] == "markdown"
        else new_code_cell(cell["source"])
        for cell in cells
    ]
    return nbformat.writes(notebook)


def render_indexed(notebook_json: str) -> str:
    """Render a notebook as an index-labelled listing for downstream agents.

    Agents (student, reviewer, reviser) must reference cells unambiguously. Handing
    them raw .ipynb JSON led to off-by-one references. This labels every cell with
    the SAME absolute index the executor uses (position in notebook.cells, markdown
    included), so feedback and execution reports line up exactly.
    """
    notebook = nbformat.reads(notebook_json, as_version=4)
    lines = [
        f"This notebook has {len(notebook.cells)} cells, indexed 0..{len(notebook.cells) - 1}. "
        "Reference cells by these exact indices.",
        "",
    ]
    for index, cell in enumerate(notebook.cells):
        lines.append(f"[cell {index} · {cell.cell_type}]")
        lines.append(cell.source if cell.source.strip() else "(empty)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```json ... ``` or ``` ... ``` fence if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # Drop the opening fence (optionally "```json") and the closing fence.
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
