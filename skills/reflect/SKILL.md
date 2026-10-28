---
name: reflect
description: End-of-session reflection. The learner writes what they learned, what was hard and what they'd change; Claude checks it against the session's evidence, then collects proposed fixes to WiseCode's own behavior.
disable-model-invocation: true
---

## Canary

Once this skill has loaded in a conversation, every chat reply you send from then on, until the conversation ends, starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them). It stays on after this skill finishes, through other skills and ordinary tasks; never drop it because the work changed.

```text
=====> ah0y_sir <name>
```

```text
<===== f1n
```

`<name>` is the name the user gave in this conversation. At the first reply of a new conversation, if no name has been given yet, start with `=====> ah0y_sir`, ask "What's your name?" before anything else, and wait; use the name from then on. Ask again in each new conversation; never store it in files or notes.

Missing start or end line → the reply was cut off or the instructions were dropped (for example after a long context or a compaction); the learner should treat it as a sign that quality may be slipping. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

# WiseCode Reflect

Reflection turns a session into memory. The learner writes it; you check it
against evidence and point at gaps. Afterwards, you look at how WiseCode itself
behaved and propose fixes to the plugin. Adapted from pstack's `reflect` skill by
Lauren Tan (MIT).

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

## 1. Locate state

Locate the state directory as the [Learn guide](../learn/SKILL.md) describes. If
there is none, say there is nothing to reflect against and suggest
`/wise-code:learn`; don't create state. Read the Reflections, Feedback and Sessions
sections of [materials.md](../learn/materials.md).

## 2. The learner writes first

Ask these three, together, and wait:

1. What did you learn this session, in your own words?
2. What was hard or confusing?
3. What would you do differently next time?

Don't offer a summary, examples, or a list of topics first. A short answer is
fine; don't push for more.

## 3. Check against the evidence

Evidence: this conversation, this session's QA (`wise.py history --since <date>
--full`), confidence vs results (`wise.py calibration --since <date>`), open
confusions (`wise.py confusions`), concept changes (`wise.py weak`, `wise.py concept <slug>`), Code review
findings, and the Git diff since the session started.
If the conversation was compacted and the learner agrees, you may read this
session's transcript; read only this project's transcript folder.

Reply in three short parts:

- **Supported**: claims the evidence backs, with the entry or commit.
- **Not yet shown**: things the learner says they learned that no answer or code
  demonstrates yet. Propose one question per item for the question bank.
- **Missed**: something the evidence shows they did or learned that they didn't
  mention. One or two items at most.

Correct a misconception in the reflection directly, citing the evidence. Don't
praise or grade. Add a `reflect` QA only for a corrected misconception or a "Not
yet shown" item.

Store the reflection: `wise.py add reflection text="<the learner's text, unchanged>"
evidence_check="<one to three lines>"`. If the project keeps its own TIL or journal file,
offer to copy the learner's words there; don't rewrite them.

## 4. WiseCode feedback

Review the session for places where WiseCode's instructions didn't work: code or
signatures given at Hint, a skipped or repeated checkpoint, the wrong assist level,
too many questions, a hint that gave the answer away, noisy materials. Also ask the
learner: "Did WiseCode get in the way anywhere?"

For each real finding (a one-off slip that the rules already cover is not a
finding), add plugin feedback: `wise.py add feedback what=… guide=… rule=…
proposed_edit="<old text> → <new text>"` (the project's plugin feedback). Never
edit the installed
plugin; the learner applies accepted edits in their WiseCode repository. Show the
entries and say how many were added. If there were none, say so.

## 5. Session recap

Last, write the session recap as "Session end" in the
[Learn guide](../learn/SKILL.md) describes: `wise.py add session …` (it starts as
`Start check: pending`), and show it in chat. Do it
after the learner's reflection and your evidence check, never before: the recap
would hand them the answers to step 2. The next new session opens with a start
check built from its `Check points:`.
