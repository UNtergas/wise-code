---
name: critique
description: Review technical writing the learner wrote (ADR, README, TIL, doc, PR description, commit message) against a writing rubric. Feedback only, at the learner's assist level; the learner rewrites.
argument-hint: "<file path, or paste the text>"
disable-model-invocation: true
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

# WiseCode Critique

Target: `$ARGUMENTS`

Critique gives feedback on writing the learner wrote. It never rewrites the
document: the learner does, because rewriting is where the writing skill grows.
The rubric is [writing-rubric.md](writing-rubric.md); read it first.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

## 1. Get the text

- A file path: read the file. Don't edit it.
- Pasted text: use it as given.
- Nothing given: ask which file or text to review.

If the text was written by an AI, say Critique is for the learner's own writing
and ask whether to continue anyway.

Locate the state directory as the [Learn guide](../learn/SKILL.md) describes. If a
profile exists, read the assist level, including an override for `writing`. With
no profile, use Hint. Don't create state.

## 2. Ask for intent

Ask in one message: who is the reader, and what should they know or do after
reading? Skip this if the document type already makes it obvious (a commit
message, an ADR with a filled Context section).

## 3. Review

Check the mode first (rubric section M), then sentences, clarity, tells, and
language. Report at most five findings, most important first, each with:

- the location (heading or line) and a short quote
- the rule ID and name
- what the problem does to the reader

Then apply the assist level:

| Level | Per finding you add |
|---|---|
| Hint | Nothing more. The learner finds the fix. |
| Pseudo | The shape of the fix ("split into claim, then condition"), no rewritten sentence |
| Full code | One rewritten example for the first finding only; the learner does the rest |

Grammar and spelling (G1, G2) are always named with the rule ("past participle
agrees with a preceding direct object"), so the learner learns the rule, not the
patch.

Say what already works only when it is specific ("the Decision section is one
sentence and names the trade-off").

## 4. Second pass

When the learner sends a revision, review only the changed parts and the open
findings. Say which findings are resolved. Stop after the open findings are
resolved, or after the learner says it's good enough.

## 5. Record

If the state directory exists, follow [materials.md](../learn/materials.md): log a
`critique` qa-history entry for a writing issue that already appeared in an earlier
`critique` entry, or a grammar rule the learner got wrong. Repeated ones are input
for `/wise-code:correct`.
