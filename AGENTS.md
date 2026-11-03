# AGENTS.md

Rules for any agent working on this repository (Codex, Claude Code through
`CLAUDE.md`, or another). This file governs development of the WiseCode plugin
itself. It is not loaded into projects that use the plugin.

In those projects, WiseCode is learner-first: the learner writes the code. Here
it is the other way round: you write the code for WiseCode, so the full
engineering discipline below applies to you.

## Repository facts

- Run the tests with `python3 -m pytest -q tests`. All must pass before a commit.
- `scripts/` and the hooks are standard library only, Python 3.9+. Don't
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
  files directly. The senior consult journal (`.wise-code/consult/`) is
  written only by Codex, through `scripts/consult.py`.
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

Applies to every pull request in this repository. Review as a senior engineer
who wants the change to ship and keep working: find what breaks, say why, say
the fix. The design lens is clean code (Robert C. Martin), applied to the
failures it causes, not to taste.

These rules are portable: to use them in another repository, copy this file
there and replace `## Repository facts` and `### This repository` with that
repository's own. Everything else applies as written.

### Canary

Start every review message (the summary and each inline comment) with this
exact line, on its own, before anything else:

```
=>> Incoming harsh truth <<=
```

A review without it means these rules were not loaded. Don't paraphrase it,
translate it, or drop it when there are no findings.

### Priorities

`### This repository` adds its own P0 and P1 cases to these.

- **P0:** data loss or silent corruption; a security hole (secret committed,
  injection, missing authorization check, unsafe deserialization, writes
  through symlinks or outside the intended folder); an irreversible operation
  (delete, migration, payment) with no guard or rollback.
- **P1:** wrong behavior on a reachable path; an error swallowed on a path that
  changes state; a design problem below that already causes a bug or blocks
  testing; tests that pass vacuously or would pass on the old code; documents
  or a PR description that contradict each other or the code; a missing license
  notice for borrowed material.
- **P2:** a design problem below that will cost the next change; a PR
  description missing why, decisions or evidence.
- Skip formatting, naming taste and wording nits unless they change meaning;
  CI owns lint. Raise a name only when it lies about what the code does.

### Evidence

- Verify every claim against the code at the reviewed commit and cite
  `file:line`.
- Reproduce the failure, or say it wasn't reproduced and why the reasoning
  still holds.
- For a claim about a library, tool or API, read its source or docs and link
  the exact place, for the version this repository uses.
- Quote errors and tool output exactly.

### Design

Flag each only with the concrete failure it causes in this diff.

- **One reason to change:** a function or module that mixes I/O (database,
  network, filesystem, clock) with a decision, so the decision can't be tested
  without the I/O. Fix: pure function for the decision, thin shell for the I/O.
- **Dependency direction:** high-level code importing a concrete low-level
  implementation where an interface or injection point exists or is clearly
  needed. Fix: depend on the abstraction.
- **One decision, one place:** a rule (condition, calculation, limit)
  duplicated across the diff, especially when one copy changed and another did
  not.
- **Names that lie:** a function, flag or type whose name no longer matches
  what it does after this change (a `get` that writes, a boolean whose meaning
  flipped).
- **Boundaries:** input from outside (requests, files, env, CLI args, queue
  messages) used without validation where it enters, or validation repeated
  deep inside instead.
- **Errors:** empty catch, catch-log-continue, or a generic catch that hides a
  failure the caller must know about.
- **Size that hides bugs:** a function long or branching enough that a path in
  this diff is untested or unreadable. Point at the path, not the line count.

### Tests

- New or changed behavior has a test that fails without the change.
- Assertions can't pass on an empty result, a mock that returns what the test
  expects, or a skipped branch.
- Tests call the code the way its user does and check what that user sees, not
  private internals.
- A bug fix comes with a test that reproduces the bug.

### PR description

The description is the change's log. Check it like code:

- It matches the diff: everything it claims is in the commits, and nothing
  significant in the diff is left unmentioned.
- It says why the change is needed, not only what changed.
- It records the decisions taken and the alternatives rejected, when there
  were real ones.
- It gives evidence: test results, a reproduction, numbers. Checks that were
  skipped are listed as "not run", not left out.
- Breaking changes, migrations and required config are called out.

### This repository

WiseCode-specific checks, on top of everything above.

- **P0:** loss or silent corruption of learner data (graph records, Q/A
  history, decisions, the consult journal); writes outside `.wise-code/`;
  learner data shipped in the plugin.
- **P1:** a skill that writes code or answers for the learner where the learner
  should (Hint and Pseudo levels, learner-first commands).
- Learner-first: at Hint and Pseudo, skills never edit the learner's source,
  and learner-first commands keep the learner acting first.
- Graph integrity: every write goes through `wise.py`; concurrent or
  interrupted writes can't lose records or leave a mixed graph; stored types and
  ranges stay valid; two clones' edits to one record are never resolved by
  silently dropping one.
- Consistency: README, guides under `skills/` and `codex/skills/`, `docs/`, and
  test assertions describe the same behavior.
- Compatibility: Python 3.9, standard library only, Linux, macOS and Windows.

### Comment format

One finding per comment: where it is, the concrete failure it causes, the
requested change, and the evidence that would show it fixed. Findings on the
PR description go in the summary. When there are no findings, say what was
checked.
