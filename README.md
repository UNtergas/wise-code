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
  spec, version claim) from primary sources in one cited Markdown file.

In a project with an active learning profile, both grills ask for your answer
before showing Claude's recommendation, and in grill-with-docs you write the ADRs.
Without a profile they behave as plain grills. `grill` starts on its own whenever
you describe a plan that still has open decisions and nothing is built yet; it
says which decisions it sees, and "skip" or "just build it" stops it.
`research` starts on its own when you say "find out" or "check the docs". The
other commands run only when you call them.

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

## Principles

`skills/learn/principles.md` is a shared vocabulary for design and review: data
structures first, model the domain, type-system discipline, boundary discipline,
test behavior not implementation, fix root causes, explain the number, and more.
Claude names the principle a problem touches, with a guiding question; you decide
whether and how it applies. At Hint, the name is the first hint. When you report a
measured number, Claude asks the "Checking a number" questions instead of running
the benchmark for you.

## One learning space per project

Start WiseCode in repository A and everything it keeps lives in repository A's
`.wise-code/`, at the Git root (or the current folder outside Git). It never
reads or writes another project's notes, a parent repository's, or a global folder.

```
<repo>/.wise-code/
  profile.md          learner profile and preferences for this project
  progress.md         concepts introduced, demonstrated, needing reinforcement
  project-map.md      the system as you understand it
  qa-history.md       dated log of questions and answers, both directions
  questions.md        question bank with spaced-repetition schedule
  cards.tsv           flashcards in Anki's import format
  guardrails.md       repeated mistakes and the check that now prevents each
  reflections.md      your session reflections, in your words
  plugin-feedback.md  proposed fixes to WiseCode, to apply in this repository
  teach/              Teach workspace: mission, lessons, reference, learning records
  backups/            created by /wise-code:reset
```

Files appear lazily, when there is something to put in them. Formats are defined in
`skills/learn/materials.md`. Add `.wise-code/` to the project's `.gitignore` if the
notes should stay local.

The plugin itself is shared by every project, so it holds only instructions,
rubrics, templates, helper scripts and tests. No learner data. Improvements found
during a project land in that project's `plugin-feedback.md`; you apply them here.

## Learning materials

- **Q/A history**: checkpoint answers, Code review findings, quiz answers, lesson
  exercises, Explore predictions, writing issues, and your own questions worth
  keeping. Gists, not transcripts.
- **Question bank**: why/how/tradeoff questions tied to the project. `/wise-code:quiz`
  asks the due ones and reschedules them (Leitner boxes: 1, 3, 7, 21, 60 days).
- **Anki cards**: one atomic fact per card. Import with File → Import → `cards.tsv`.
  Re-importing the whole file is safe: Anki matches the front, updates the note and
  keeps its review schedule. Each project gets its own deck, `wise-code::<project>`.
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
