# Learning graph

Everything WiseCode records about a project's learning lives in one graph,
read and written only through `scripts/wise.py`. Settled in a grill on 2026-10-28;
this file is the spec. Commands and writing conventions for Claude are in
`skills/learn/materials.md`.

## Why

Before the graph, every lookup read whole Markdown files: Quiz read all of
`questions.md` to find the due ones, Correct read all of `qa-history.md`, the
hook scanned `progress.md`. Cost grew with history. Now a query returns only the
slice a step needs, capped at about 1.5k tokens, and the cap is tested.

On the test fixture (300 Q/A, 100 questions, 30 concepts, 5 sessions;
`python3 tests/measure_tokens.py`):

| Command | Before (tokens) | After (tokens) | Saved |
|---|---:|---:|---:|
| quiz: find due questions | 8,018 | 390 | 96% |
| start check | 660 | 146 | 78% |
| restore: pending decisions + weak topics | 1,619 | 246 | 85% |
| correct: repeated mistakes | 23,489 | ≈1,020 | 96% |
| history of one concept | 21,808 | 375 | 99% |
| teach: what is known | 1,671 | 229 | 87% |

The "before" column grows with history; the "after" column doesn't.

## Store

```
<repo>/.wise-code/graph/
  nodes.jsonl     one JSON object per line, sorted by id
  edges.jsonl     {"from", "rel", "to"}, sorted
  .gitattributes  *.jsonl merge=union
  .gitignore      .lock, .commit, .*.tmp (process-local, never merged)
```

- JSONL is canonical. Sorted lines give line-level git diffs.
- IDs: `PREFIX-YYYYMMDD-xxxx` (4 random hex), unique without coordination, so
  two machines or two projects never collide. Concepts use a lowercase slug
  (`rust-strings`) with `aliases`. Shelf books and sections use stable slugs
  (`BK-ddia`, `SEC-ddia-1.2`), so every project means the same section.
- Merges: git's built-in `union` driver keeps both sides' lines, so concurrent
  additions never conflict. A merge never drops an edit silently. Every change
  through `wise.py` stamps the node (`updated`, `rev`) and lists the version it
  was edited from in `seen` (content hashes, the last 16). When a merge leaves
  several lines for one node, the loader drops identical copies and every line
  another line lists in `seen` (it was edited from it, so it adds nothing); the
  next write removes them. If more than one line remains, the sides edited the
  node independently, whatever their stamps say: a higher `rev` or a later date
  doesn't show that side saw the other's change. Both stay on disk, every
  command warns, changes to that node are refused, and `wise.py resolve <id>`
  shows how they differ; `--keep <n>` keeps one, recording every version in its
  `seen` (with what they include) so a later merge that brings one back settles
  silently. Two exceptions combine versions without asking, when they differ
  only in these fields and in metadata (`SOONER` and `GROW_ONLY` in
  `scripts/wise.py`):
  - A question's `box` and `due`: answering on two clones keeps both answers
    (QA records) and reschedules on each side. The merge keeps the lower box
    and the earlier due date, each on its own, so the question comes back
    sooner, never later. A missing value is the lowest (box 1, due now).
  - A book's `projects`: it only grows (each project that cites the book adds
    itself), so the lists are united. To keep that lossless, any change that
    would drop an item is refused, and `resolve` keeps every version's
    projects whichever version is kept.

  Any other difference still waits for `resolve`. Malformed versions are never
  combined: they stay a conflict and `check` reports them. Lines with no
  `seen` (written before it existed, or edited by hand) can't be shown to
  include another, so they too wait for `resolve`, unless they differ only as in
  the two exceptions. Leftover conflict markers are ignored.
- Writes go only through the script: it assigns IDs, validates fields and
  edges (stored JSON types, not just CLI text), and refuses near-duplicate
  concepts. `--force` overrides similarity, never an existing concept id.
- One writer at a time: every command holds an exclusive lock on `graph/.lock`
  from load to exit, so a save always writes the snapshot it loaded. A second
  command waits (up to 20 s, then fails with "busy"). When the graph doesn't
  exist yet, the first save creates it and a stale second save is refused.
- Saves commit as one unit: both new files are written and synced, then the
  journal `graph/.commit` is published, then the files are renamed into place.
  Interrupted before the journal: the old graph stays, its temps are deleted.
  After it: the next command finishes the renames. Readers never see a mix.
  Process crashes are covered; files and the folder are fsynced, but power-loss
  durability still depends on the file system honoring fsync.
- Symlinks: the state folder, `graph/` and every file in it are refused.
- If Python 3.9+ is missing or the command is blocked, Claude stops learning
  writes and guides the fix. There is no Markdown fallback.

## Three tiers

1. **The graph is the store**: Concept, QA, Question, Card, Session, Decision,
   Guardrail, Reflection, Feedback, LearningRecord.
2. **A file is the store; the graph indexes it** (node = path, title, edges to
   concepts): Lesson, Reference, Research, ADR, Mission, Resource. A repo
   `GLOSSARY.md` stays a file too; concepts point to it with `glossary`.
3. **Outside the graph**: `profile.md`, `project-map.md` (yours, read whole),
   `shelf.md`, `backups/`.

Readable views of tier 1 come from `wise.py render`; `cards.tsv` is an export.

## Learner's words

Records that say what the learner decided or reasoned carry `said`: a verbatim
span (3 to 40 words per part, parts joined with ` … `) of the learner's own
message. Without it, a note Claude wrote ("outcome", a QA gist) gets read back
after a restart as if the learner had said it, and each restart paraphrases the
last paraphrase. Research solved the same problem for web pages with verbatim
spans; this applies it to the learner.

- Required on write (`add`, `set`, `answer`) for a settled decision `by=learner`
  or `both`, and for QA from `checkpoint`, `explore`, `reflect` and `repair`.
  Graphs written before the rule still pass `check`.
- `said_check` (`unchecked`, `ok`, `missing`, `unverified`) is set only by
  `wise.py check-said`, which matches each part against the typed user messages
  in this project's Claude Code transcripts. It skips compaction summaries,
  tool results, sub-agent threads, injected reminders and client text
  nobody typed (`textNotTyped`), and stores nothing
  from the transcripts. Reflections are checked on their `text`.
- Matching is whole-word: `safe to use` does not match `unsafe to use`.
- A check is bound to the words it checked (`said_hash`). If the quote later
  changes by any path (`set`, `edit`, a hand edit, a union merge), it reads as
  `unchecked` and the next `check-said` checks it again. `edit` refuses changes
  to `said_check` and `said_hash`, and applies the same quote rules as `set`.
- `decisions` and `history --full` print quotes as `learner said «…» · check …`
  and label `proposal` and `outcome` as AI notes, so the restore reads the
  difference instead of guessing it.

## Edges

| Relation | From | To |
|---|---|---|
| `about` | QA, decision, record, citation, explain-back, feedback, reflection | concept |
| `in` | QA, decision, reflection, feedback, question, card, record | session |
| `answers` | QA | question |
| `tests` | question, card | concept |
| `prereq` | concept | concept (proposed by Claude, confirmed by the learner) |
| `covers` | lesson, reference, research, ADR, mission, resource, record, section | concept |
| `supersedes` | record | record |
| `from` | question, card | QA, record, lesson, citation, section |
| `evidence` | guardrail | QA |
| `repairs` | QA (the repair answer) | QA (the confusion it targets) |
| `of`, `on`, `for` | section → book; citation, read, explain-back → section; read, explain-back → citation |

## Confidence and repair

QA carries `confidence` (`low`, `mid`, `high`) only as the learner stated it, by
prefixing the answer. Confusions and repairs are derived on read, never stored:

- **Confusion**: `wrong` at any confidence, or `partial` at `high`.
- **Repaired**: a later `correct` answer that `repairs` this confusion, is
  `about` the same concept, and asks a different question (by `answers` edge and
  normalized question text). A correct answer that only shares the concept does
  not count: it may test another idea. One repair answer may link several
  confusions when it tests the idea they share. `repairs` must point at a
  confusion, or the link is refused.
- **Gate** (`wise.py confusions --concept X --with-prereqs`): `clear`, `repair
  first`, or `blocked` once `SKIP_CAPACITY` (2) skipped confusions are open.
  `skip-repair` stamps `skipped` on the QA and is refused at capacity.
- `calibration`: accuracy per confidence level and the high-confidence misses.

QA also gets an `at` timestamp so records within one day are ordered.

## Lesson results

Lessons are static HTML, so a quiz inside one can't write to the repo. The
lesson's **Download results** button (`skills/teach/templates/results.js`) saves
`{lesson, result_id, date, answers: [{id, q, answer, correct, expected}]}`. Put the
file in `.wise-code/inbox/` (imported at the next session start) or run
`wise.py import-lesson <file>`. Imported inbox files move to `inbox/done/` under
a free name (`r-2.json`), never over an earlier one; a symlinked `inbox/`,
`done/` or `backups/` is refused before the graph changes. Each answer becomes a `lesson` QA, wrong answers
enter the question bank. A page load is one attempt with one `result_id`, and
each answer in it is recorded once however many times it is downloaded; a
reload is a new attempt. The whole
file is checked before anything is recorded: `correct` must be a JSON boolean
and `id`, `q`, `answer`, `expected` strings, so a malformed file is rejected with the
number of the bad answer and the graph stays unchanged.

## Shelf graph

The shelf repo has its own graph at `<shelf>/.wise-code/graph/`: Book, Section,
Citation, Read, ExplainBack (plus Question, Card and QA for book quizzes). Every
shelf record carries `project` from the project's `shelf.md`; a Book lists the
projects that cite it. `wise.py --root <shelf> impact` shows use across projects.
Project concepts point to shelf sections by id strings in `shelf`;
`wise.py check --shelf <folder>` warns about ids the shelf no longer has.

## Reset

`/wise-code:reset` backs up the graph, then clears each concept's `status` and
every `pending` decision. Everything else stays.

## Code

WiseCode never builds a code graph. Code lookups use an installed code-graph MCP
server when the session has one, otherwise Read and Grep. With one, Explore and
Code review compare it with `project-map.md` and turn mismatches into questions.
Concepts keep plain `file:symbol` strings in `code`; `check` warns when a file
is gone.
