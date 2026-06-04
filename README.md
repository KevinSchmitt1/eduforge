# eduforge

**A multi-agent CLI that builds — and self-checks — IT learning notebooks.**

eduforge turns a one-line topic into a runnable Jupyter notebook by passing it
through a pipeline of role-specialised agents (planner → code author → executor →
student → reviser …). Crucially, one stage **actually executes** the generated
notebook and captures what every cell really does, so the explanations are checked
against reality instead of assumption.

It exists to kill a specific failure mode: teaching material whose prose claims
things the code doesn't actually do.

## Why it's built this way

- **Sandboxed agents** — each agent sees only its persona and its declared inputs,
  never the others' reasoning. They behave like distinct collaborators.
- **Reality-checked** — the executor runs the notebook; the student/reviewer judge
  the *real* outputs. Regressions are caught, not shipped.
- **Reproducible** — every run writes a self-contained directory with the deliverable
  notebook, a readable summary, and a manifest.
- **Dynamic** — the "team" is a YAML file. Add, remove, or reorder stages without
  touching Python.
- **Retargetable** — *who* the lesson is for lives in one swappable profile file.
  Point it at a beginner, an expert, any environment — the whole pipeline recalibrates.
- **Local or cloud** — the same code talks to OpenAI or a local Ollama server; only
  the `base_url` differs. Point at Ollama and nothing leaves your machine.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # editable install; adds the `eduforge` command
cp .env.example .env        # then put your OPENAI_API_KEY in .env
```

## Use

```bash
# Full pipeline (plan → author → run → student → revise → re-run → re-check)
eduforge build --topic "How a Bloom filter works"

# Cheaper, shorter pipeline
eduforge build --topic "How a Bloom filter works" \
    --config config/pipeline.skeleton.yaml

# Target a specific learner
eduforge build --topic "Recursion and the call stack" \
    --profile examples/profiles/web-dev-beginner.md

# Run fully local / private (start `ollama serve`, set provider: ollama in the YAML)
```

Output lands in `./runs/<timestamp>_<pipeline>/`:

- `lesson.ipynb` — the deliverable, with **real cell outputs** baked in
- `SUMMARY.md` — per-stage status, any execution failures, plan + feedback inline
- `manifest.json` — provenance (what was produced and pruned)

Intermediate plumbing (raw JSON reports, draft notebooks) is pruned automatically on
success; failed runs keep everything for debugging.

### Housekeeping

Run directories are never auto-deleted. Prune them yourself:

```bash
eduforge clean --keep 10     # keep the 10 newest runs
```

## How it fits together

```
brief    ┐                                                   executor ─► report
profile  ┴► planner ─► plan ─► code_author ─► notebook ─►  └─► student ─► feedback
                                                          (runs it!)
            … reviser ─► executor ─► student  (the review-loop config repeats this)
```

| Module | Responsibility |
|--------|----------------|
| `eduforge/config.py` | Load + validate the pipeline YAML (dataflow checked) |
| `eduforge/artifacts.py` | Immutable artifacts + reproducible run dirs + cleanup |
| `eduforge/llm.py` | Pluggable OpenAI/Ollama client |
| `eduforge/notebook.py` | Assemble `.ipynb` from JSON cells; index-label for agents |
| `eduforge/agent.py` | `LLMAgent`: persona + inputs → one output artifact |
| `eduforge/executor.py` | Run the notebook, capture per-cell errors (anti-bug) |
| `eduforge/report.py` | Human-readable `SUMMARY.md` |
| `eduforge/orchestrator.py` | Run stages, pass artifacts, finalize the run |
| `eduforge/cli.py` | `eduforge build` / `eduforge clean` |

Pipelines live in `config/`, agent system-prompts in `personas/`, learner profiles
in `profiles/` (with more in `examples/profiles/`).

## Customise

- **New learner:** copy `profiles/default.md`, edit, pass `--profile`.
- **New team shape:** copy a file in `config/`, add/remove/reorder stages, pass
  `--config`. A stage references upstream outputs by name; the loader fails fast if
  the dataflow is broken.
- **New role:** drop a system-prompt in `personas/`, reference it from a stage.

## Tests

```bash
pip install -e ".[dev]"
pytest -q          # offline: no API key needed
```

Covers config validation, notebook assembly, cell indexing, the executor catching a
failing cell, run finalization, summary generation, and the clean command.

## License

MIT.
