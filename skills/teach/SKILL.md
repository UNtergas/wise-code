---
name: teach
description: Teach the user a new skill or concept over multiple sessions, using this project's .wise-code/teach/ as a stateful teaching workspace.
disable-model-invocation: true
argument-hint: "What would you like to learn about?"
---

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

| Path | Purpose |
|---|---|
| `MISSION.md` | _Why_ user is learning. Grounds every decision. |
| `RESOURCES.md` | Curated trusted sources (knowledge + communities). |
| `GLOSSARY.md` | Canonical terminology. All lessons/records adhere. |
| `NOTES.md` | Scratchpad: user teaching preferences, working notes. |
| `./lessons/NNNN-slug.html` | Primary teaching unit. One tight topic each. |
| `./reference/*.html` | Compressed essence of lessons: cheat sheets, syntax, algorithms, poses. Print well. |
| `./learning-records/NNNN-slug.md` | ADR-like records of what user has learned. Drive ZPD. |
| `./assets/*` | Reusable components (stylesheet, quiz widgets, simulators, diagram helpers). |

Numbering: scan dir for highest number, +1.

Shared learning materials (`qa-history.md`, `questions.md`, `cards.tsv`) sit one level up in `<state>/`, shared w/ Learn and Quiz. Formats: [../learn/materials.md](../learn/materials.md).

## Session flow

1. Read `MISSION.md`, `NOTES.md`, `GLOSSARY.md`, `learning-records/`, `assets/`. If `<state>/profile.md` or `<state>/progress.md` exist, read them (read-only) — concepts already demonstrated there count when judging ZPD. Don't edit Learn's files.
2. No/vague mission → interview user on _why_ before anything else.
3. `RESOURCES.md` thin → find high-trust resources first. Never trust parametric knowledge. Hand the search to one background agent (Agent tool, `model: sonnet`) briefed with the mission and the source rules of [../research/SKILL.md](../research/SKILL.md); vet its candidates yourself before they enter `RESOURCES.md`.
4. Pick next lesson: user's explicit req, else most mission-relevant thing in zone of proximal development (ZPD — challenged "just enough"), judged from learning records.
5. Build lesson from existing assets; add new reusable components to `./assets/`.
6. Create/update reference docs alongside.
7. Open lesson via CLI if possible.
8. After evidence of learning: write learning records, promote glossary terms.
9. Before ending: update shared materials per [../learn/materials.md](../learn/materials.md) — qa-history entries for exercises answered in chat + learner questions worth keeping; up to 3 questions per new learning record into `questions.md`; atomic facts into `cards.tsv`. One line telling user what was added. Suggest `/wise-code:quiz` when questions are due.

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

**Evidence**: in-browser quiz results never reach agent. Ask user how it went, or re-ask key questions in chat, before writing learning records or verdicts.

## Assets

Reuse is default. Before authoring a lesson, read `./assets/` and build from what's there. Anything a second lesson could reuse → component in `./assets/`, linked, never inlined. First component every workspace earns: shared stylesheet linked by all lessons, so they read as one course. Start it by copying [templates/lesson.css](templates/lesson.css) into `./assets/lesson.css`; edit the copy, never the plugin template. Library grows w/ workspace.

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

## `GLOSSARY.md` format

```md
# {Topic} Glossary

{1-2 sentence topic description.}

## Terms

**Progressive overload**:
Systematically increasing demand on a muscle over time, via load, volume, or intensity.
_Avoid_: Pushing harder, levelling up
```

Rules:
- Add term only once user can use it correctly. Record of compressed knowledge, not a dictionary to learn from.
- Opinionated: pick best word, list alternatives under `_Avoid_`.
- Definitions 1-2 sentences: what term IS, not what it does.
- Use glossary terms inside other definitions.
- Group under subheadings when clusters emerge.
- Flag ambiguities: "In this workspace, 'set' always means a working set."
- Revise in place as understanding deepens. Once created, every lesson adheres.

## Learning record format

```md
# {Short title of what was learned/established}

{1-3 sentences: what is now known and why it changes what to teach next.}
```

That's the whole format. Optional only when valuable:
- **Status** frontmatter: `active | superseded by LR-NNNN`
- **Evidence**: how user demonstrated it (answer, exercise, cited experience)
- **Implications**: what it unlocks/rules out, if non-obvious

Write one when:
1. User showed genuine understanding of something non-trivial (evidence, not exposure) — sets new floor.
2. User disclosed prior knowledge — record it and claimed depth, so it's not re-taught.
3. Misconception corrected — high value, predicts related stumbles.
4. Mission shifted — link `MISSION.md` and update it.

Don't write for: material merely covered (coverage ≠ learning), anything already in `GLOSSARY.md`, session activity logs (records are decision-grade insights, not a journal — Q/A goes to `qa-history.md`).

Supersession: contradicted record → mark `Status: superseded by LR-NNNN`, never delete. Evolution of understanding is signal.
