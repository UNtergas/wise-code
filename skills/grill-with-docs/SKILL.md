---
name: grill-with-docs
description: Interview the user about a plan or design inside a repo until both share one understanding, writing vocabulary to GLOSSARY.md and hard decisions to docs/adr/ as they resolve. Use at the start of a change that fits in ONE session when the plan is fuzzy and the words for the thing aren't settled. User says "grill me", "grill with docs", "stress-test this plan", "help me document my repo". For multi-session efforts use wayfinder; for questions talking can't settle use prototype; for external facts use research.
disable-model-invocation: true
argument-hint: "What plan or change should I grill you on?"
---

## Canary

Every chat reply you send while this skill is active starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them):

```text
=====>
```

```text
<=====
```

Missing end line → the reply was cut off or the instructions were dropped; the learner should treat it as incomplete. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

Stateful interview. Same loop as a plain grill, pointed at a codebase, and it leaves files behind: terms → `GLOSSARY.md` the moment they resolve, hard decisions → ADRs. Self-contained: this file holds the interview rules and the writing rules, plus one section for WiseCode learning mode.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

## Is this the right skill?

| Have | Use |
|---|---|
| No repo / not in a working dir | plain grill (`/wise-code:grill`; interview only, write no files) |
| Repo + change settleable in one session | **this** |
| Effort too big for one session | wayfinder, if installed |
| Repo with no domain docs, no feature in mind | **this**, aimed at the repo ("document my repo") |
| Question talking can't settle (how should it look/behave) | prototype, if installed |
| Blocked on a fact outside the repo | `/wise-code:research` |

Session count decides, not project size. Wayfinder on a well-scoped feature = slow and dense for nothing.

## Interview rules

1. **Explore before asking.** Anything the codebase can answer, answer by reading it. Never ask the user what a file already says. Bring findings into the question ("`Order` has `status` in 3 states; plan says 4. Which is it?").
2. **One topic per round, small batch.** Ask 1-3 tightly related questions, then **stop and wait**. Never dump the whole question list at once.
3. **Recommend an answer** with each question and say why. User can say "yes". Cuts decision fatigue and shows the reasoning chain. (In learning mode, see below.)
4. **Walk the decision tree.** Settle upstream decisions before downstream ones. State why a question matters if it isn't obvious (what it unblocks).
5. **Challenge words.** When user uses a term the glossary defines differently, or uses two words for one thing, or one word for two things, say so immediately and force a pick.
6. **Probe edge cases** with concrete scenarios, not abstractions ("A user deletes the last admin: what happens?").
7. **Keep questions short.** A three-paragraph question hides why it's asked.
8. **Never answer your own questions.** If user is silent, wait.
9. Stop when no open branch remains, or user says stop. Say what is still unresolved.

## Writing during the session

Write the moment something resolves, not in a batch at the end. Create files lazily; nothing exists until needed.

### Terms → `GLOSSARY.md`

Location: repo root. If a `GLOSSARY-MAP.md` at root marks a multi-context repo, write to the relevant context's `GLOSSARY.md`. If a `GLOSSARY.md` already exists, read it first and obey it.

```md
# {Project} Glossary

{1-2 sentence description of the domain.}

## Terms

**Order**:
A confirmed request by a customer for one or more items, created at checkout.
_Avoid_: Cart, purchase, transaction
```

Rules:
- Only the project's own words for things. **Pure vocabulary**: no implementation detail, no spec prose, no scratch notes.
- Definition = what the term IS, 1-2 sentences, using other glossary terms.
- Opinionated: pick the best word, list rejected synonyms under `_Avoid_`.
- Add a term only after the user agrees on it. Revise in place as understanding sharpens.
- Group under subheadings when clusters emerge. Flag ambiguity explicitly ("'Session' always means a login session here").

### Decisions → ADR in `docs/adr/`

Write an ADR only when **all three** hold:
1. **Hard to reverse**: cost of changing later is meaningful.
2. **Surprising without context**: a future reader would ask "why on earth?".
3. **Real trade-off**: genuine alternatives existed and one was chosen for reasons.

Most decisions fail a gate. Most sessions produce zero ADRs; that's correct. Number `NNNN-slug.md` (scan dir, highest + 1). If `docs/adr/` already has a template or an index (for example `0000-template.md`, `README.md`), follow the template and update the index.

```md
# {Short decision title}

Status: accepted | superseded by NNNN

## Context
{Forces at play, 2-4 sentences.}

## Decision
{What was chosen. Active voice.}

## Consequences
{What gets easier, what gets harder, what alternatives were rejected and why.}
```

Never edit an accepted ADR's decision; supersede it with a new one.

### Everything else

Not a glossary entry, not an ADR → stays in the conversation. That is a real loss risk, so see the close.

## Learning mode

Check for this project's WiseCode state as the [Learn guide](../learn/SKILL.md)
describes. If `profile.md` exists and says `Learning mode: active`, the interview
is also a learning checkpoint, and the learner does the thinking and the writing:

1. **Learner answers first.** Ask without your recommendation. After the answer,
   give your recommendation only where it differs, with the reason, and let them
   keep or change theirs. "recommend" gets it up front for that question.
2. **Glossary wording is theirs.** Ask the learner to define the term in one or
   two sentences, then tighten it with them. Write the agreed wording; don't
   substitute your own.
3. **ADRs are theirs.** When a decision passes all three gates, say so and name
   the gates it passes. The learner writes the ADR; offer `/wise-code:critique`
   on the draft. Write it yourself only when they ask.
4. **Record it.** Settled decisions go into `project-map.md` as chosen. Reasoning
   that shows real understanding, or a real gap, gets a `checkpoint` entry in
   `qa-history.md` per [materials.md](../learn/materials.md).

With no profile, or `Learning mode: paused`, follow the rules above as written.

## Close

The paper trail is thin by design. Before ending:
1. List every resolved decision in chat, **verbatim-precise** (ordering guarantees, negative requirements, numeric defaults, edge-case outcomes). Do not soften into prose.
2. List what is still unresolved.
3. Tell user which files changed (glossary terms added/revised, ADRs written) or that none qualified. In learning mode, also list the ADRs the learner still has to write.
4. Offer next step: write the decision list to a spec file in the repo's notes convention, or go straight to implementation if the change is small. **Keep the conversation**; don't clear it before the decisions are written down somewhere.

## It's working if

- `GLOSSARY.md` changes during the session, term by term.
- Glossary reads as vocabulary only.
- Questions the code could answer were answered by reading code.
- Zero or few ADRs, each one you'd be annoyed to re-argue.
- It pushed back on a word you used.

## Known failure modes

- Ran inside someone else's orchestration/wrapper and files silently weren't written → verify the working dir before trusting the output.
- Asked everything at once with no recommendations → interview rules weren't followed; restart from rule 2. (Learning mode withholds recommendations on purpose until the learner answers; that is not this failure.)
