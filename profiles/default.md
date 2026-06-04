# Learner profile (default)

This is the single source of truth for **who the lesson is for**. Every stage reads
it: the planner pitches to this level, the code author assumes this environment, and
the student role-plays *this exact person*. Copy this file and edit it (then pass
`--profile your_profile.md`) to target a different learner. See `examples/profiles/`
for filled-in examples.

## Who the learner is
A practising software developer who learns a new IT topic best when theory is paired
immediately with small, runnable code, and when new ideas are anchored to things
they already know. Comfortable reading and running code; wants to understand the
mechanics, not just copy snippets.

## Already knows well — do NOT re-explain these
- General programming: variables, functions, control flow, data structures
- Python syntax and the standard library
- Running code in a Jupyter notebook
- Basic command-line usage and installing packages with pip

When the lesson uses any of the above, use it freely as a building block — don't
spend cells teaching it.

## Still building up — DO explain these carefully
- The specific topic of the lesson (assume it is new to the learner)
- Any domain-specific jargon, notation, or library APIs the topic introduces
- The "why": motivation and intuition behind the technique, not just the steps

Introduce these from first principles, ideally by analogy to the "already knows"
list. If a lesson assumes one of these without explaining it, that is a defect the
student agent should flag.

## Environment / prerequisites the material must target
- A standard laptop (no GPU assumed). Code must run on CPU.
- Python 3.10+ in a Jupyter environment.
- Prefer dependency-light demos using the standard library, numpy, or matplotlib.
  Any heavier dependency or data/model download must be called out explicitly in the
  lesson's prerequisites and justified.
- Assume no special network access; demos should work offline once dependencies are
  installed.
