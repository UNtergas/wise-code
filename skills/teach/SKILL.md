---
name: teach
description: Teach the user a new skill or concept over multiple sessions, using this project's .wise-code/teach/ as a stateful teaching workspace.
disable-model-invocation: true
argument-hint: "What would you like to learn about?"
---

## Canary

Every chat reply you send while this skill is active starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them):

```text
=====> ah0y_sir <name>
```

```text
<===== f1n
```

`<name>` is the name the user gave in this conversation. At the first reply of a new conversation, if no name has been given yet, start with `=====> ah0y_sir`, ask "What's your name?" before anything else, and wait; use the name from then on. Ask again in each new conversation; never store it in files or notes.

Missing end line → the reply was cut off or the instructions were dropped; the learner should treat it as incomplete. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

User wants to learn a topic over multiple sessions. Teaching workspace = `teach/` inside this project's WiseCode state dir. Every project has its own workspace: start `/wise-code:teach` in repo A → lessons, mission, records live in repo A only.

If running in Codex rather than Claude Code, first read [codex.md](codex.md).

## Locate workspace

Same lookup as Learn ([../learn/SKILL.md](../learn/SKILL.md), "Locate state"):

- From cwd, look upward for `.wise-code/`, stop at nearest `.git` dir or file (incl. worktree root). Never cross that boundary.
- No Git → check cwd only; don't search parents.
- None found → create `.wise-code/` at Git root (cwd without Git). Learn onboarding not required to teach.
- Never follow symlinked state dirs/files; explain issue instead.
- Workspace = `<state>/teach/`. All paths below resolve from there. Create dirs lazily.
- Never write lessons/records to plugin folder, home dir, parent repo, other worktree, or other project. Never read another project's workspace.

## Workspace

| Where | Purpose |
|---|---|
| `MISSION.md` | _Why_ user is learning. Grounds every decision. File; indexed as `mission`. |
| `RESOURCES.md` | Curated trusted sources (knowledge + communities). File; each entry indexed as `resource`. |
| Glossary (graph) | Canonical terminology: concept `definition`, `aliases`, `avoid`. All lessons/records adhere. Read with `wise.py render glossary`. |
| `NOTES.md` | Scratchpad: user teaching preferences, working notes. File. |
| `./lessons/NNNN-slug.html` | Primary teaching unit. One tight topic each. File; indexed as `lesson`. |
| `./reference/*.html` | Compressed essence of lessons: cheat sheets, syntax, algorithms, poses. Print well. File; indexed as `reference`. |
| Learning records (graph) | ADR-like records of what user has learned (type `record`). Drive ZPD. Read with `wise.py list record`. |
| `./assets/*` | Reusable components (stylesheet, results script, quiz widgets, simulators, diagram helpers). |

Numbering (lessons): scan dir for highest number, +1.

The learning graph sits one level up in `<state>/graph/`, shared w/ Learn and Quiz, read and written only through `wise.py` (commands, the "Script blocked" fix, and every format: [../learn/materials.md](../learn/materials.md)). Every new lesson, reference, mission or resource gets indexed right after it is written: `wise.py add lesson path=.wise-code/teach/lessons/0007-slug.html title="…" --covers <concept>` (same for `reference`, `mission`; `resource` takes `title=`, `url=`, `kind=knowledge|community`, `path=.wise-code/teach/RESOURCES.md`). `wise.py index` catches any missed.

## Session flow

1. Read `MISSION.md`, `NOTES.md`, `assets/`; query `wise.py render glossary`, `wise.py list record --limit 20`, `wise.py weak`. If `<state>/profile.md` exists, read it (read-only) — concepts demonstrated in the graph (`wise.py list concept --where status=demonstrated`) count when judging ZPD. Don't edit Learn's files. Lesson results waiting in `<state>/inbox/` → `wise.py import-lesson --inbox` first.
2. No/vague mission → interview user on _why_ before anything else.
3. `RESOURCES.md` thin → find high-trust resources first. Never trust parametric knowledge. Hand the search to one background agent (Agent tool, `model: sonnet`) briefed with the mission and the source rules of [../research/SKILL.md](../research/SKILL.md); vet its candidates yourself before they enter `RESOURCES.md`.
4. Pick next lesson: user's explicit req, else most mission-relevant thing in zone of proximal development (ZPD — challenged "just enough"), judged from learning records.
5. Build lesson from existing assets; add new reusable components to `./assets/`.
6. Create/update reference docs alongside.
7. Open lesson via CLI if possible.
8. After evidence of learning: write learning records (`wise.py add record …`), promote glossary terms (concept `definition`).
9. Before ending: update shared materials per [../learn/materials.md](../learn/materials.md) — `lesson` QA for exercises answered in chat + learner questions worth keeping (`asked`); up to 3 questions per new learning record (`wise.py add question … --tests <concept> --from <record id>`); atomic facts as cards. One line telling user what was added. Suggest `/wise-code:quiz` when questions are due.

## Philosophy

Deep learning needs three things:
- **Knowledge** — from high-trust resources. Difficulty is the enemy here: it eats working memory.
- **Skills** — via interactive lessons w/ feedback loops. Difficulty is the tool: effortful retrieval builds retention.
- **Wisdom** — from real-world practice w/ other learners/practitioners.

Balance varies by topic (theoretical physics → knowledge-heavy; yoga → skills-heavy).

**Fluency vs storage strength.** Fluency (in-the-moment recall) gives illusory mastery. Target storage strength (long-term retention) via desirable difficulty:
- Retrieval practice (recall from memory)
- Spacing (distribute practice over time)
- Interleaving (mix related topics — skills practice only)

Question bank + Quiz = spacing + retrieval across sessions. Lessons teach; Quiz makes it stick.

## Lessons

Single self-contained HTML file in `./lessons/`.

- **Beautiful** — clean typography, Tufte-like. User returns to review.
- **Short** — completable fast; fits small working memory. One tangible win to build on.
- **Tied to mission**, inside ZPD.
- Teach only knowledge required for the skill, then practice skill via interactive feedback loop.
- Littered w/ citations to external resources backing every claim.
- Recommends one primary source (best high-trust resource found) to read/watch.
- Links via anchors to other lessons and reference docs.
- Reminds user to ask agent follow-up questions — agent is their teacher.

**Feedback loops**: as tight as possible — immediate, ideally automatic. Formats: in-browser quizzes/light tasks, or guided real-world step lists (e.g. yoga poses).

**Quizzes**: every answer option same word count (and char count if possible). Vary correct-answer position. No clues via formatting or order.

**Evidence**: in-browser quiz results reach the agent only as a file. Every lesson with a quiz loads `../assets/results.js` (copied from [templates/results.js](templates/results.js); edit the copy, never the plugin template), names itself (`WiseResults.lesson("0007-slug")`), records each first answer (`WiseResults.record(id, question, answer, correct, expected)`) and has a `<div id="wise-results"></div>`, where a **Download results** button appears. The learner saves the `.json` into `<state>/inbox/` (imported at the next session start) or tells you where it is: `wise.py import-lesson <path>`. Each answer becomes a `lesson` QA; wrong ones enter the question bank; a result is never imported twice. No file → ask how it went, or re-ask key questions in chat, before writing learning records or verdicts.

## Assets

Reuse is default. Before authoring a lesson, read `./assets/` and build from what's there. Anything a second lesson could reuse → component in `./assets/`, linked, never inlined. First component every workspace earns: shared stylesheet linked by all lessons, so they read as one course. Start it by copying [templates/lesson.css](templates/lesson.css) into `./assets/lesson.css`, and [templates/results.js](templates/results.js) into `./assets/results.js`; edit the copies, never the plugin templates. Library grows w/ workspace.

## Reference docs

Lessons rarely revisited; reference docs are. Compressed essence, built for quick lookup: syntax/snippets, algorithms/flowcharts, poses/sequences, exercises/routines, glossaries.

## Wisdom & communities

Wisdom-type question → attempt answer, but ultimately delegate to a **community** (forum, subreddit, class if budget allows, local group). Find high-reputation ones. If user declines communities, respect it and note in `RESOURCES.md`.

---

## `MISSION.md` format

```md
# Mission: {Topic}

## Why
{1-3 sentences. Concrete real-world outcome — what changes in their life/work. Not "to understand X".}

## Success looks like
- {Specific, observable capability}

## Constraints
- {Time, budget, commitments, learning preferences}

## Out of scope
- {Adjacent topics explicitly not chased now — protects ZPD}
```

Rules:
- One mission per project workspace. Unrelated topic → run `/wise-code:teach` in another project folder (any non-Git folder works as its own space).
- Concrete over abstract ("Ship a Rust CLI to my team" > "learn Rust").
- Push back on vagueness; interview first. Bad mission worse than none.
- Missions shift. Confirm w/ user, update file, write learning record. No stale missions.
- Max one screen. Longer = plan, not compass.

## `RESOURCES.md` format

```md
# {Topic} Resources

## Knowledge
- [Book: _Title_ by Author](url)
  What it covers. Use for: {when to reach for it}.

## Wisdom (Communities)
- [r/example](url)
  Why trustworthy. Use for: {when}.
- Local: {class/group}
  Use for: {when}.

## Gaps
- {Mission area w/ no good resource yet — drives future search}
```

Rules:
- High-trust only: primary sources, recognised experts, peer-reviewed work, well-moderated communities. No marketing-as-education.
- Annotate every entry (what + when). Bare links useless later.
- Prune ruthlessly: wrong/shallow/off-mission → remove. Five sharp > thirty mediocre.
- Record community opt-out here.

## Glossary (in the graph)

A term is a concept with a `definition`; the learner reads the whole glossary with `wise.py render glossary`.

```sh
wise.py add concept name="Progressive overload" \
  definition="Systematically increasing demand on a muscle over time, via load, volume, or intensity." \
  avoid+="Pushing harder" avoid+="levelling up"
wise.py set progressive-overload definition="…"     # revise in place
```

Rules:
- Add term only once user can use it correctly. Record of compressed knowledge, not a dictionary to learn from.
- Opinionated: pick best word, list alternatives in `avoid`. An existing concept close to the term → `add` refuses and shows it; set its `definition` instead.
- Definitions 1-2 sentences: what term IS, not what it does.
- Use glossary terms inside other definitions.
- Flag ambiguities in the definition: "In this workspace, 'set' always means a working set."
- Revise in place as understanding deepens. Once created, every lesson adheres.

## Learning record format

```sh
wise.py add record title="<Short title of what was learned/established>" \
  body="<1-3 sentences: what is now known and why it changes what to teach next.>" \
  --about <concept>
```

That's the whole format. Optional only when valuable:
- `evidence=`: how user demonstrated it (answer, exercise, cited experience)
- `implications=`: what it unlocks/rules out, if non-obvious

Write one when:
1. User showed genuine understanding of something non-trivial (evidence, not exposure) — sets new floor.
2. User disclosed prior knowledge — record it and claimed depth, so it's not re-taught.
3. Misconception corrected — high value, predicts related stumbles.
4. Mission shifted — update `MISSION.md` and write a record about the shift.

Don't write for: material merely covered (coverage ≠ learning), anything already a glossary definition, session activity logs (records are decision-grade insights, not a journal — Q/A goes to QA).

Supersession: contradicted record → `wise.py link <new> supersedes <old>` and `wise.py set <old> status=superseded`, never delete. Evolution of understanding is signal.
