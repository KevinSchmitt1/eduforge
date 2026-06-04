"""eduforge command-line interface.

Usage:
    eduforge build --topic "How a hash map works"
    eduforge build --topic "..." --config config/pipeline.skeleton.yaml \
        --profile profiles/default.md
    eduforge clean --keep 10

Bundled defaults (pipeline configs, personas, the default profile) ship with the
package. Run output is written to ./runs in the current working directory. Keys are
read from the environment or a local .env (OPENAI_API_KEY, or OLLAMA_BASE_URL for
local inference).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .config import load_pipeline
from .orchestrator import Orchestrator

# Repository/package root — where the bundled config/personas/profiles live.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "pipeline.review-loop.yaml"
DEFAULT_PROFILE = PACKAGE_ROOT / "profiles" / "default.md"
DEFAULT_PERSONAS = PACKAGE_ROOT / "personas"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "clean":
        return _cmd_clean(args)
    return _cmd_build(args)


def _cmd_build(args) -> int:
    # Keys come from the environment or a local .env (current dir or package root).
    _load_dotenv(Path.cwd() / ".env")
    _load_dotenv(PACKAGE_ROOT / ".env")

    pipeline = load_pipeline(args.config)
    profile = _read_profile(Path(args.profile))
    orchestrator = Orchestrator(
        pipeline=pipeline,
        personas_dir=Path(args.personas),
        runs_root=Path(args.runs),
    )

    print(f"▶ pipeline '{pipeline.name}'  ({len(pipeline.stages)} stages)")
    print(f"  learner profile: {args.profile}\n")
    try:
        store = orchestrator.run(
            args.topic, profile, profile_label=Path(args.profile).name,
            on_stage=_print_stage,
        )
    except Exception as exc:  # noqa: BLE001 — top-level: report cleanly, exit non-zero
        print(f"\n✗ pipeline failed: {exc}", file=sys.stderr)
        return 1

    print(f"\n✓ done — open {store.run_dir / 'lesson.ipynb'}")
    print(f"  summary: {store.run_dir / 'SUMMARY.md'}")
    return 0


def _cmd_clean(args) -> int:
    """Prune old run directories, keeping the newest --keep. Manual only — never
    runs automatically. Run dirs sort chronologically by their timestamp prefix."""
    runs_root = Path(args.runs)
    if not runs_root.is_dir():
        print(f"No runs directory at {runs_root} — nothing to clean.")
        return 0

    run_dirs = sorted((p for p in runs_root.iterdir() if p.is_dir()), reverse=True)
    to_remove = run_dirs[args.keep:]
    if not to_remove:
        print(f"{len(run_dirs)} run(s) present; keeping newest {args.keep} — nothing to remove.")
        return 0

    for path in to_remove:
        shutil.rmtree(path)
    print(f"Removed {len(to_remove)} old run(s); kept newest {args.keep}.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eduforge", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a lesson notebook from a topic")
    build.add_argument("--topic", required=True, help="The lesson topic or brief")
    build.add_argument(
        "--config", default=str(DEFAULT_CONFIG),
        help="Path to the pipeline YAML (default: bundled review-loop pipeline)",
    )
    build.add_argument(
        "--profile", default=str(DEFAULT_PROFILE),
        help="Learner profile: prior knowledge + environment/prerequisites",
    )
    build.add_argument(
        "--personas", default=str(DEFAULT_PERSONAS),
        help="Directory holding persona/system-prompt files",
    )
    build.add_argument(
        "--runs", default=str(Path.cwd() / "runs"),
        help="Root directory for run outputs (default: ./runs)",
    )

    clean = sub.add_parser("clean", help="Prune old run directories (manual)")
    clean.add_argument(
        "--keep", type=int, default=10,
        help="Number of most-recent runs to keep (default: 10)",
    )
    clean.add_argument(
        "--runs", default=str(Path.cwd() / "runs"),
        help="Root directory for run outputs (default: ./runs)",
    )
    return parser


def _read_profile(path: Path) -> str:
    """Load the learner profile file. A profile is required so every stage knows
    who the lesson is for and what environment it targets."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Learner profile not found: {path}. Pass --profile or use the bundled "
            "profiles/default.md."
        )
    return path.read_text(encoding="utf-8")


def _print_stage(name: str, status: str, detail: str) -> None:
    glyph = {"start": "…", "done": "✓", "error": "✗"}.get(status, "·")
    suffix = f"  → {detail}" if status != "start" else f"  ({detail})"
    print(f"  {glyph} {name}{suffix}")


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, no external dependency. Does not
    overwrite variables already present in the environment."""
    import os

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


if __name__ == "__main__":
    raise SystemExit(main())
