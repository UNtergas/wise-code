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
2. Find `questions.md` with Glob. If it is missing or has no questions, say there
   is nothing to quiz yet. Offer to propose questions from `progress.md` and
   `teach/learning-records/`; add them only after the learner agrees, then stop.
3. Parse the arguments, ignoring case: an optional topic filter and an optional
   count (default 5, at most 10). Pick questions that are due today or earlier,
   oldest due date first, matching the topic if one was given. When several topics
   are due, interleave them. If nothing is due, say when the next question is due
   and offer an early round; early answers are scheduled from today.
4. Ask one question at a time, in chat, and wait for the answer. Don't show the
   reference answer, options, or hints first. Give a hint only when asked; a hinted
   answer is at best `partial`. If the learner says "skip", leave that question's
   schedule unchanged.
5. After each answer, give a verdict (`correct`, `partial`, `wrong`) and one to
   three lines of feedback grounded in the reference answer and this project's
   code. Equivalent reasoning in the learner's own words is correct; don't demand
   the reference wording. If the reference answer turns out to be wrong, say so,
   fix it in `questions.md`, and don't count the answer against the learner.
6. Update that question's `Box:` and `Due:` per the Leitner rules, and append a
   qa-history entry with source `quiz`. Write after each answer, not at the end,
   so an interrupted quiz keeps its progress.
7. If a `wrong` answer reveals a gap in a topic that `progress.md` tracks, add or
   consolidate a Needs reinforcement bullet under that topic. Don't create topics
   or touch pending decisions.
8. End with one line: score, which topics were weak, and the next due date. Offer
   to add atomic cards to `cards.tsv` for facts the learner missed.

Ask in the language the learner uses in this conversation. Quiz questions stay
open-ended unless the learner asks for options.
