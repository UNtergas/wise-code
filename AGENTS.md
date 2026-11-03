# AGENTS.md

Rules for any agent working on this repository (Codex, Claude Code through
`CLAUDE.md`, or another). This file governs development of the WiseCode plugin
itself. It is not loaded into projects that use the plugin.

In those projects, WiseCode is learner-first: the learner writes the code. Here
it is the other way round: you write the code for WiseCode, so the full
engineering discipline below applies to you.

## Repository facts

- Run the tests with `python3 -m pytest -q tests`. All must pass before a commit.
- `scripts/wise.py` and the hooks are standard library only, Python 3.9+. Don't
  add dependencies or newer syntax.
- Each skill in `skills/<name>/` has `SKILL.md` (frontmatter `name` and
  `description`) and is Claude-only: no `codex.md`, no `agents/openai.yaml`.
  Learning commands keep `disable-model-invocation: true`;
  `tests/test_skills.py` enforces the layout.
- Codex is the on-demand senior developer, not the teacher. Its skills live in
  `codex/skills/`, the only folder `.codex-plugin/plugin.json` loads.
- Model hints (`model: sonnet`) go in the skill body, never in frontmatter.
- Every skill keeps its Canary section; don't edit or drop it.
- The plugin ships no learner data. Learning state lives in each project's
  `.wise-code/` and is written only through `wise.py`. Never write the JSONL
  files directly.
- Releases bump `version` in both `.claude-plugin/plugin.json` and
  `.codex-plugin/plugin.json`.
- Borrowed material is credited in `THIRD_PARTY_NOTICES.md` with its license.

## Working rules

Adapted from ub-mode by Robert C. Martin (MIT; see `THIRD_PARTY_NOTICES.md`).
Every change follows: first make it work, then make it right, then practice.

### First make it work

- Smallest edit that solves the problem. One decision lives in one place.
- Get the data shape right before the logic.
- Test first: write the failing test, run it, and see it fail for the reason
  you expect. Then make the smallest change that passes. If an honest test is
  impractical, say so; don't write a test that checks nothing.
- Don't bolt a requirement onto the old design: ask what you would build if it
  had been there from day one, then deliver that in pieces.
- Take complexity out before adding any.
- When two fixes sharing one assumption fail, write the assumption down and
  test it before a third fix.
- Check data where it enters (CLI args, JSON lines, files, paths); trust it
  inside. Keep logic in pure functions.
- Operations are idempotent: running twice, or after a crash halfway, ends in
  the same state.

### Then make it right

- Fix root causes. Reproduce first. A guard that hides the crash is not a fix.
- Work in small units you can verify, one at a time.
- Tests call the code the way its user does and check what that user would see.
  A test that passes on the old code, or passes when nothing is found, proves
  nothing: check new tests fail on the code before the fix.
- Refactor only with behavior pinned by tests; rerun them after.
- Quality gates, when installed (see `skills/learn/gates.md`): crapper on
  changed code (CRAP < 10), dryer on the whole tree with `--threshold 0.8`,
  mutator on changed code before opening a PR. Report gates that didn't run as
  "not run".
- One source of truth: when a behavior is described in several places (README,
  a guide, a test), change them in the same commit, or make the others point
  to the one that defines it.

### Practice

- Never commit to `main` and never force-push. Work on a branch; open a PR.
- Small commits, ordered so each proves itself. Each message says why, what
  changed, and how it was checked.
- The PR description is the log: what changed, the decisions taken, and the
  evidence (tests, reproductions, numbers).
- Answer every review comment with the commit that addresses it, or with the
  evidence for not changing it.

## Code Review Rules

Applies to every pull request in this repository.

### Canary

Start every review message (the summary and each inline comment) with this
exact line, on its own, before anything else:

```
=>> Incoming harsh truth <<=
```

A review without it means these rules were not loaded. Don't paraphrase it,
translate it, or drop it when there are no findings.

### Priorities

- **P0:** loss or silent corruption of learner data (graph records, Q/A
  history, decisions); writes outside `.wise-code/` or through symlinks;
  learner data shipped in the plugin.
- **P1:** wrong behavior; a skill that writes code or answers for the learner
  where the learner should (Hint and Pseudo levels, learner-first commands);
  documents that contradict each other or the code; tests that pass vacuously or
  that would pass on the old code; a missing license notice for borrowed
  material.
- Skip style preferences and wording nits unless they change meaning.

### Evidence

- Verify every claim against the code at the reviewed commit and cite
  `file:line`.
- Reproduce the failure, or say it wasn't reproduced and why the reasoning
  still holds.
- For a claim about another project's tool or API, read its source or docs and
  link the exact place.
- Quote errors and tool output exactly.

### What to check

- Learner-first: at Hint and Pseudo, skills never edit the learner's source,
  and learner-first commands keep the learner acting first.
- Graph integrity: every write goes through `wise.py`; concurrent or
  interrupted writes can't lose records or leave a mixed graph; stored types and
  ranges stay valid; two clones' edits to one record are never resolved by
  silently dropping one.
- Tests: new behavior has a test that failed before the change; assertions
  can't pass on an empty result.
- Consistency: README, guides under `skills/`, `docs/`, and test assertions
  describe the same behavior.
- Compatibility: Python 3.9, standard library only, Linux, macOS and Windows.

### Comment format

One finding per comment: where it is, the concrete failure it causes, the
requested change, and the evidence that would show it fixed. When there are no
findings, say what was checked.
