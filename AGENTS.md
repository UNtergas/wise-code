# AGENTS.md

Rules for any agent working on this repository (Codex, Claude Code through
`CLAUDE.md`, or another). This file governs development of the WiseCode plugin
itself. It is not loaded into projects that use the plugin.

In those projects, WiseCode is learner-first: the learner writes the code. Here
it is the other way round: you write the code for WiseCode, so the full
engineering discipline below applies to you.

## Repository facts

- Run the tests with `python3 -m pytest -q tests`. All must pass before a commit.
  CI (`.github/workflows/tests.yml`) runs them on Python 3.9 and 3.13 for every
  pull request and every push to `main`.
- `tests/test_e2e.py` walks one learner through two weeks using the real entry
  points (the session hook as registered, `wise.py` as the skills call it).
  Unit tests cover a rule's edges; the journey covers the joins between
  commands.
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
  written only by Codex, through `scripts/consult.py`; the teacher's
  acknowledgments (`.wise-code/consult-acks.txt`) only by Claude, through
  `consult.py ack`. Codex also counts lookups (`consult.py lookup`, date and
  topic only) in `.wise-code/consult/lookups.txt`.
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

## Changing WiseCode

A checklist for the next change, from what went wrong and right in earlier ones.

### Before you start

- Sync `main` and check for open pull requests and review comments first.
- One branch per change. Dependent changes are stacked pull requests, merged
  in order with merge commits, each retargeted to `main` before its merge.
- Read the guide that calls the code you are changing. A command and the skill
  step that runs it are one behavior.

### What a change to `wise.py` includes

1. A failing test that calls the command line the way a skill does.
2. The check where the data enters (an argparse `type`, or the top of the
   command). A stricter rule applies when a record is written, never when one
   is loaded: older graphs and imports must keep working.
3. The guides, in the same commit: `skills/learn/materials.md` (the reference
   for every command), the skill step that runs the command, `docs/graph.md`,
   and the README when the learner sees the difference.
4. `tests/test_e2e.py`, when the change alters what one command writes and
   another reads, or what the hook says.
5. `python3 tests/measure_tokens.py`, and the two tables (README,
   `docs/graph.md`) when a number moved.
6. The version, in both plugin manifests.

### Where a rule lives

- If the script can enforce a rule, it does (a refused command, a bounded
  verdict). A rule that exists only as text in a guide is a request.
- A rule the script can't enforce should leave a record `lint-session` can
  read (a quote, a prefix, a count). Add the flag with the rule.
- The script reports what Claude judged; it can't check the judgment. Make the
  judgment explicit and small (`--hit 1,3`, `--covers 2`), keep the learner's
  words beside it, and say in the pull request what stays unverified.
- The script never runs a command stored in the graph.
- A write command prints its record's id as the first line. Anything else it
  has to say (`confusion: …`) comes on later lines.

### What a change to the learning design includes

- The learner does the work. A change may not move writing, deciding or
  recalling from the learner to Claude.
- Every rule costs the learner time in every session. Say in the pull request
  what it costs, and what in `calibration`, `weak` or `lint-session` would show
  that it helps. Prefer changing what is practiced over adding what is tracked.
- A gate the learner can't skip needs a reason in the guide. Most can be
  skipped, and a skip is recorded or visibly not counted.

### Tests

- Import a test module, not its classes (`import test_session_start as hooks`):
  a test class imported by name is collected and run a second time.
- A question without key points can only be made through `import-md`; `add
  question` refuses it. A quote needs at least three words.
- Pass the day (`WISE_TODAY`) in every call; never depend on today's date or on
  the order of the random id suffix.
- Check that a new test fails before the change, for the reason you expect,
  and say in the commit which tests only pin existing behavior.
- A journey step in `tests/test_e2e.py` asserts what the scenario really
  implies. When one fails, first work out which is wrong, the code or the
  expectation, before changing either.

### Committing

- Run the whole suite and read its last line before every commit. Don't rely on
  `set -e` around a pipeline or a negated command: it doesn't stop.
- One commit per finding when the hunks separate cleanly. Don't split a file
  with zero-context patches (`git diff -U0` piped to `git apply`): it can
  misplace a hunk without an error. Build the commits in order, or commit the
  related files together and say why.
- A branch pushed with a failing commit is not rewritten: open a clean branch.
- Check the oldest supported Python before the pull request:
  `uv run --no-project --python 3.9 --with pytest python -m pytest -q tests`.
- A test that fails once is not rerun until green. Get its name (`-rfE`),
  reproduce it (in a loop, under load), and report it if it can't be found.

### Reporting

- State what was not run (a live Claude Code session, a gate, another OS).
- Guides are instructions to a model. A test can pin that a rule is written
  where Claude reads it, not that Claude follows it: say which kind each test is.

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

Where the review tool writes the summary itself (Codex on GitHub posts a fixed
receipt as the review body), the canary is checked on inline comments only.

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
- Codex on GitHub posts only P0 and P1 findings. P2 checks still apply, but they
  surface only in reviews that report every priority.
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

### Re-review

When the pull request already has review findings (yours or anyone's), account
for every earlier finding at the commit now reviewed:

- the finding's title and a link to its thread;
- **fixed**, **not fixed** or **can't tell**;
- the evidence: the `file:line` that now handles it, the test that covers it,
  or why the reasoning still fails.

Where you write the summary, it opens with that list, right after the canary.

Where you can only post inline findings (Codex on GitHub), the list has no
place in the review, so:

- Post every **not fixed** finding again, as an inline comment on the line that
  still has the problem, titled `Still not fixed: <title>`, with a link to the
  first thread and its original priority. A fixed finding needs no comment.
- The full list comes from a follow-up comment on the pull request, which Codex
  answers in a reply:
  `@codex For every earlier review finding on this pull request, say fixed, not fixed or can't tell at the latest commit, with file:line evidence.`

A reply in the thread that says "fixed" is a claim, not evidence: check the
code. A finding marked **not fixed** keeps its priority. A re-review that says
nothing about an earlier finding has not shown it fixed; only the list does.

### This repository

WiseCode-specific checks, on top of everything above.

- **P0:** loss or silent corruption of learner data (graph records, Q/A
  history, decisions, the consult journal); writes outside `.wise-code/`;
  learner data shipped in the plugin.
- **P1:** a skill that writes code or answers for the learner where the learner
  should (Hint and Pseudo levels, the learner's own problem at Example,
  learner-first commands).
- Learner-first: at Hint and Pseudo (and Example, where the only code is for a
  different problem), skills never edit the learner's source,
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
PR description go in the summary or, where you can't write one, in an inline
comment on the first changed line that starts with `PR description:`. When there are no findings, say what was
checked.
