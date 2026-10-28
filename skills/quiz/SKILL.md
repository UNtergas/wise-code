---
name: quiz
description: Run a short spaced-retrieval quiz from this project's question bank, log each answer to the Q/A history, and reschedule the questions.
argument-hint: "[topic] [number of questions]"
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

# WiseCode Quiz

Arguments: `$ARGUMENTS`

Retrieval practice for this project. Formats and scheduling rules are in
[materials.md](../learn/materials.md); read it first. This command never edits
the learner's source files.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

1. Locate the state directory the same way as [the Learn guide](../learn/SKILL.md)
   (nearest `.wise-code/` up to the Git root, no symlinks; without Git, the
   current directory only). If there is none, say so and suggest
   `/wise-code:learn` or `/wise-code:teach`; don't create state here.
2. Parse the arguments, ignoring case: an optional topic filter and an optional
   count (default 5, at most 10). Run `wise.py due --limit <count> [--topic <topic>]`:
   due questions, oldest first, topics interleaved. Read the ones you ask with
   `wise.py show <id>` (its reference answer). Never read the graph files.
   "no questions yet" → say there is nothing to quiz yet. Offer to propose
   questions from `wise.py weak` and `wise.py list record`; add them only after the
   learner agrees, then stop. "nothing due" → say when the next one is due and
   offer an early round (`--early`); early answers are scheduled from today.
   Script refused → "Script blocked" in materials.md.
3. Ask one question at a time, in chat, and wait for the answer. End it with the
   reminder "Prefix your answer with your confidence: `high:`, `mid:` or `low:`."
   Don't show the reference answer, options, or hints first. Give a hint only when asked; a hinted
   answer is at best `partial`. If the learner says "skip", leave that question's
   schedule unchanged.
4. After each answer, give a verdict (`correct`, `partial`, `wrong`) and one to
   three lines of feedback grounded in the reference answer and this project's
   code. Equivalent reasoning in the learner's own words is correct; don't demand
   the reference wording. If the reference answer turns out to be wrong, say so,
   fix it (`wise.py set <id> a="…"`), and don't count the answer against the learner.
5. Record it: `wise.py answer <id> <verdict> --answer "<gist>" [--confidence <as
   prefixed>] [--hints N]`. When it prints `confusion:`, say so in one line: the
   next build step on that concept starts with a repair. That
   logs a `quiz` QA and reschedules the question by the Leitner rules. Run it after
   each answer, not at the end, so an interrupted quiz keeps its progress.
6. If a `wrong` answer reveals a gap in a concept the graph tracks, mark it
   (`wise.py set <concept> status=reinforce notes+="…"`). Don't create concepts
   or touch pending decisions.
7. End with one line: score, which topics were weak, any high-confidence misses,
   and the next due date. Offer
   to add atomic cards (`wise.py add card … --tests <concept>`) for facts the
   learner missed.

Ask in the language the learner uses in this conversation. Quiz questions stay
open-ended unless the learner asks for options.
