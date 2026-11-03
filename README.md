# wise-code

Personal Claude Code plugin for learning-first development. You own the design;
the assist level decides how much code Claude writes.

Fork of [VibeWise](https://github.com/nykooi1/vibe-wise) by Noah Kim (MIT).
Main changes: three assist levels (`skills/learn/assist-levels.md`), a Teach mode
for topic lessons, per-project learning materials (Q/A history, question bank,
Anki cards) with a Quiz command, and learner-first versions of several
[pstack](https://github.com/cursor/plugins/tree/main/pstack) skills by Lauren Tan
(MIT; see `THIRD_PARTY_NOTICES.md`).

| Level | Claude gives | You write real code |
|---|---|---|
| Hint (default) | Direction only, one hint at a time | Yes |
| Pseudo | Language-aware pseudocode + concepts | Yes |
| Full code | The agreed implementation | No |

At Hint and Pseudo, Claude never edits your source files. When you finish a step,
it runs a Code review: reads your changes, runs the project's checks, and gives
feedback at your level.

## Commands

Build and learn:

- `/wise-code:learn` — start or resume learning mode while building.
- `/wise-code:level [hint|pseudo|full] [for <topic>]` — show or set the assist level.
- `/wise-code:teach [topic]` — multi-session lessons on a topic, kept in this project.
- `/wise-code:explore <question>` — how or why existing code works: you predict,
  Claude checks the prediction against the code and its Git history. Read-only.
- `/wise-code:sharpen <task>` — make a task deeper, not bigger; you rewrite it.
- `/wise-code:grill <plan>` — stress-test a plan in rounds of questions until
  nothing is left assumed.
- `/wise-code:grill-with-docs <plan>` — the same inside a repo, keeping
  `GLOSSARY.md` and ADRs in `docs/adr/` as decisions settle.
- `/wise-code:research <question>` — answer an external question (API behavior,
  spec, version claim) from primary sources in one cited Markdown file. Each
  Evidence line carries a short «verbatim span» from the page it links;
  `skills/research/verify_quotes.py` checks every span against the live page
  before the report goes out.
- `/wise-code:shelf [question]` — send you to the exact section of your own
  books (a private shelf repo) for a concept question; you read, explain it back,
  and the shelf records it. No question, run in the shelf repo: status report.
  Needs setup: [docs/shelf-setup.md](docs/shelf-setup.md).

In a project with an active learning profile, both grills ask for your answer
before showing Claude's recommendation, and in grill-with-docs you write the ADRs.
Without a profile they behave as plain grills. When you describe a plan that
still has open decisions and nothing is built yet, Claude adds one line naming
them and suggesting `/wise-code:grill`; it grills only when you run the command
or ask to be grilled. `research` starts on its own when you say "find out" or
"check the docs". `shelf` starts on its own for concept questions, but only in a
project with `.wise-code/shelf.md`; elsewhere it stays silent. The other commands
run only when you call them.

Review and retain:

- `/wise-code:quiz [topic] [count]` — spaced-retrieval quiz from this project's question bank.
- `/wise-code:critique <file>` — feedback on your ADRs, docs, TIL entries, PR
  descriptions and commit messages; you rewrite.
- `/wise-code:correct [topic]` — turn mistakes you made twice into checks you
  write (types, lint, tests), proven against the old mistake.
- `/wise-code:reflect` — you write the session reflection; Claude checks it against
  the evidence and collects fixes for WiseCode itself.
- `/wise-code:reset` — back up learning notes and restart onboarding.

Switch levels in chat at any time:

- `level hint` / `level pseudo` / `level full` — change the default.
- `pseudo for Rust`, `hint for FastAPI`, `pseudo for writing` — per-topic override.
- `full code for this step` — one step only.

## Codex: the senior developer

The skills above are Claude-only: Claude is the teacher. Codex installs from the
same repository (`.codex-plugin/`) but loads only `codex/skills/`, a separate
senior-developer role you call in on purpose, never on its own:

- `$wise-code:consult` — at your assist level (Hint stays a hint) and logged.
  Two kinds: a *doubt* about a teacher decision, hint or explanation (Codex
  asks what you tried and know, then checks the teacher's claim against the code
  and primary sources), or an independent *question* on syntax, config or a tool
  (it asks only if you gave no context). It never edits your code or the
  learning graph. Each consult is appended to `.wise-code/consult/journal.md`
  through `scripts/consult.py`; at the next session start (or compaction)
  Claude is told how many consults came in and how many doubts disagree with
  it, reads them, and re-examines its own call with you.
- `$wise-code:google` — a quick lookup answered in full, ignoring the assist
  level, from primary sources and checked against this project's versions. Not
  logged anywhere; your choice to step outside the learning loop for one answer.
- PR review: a clean-code pass on an open pull request, on request (in progress).

Consult replies start with `=>> senior on call <<=`; lookups with
`=>> senior lookup <<=`.

## Canary

Every WiseCode reply starts with the line `=====> ah0y_sir <name>` and ends
with `<===== f1n` (stated in each skill and in the restore hook for active
projects). Each new conversation opens by asking your name (first line
`=====> ah0y_sir` until you answer); the name is never stored.

It starts at the first reply of a session in a project with an active profile or
a shelf (the hook), or when any wise-code skill first loads, and then stays on
for every reply until the conversation ends, whatever the task. A missing start
or end line means the reply was cut off or the instructions were dropped, usually
after a long context or a compaction: a sign that quality may be slipping. It
marks a complete, on-instruction reply, not a true one; facts are guarded by
research's span check.

PR reviews of this repository (`@codex review`) carry their own canary: every
review message starts with `=>> Incoming harsh truth <<=`. A review without it
means the Code Review Rules in `AGENTS.md` were not loaded.

## Principles

`skills/learn/principles.md` is a shared vocabulary for design and review: data
structures first, model the domain, type-system discipline, boundary discipline,
test behavior not implementation, fix root causes, explain the number, and more.
Claude names the principle a problem touches, with a guiding question; you decide
whether and how it applies. At Hint, the name is the first hint. When you report a
measured number, Claude asks the "Checking a number" questions instead of running
the benchmark for you.

## Quality gates

`skills/learn/gates.md` adds Uncle Bob's deterministic gates from
[ub-mode](https://github.com/unclebob/ub-mode):
[crapper](https://github.com/unclebob/crapper) (CRAP < 10 per function),
[dryer](https://github.com/unclebob/dryer) (no duplication at similarity 0.8) and
[mutator](https://github.com/unclebob/mutator) (no surviving mutants). Crapper and mutator run on
the changed code; dryer scans the whole tree with `--threshold 0.8` and reports
only pairs that touch changed code, so copies from unchanged files are caught.
Code review runs the ones you have installed and reports
the numbers; at Hint and Pseudo you fix what they find. At Full code Claude
follows ub-mode's order: failing test first, make it work, then make it right
against the gates. Missing tools are skipped; Claude never installs them.

## One learning space per project

Start WiseCode in repository A and everything it keeps lives in repository A's
`.wise-code/`, at the Git root (or the current folder outside Git). It never
reads or writes another project's notes, a parent repository's, or a global folder.

```
<repo>/.wise-code/
  profile.md          learner profile and preferences for this project
  project-map.md      the system as you understand it
  graph/              the learning graph: everything else WiseCode records
    nodes.jsonl       concepts, Q/A, questions, cards, sessions, decisions,
    edges.jsonl       guardrails, reflections, plugin feedback, learning records,
                      and index entries for lessons, research, ADRs, the mission
  cards.tsv           Anki export, regenerated by `wise.py export anki`
  inbox/              lesson results waiting to be imported
  teach/              Teach workspace files: mission, lessons, reference, assets
  shelf.md            shelf config (opt-in); see docs/shelf-setup.md
  shelf-repo/         sparse clone of your shelf, gitignored
  backups/            created by /wise-code:reset and by the Markdown import
```

The one opt-in exception: with `shelf.md`, the project reads its mapped folders of
your shelf repo and pushes citation records to the shelf's own graph. Book records
live in the shelf, project records in the project.

Files appear lazily, when there is something to put in them. Add `.wise-code/` to
the project's `.gitignore` if the notes should stay local.

The plugin itself is shared by every project, so it holds only instructions,
rubrics, templates, helper scripts and tests. No learner data. Improvements found
during a project land in that project's plugin feedback (`wise.py list feedback`);
you apply them here.

## The learning graph

All learning data goes through one script, `scripts/wise.py` (standard-library
Python 3.9+, required). Claude never reads the JSONL files; it asks the script for
the slice a step needs, and every query stops at about 1.5k tokens. Spec:
[docs/graph.md](docs/graph.md); commands and conventions:
`skills/learn/materials.md`.

- **IDs** are `PREFIX-YYYYMMDD-xxxx`, unique without coordination; concepts are
  slugs with aliases, and near-duplicates are refused. Two machines, or two
  projects writing to the shelf, merge with git's `union` driver and no
  conflicts.
- **Your words, quoted:** a decision you made or reasoning you gave is stored
  with a verbatim span of your message (`said`). `wise.py check-said` matches it
  against this project's session transcripts, so Claude can't later "remember"
  you saying something you didn't. Anything else is labeled as Claude's note.
- **Read it yourself:** `wise.py render all --out <folder>` writes Markdown views;
  `wise.py edit <id>` changes one node in your editor; `wise.py check` validates.
- **Old notes:** a project with the earlier Markdown files is converted once with
  `wise.py import-md` (the hook reminds Claude); originals go to `backups/`.
- **No Python, or the command blocked:** Claude stops learning writes and shows
  the fix (install Python, or allow `Bash(python3 *wise.py*)`). Coding help goes on.
- **`blockReadsOutsideWorkingDirectories` on:** the plugin lives outside your
  project, so its scripts would be refused. At session start the hook notices
  and Claude offers to add the plugin folder to `permissions.additionalDirectories`
  in `~/.claude/settings.json` (**Add it** / **Show me only** / **Not now**); it
  never edits the file without your yes. `Settings prompt: off` in `profile.md`
  stops the offer.
- **Code:** WiseCode doesn't index your code. If a code-graph MCP server is
  installed, Explore and Code review use it (and compare it with your
  `project-map.md`); otherwise Read and Grep.

What a step reads, before (whole Markdown files) and after (one query), on the
test fixture (300 Q/A, 100 questions, 30 concepts, 5 sessions;
`python3 tests/measure_tokens.py`):

| Command | Before (tokens) | After (tokens) | Saved |
|---|---:|---:|---:|
| quiz: find due questions | 8,018 | 390 | 96% |
| start check | 660 | 146 | 78% |
| restore: pending decisions + weak topics | 1,619 | 246 | 85% |
| correct: repeated mistakes | 23,489 | ≈1,020 | 96% |
| history of one concept | 21,808 | 375 | 99% |
| teach: what is known | 1,671 | 229 | 87% |

## Learning materials

- **Q/A history**: checkpoint answers, Code review findings, quiz answers, lesson
  exercises, Explore predictions, writing issues, and your own questions worth
  keeping. Gists, not transcripts.
- **Question bank**: why/how/tradeoff questions tied to the project. `/wise-code:quiz`
  asks the due ones and reschedules them (Leitner boxes: 1, 3, 7, 21, 60 days).
- **Anki cards**: one atomic fact per card. `wise.py export anki` writes `cards.tsv`;
  import it with File → Import.
  Re-importing the whole file is safe: Anki matches the front, updates the note and
  keeps its review schedule. Each project gets its own deck, `wise-code::<project>`.
- **Session recap + start check**: when you stop ("done for today", "wrap up",
  or `/wise-code:reflect`), Claude adds an evidence-backed session recap to the
  graph: finished, learned, decided, open, and 3–5 check points.
  The next new session (startup or `/clear`, not resume or compaction) opens
  with a start check before any other work: 2–3 multiple-choice questions and
  1–2 open questions on those check points, recap hidden until you answer.
  Answers become `start-check` Q/A; misses enter the question bank.
  Say "skip" to skip. On claude.ai there is no SessionStart hook, so the check
  runs when you invoke `/wise-code:learn`.
- **Confidence and repair**: answer checkpoint, quiz and repair questions with a
  confidence prefix (`high: …`, `mid: …`, `low: …`). A wrong answer, or a partial
  one you were sure of, is a confusion. Before the next build step on that
  concept (or one that depends on it), Claude asks you one fresh question about
  your code that targets that confusion; a correct answer to it (a *different*
  question from the one you missed) repairs it. Getting some other question on
  the same concept right doesn't. You can say
  "skip repair", but only 2 skips may stay open; past that, repair first.
  `wise.py calibration` shows how well your confidence predicts your answers.
- **Guardrails**: one row per repeated mistake: the evidence, the level that
  enforces it, and the proof that it fails on the old mistake.

Claude proposes questions and cards and tells you in one line what it added. Edit
or delete them freely; your own wording beats Claude's.

`/wise-code:reset` resets profile, progress and map only. Learning materials and
`teach/` are kept.

## Install (Claude Code)

```sh
/plugin marketplace add /absolute/path/to/wise-code
/plugin install wise-code@wise-code
```

Restart Claude Code, then run `/wise-code:learn` or `/wise-code:teach` in your project.

If you also have a standalone `/teach` skill installed, remove it: it uses the
current directory as its workspace, while `/wise-code:teach` uses the project's
`.wise-code/teach/`. The same goes for account-level `grilling`,
`grill-with-docs` and `research` skills: with both installed, the same request can
trigger either copy.

## Development

Run tests: `python3 -m unittest discover -s tests`, and check the plugin with
`claude plugin validate .`.

The repository is one plugin. claude.ai syncs the whole repository as that
plugin and rejects a second `plugin.json` anywhere below the root, so a test
fails if one appears.
