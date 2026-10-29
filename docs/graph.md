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
```

- JSONL is canonical. Sorted lines give line-level git diffs.
- IDs: `PREFIX-YYYYMMDD-xxxx` (4 random hex), unique without coordination, so
  two machines or two projects never collide. Concepts use a lowercase slug
  (`rust-strings`) with `aliases`. Shelf books and sections use stable slugs
  (`BK-ddia`, `SEC-ddia-1.2`), so every project means the same section.
- Merges: git's built-in `union` driver keeps both sides' lines, so concurrent
  additions never conflict. Every change stamps the node (`updated`, `rev`); when
  both sides changed the same node, the loader keeps the newer one and the next
  write drops the other line. Leftover conflict markers are ignored.
- Writes go only through the script: it assigns IDs, validates fields and
  edges, refuses near-duplicate concepts, and rewrites the files atomically.
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
`{lesson, result_id, date, answers: [{q, answer, correct, expected}]}`. Put the
file in `.wise-code/inbox/` (imported at the next session start) or run
`wise.py import-lesson <file>`. Each answer becomes a `lesson` QA, wrong answers
enter the question bank, and a `result_id` is never imported twice.

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
