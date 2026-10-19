# wise-code

Personal Claude Code plugin for learning-first development. You own the design;
the assist level decides how much code Claude writes.

Fork of [VibeWise](https://github.com/nykooi1/vibe-wise) by Noah Kim (MIT).
Main changes: three assist levels (`skills/learn/assist-levels.md`), a Teach mode
for topic lessons, and per-project learning materials (Q/A history, question bank,
Anki cards) with a Quiz command.

| Level | Claude gives | You write real code |
|---|---|---|
| Hint (default) | Direction only, one hint at a time | Yes |
| Pseudo | Language-aware pseudocode + concepts | Yes |
| Full code | The agreed implementation | No |

At Hint and Pseudo, Claude never edits your source files. When you finish a step,
it runs a Code review: reads your changes, runs the project's checks, and gives
feedback at your level.

## Commands

- `/wise-code:learn` — start or resume learning mode while building.
- `/wise-code:level [hint|pseudo|full] [for <topic>]` — show or set the assist level.
- `/wise-code:teach [topic]` — multi-session lessons on a topic, kept in this project.
- `/wise-code:quiz [topic] [count]` — spaced-retrieval quiz from this project's question bank.
- `/wise-code:reset` — back up learning notes and restart onboarding.

Switch levels in chat at any time:

- `level hint` / `level pseudo` / `level full` — change the default.
- `pseudo for Rust`, `hint for FastAPI` — per-topic override.
- `full code for this step` — one step only.

## One learning space per project

Start WiseCode in repository A and everything it keeps lives in repository A's
`.wise-code/`, at the Git root (or the current folder outside Git). It never
reads or writes another project's notes, a parent repository's, or a global folder.

```
<repo>/.wise-code/
  profile.md        learner profile and preferences for this project
  progress.md       concepts introduced, demonstrated, needing reinforcement
  project-map.md    the system as you understand it
  qa-history.md     dated log of questions and answers, both directions
  questions.md      question bank with spaced-repetition schedule
  cards.tsv         flashcards in Anki's import format
  teach/            Teach workspace: mission, lessons, reference, learning records
  backups/          created by /wise-code:reset
```

Files appear lazily, when there is something to put in them. Formats are defined in
`skills/learn/materials.md`. Add `.wise-code/` to the project's `.gitignore` if the
notes should stay local.

The plugin itself is shared by every project, so it holds only instructions,
templates (`skills/learn/state-templates.md`, `skills/teach/templates/lesson.css`),
helper scripts and tests. No learner data.

## Learning materials

- **Q/A history**: checkpoint answers, Code review findings, quiz answers, lesson
  exercises, and your own questions worth keeping. Gists, not transcripts.
- **Question bank**: why/how/tradeoff questions tied to the project. `/wise-code:quiz`
  asks the due ones and reschedules them (Leitner boxes: 1, 3, 7, 21, 60 days).
- **Anki cards**: one atomic fact per card. Import with File → Import → `cards.tsv`.
  Re-importing the whole file is safe: Anki matches the front, updates the note and
  keeps its review schedule. Each project gets its own deck, `wise-code::<project>`.

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
`.wise-code/teach/`.

## Development

Run tests: `python3 -m unittest discover -s tests`
