---
name: reflect
description: End-of-session reflection. The learner writes what they learned, what was hard and what they'd change; Claude checks it against the session's evidence, then collects proposed fixes to WiseCode's own behavior.
disable-model-invocation: true
---

## Canary

Every chat reply you send while this skill is active starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them):

```text
--------> sir _h00t
```

```text
<---------------- fin3
```

Missing end line → the reply was cut off or the instructions were dropped; the learner should treat it as incomplete. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

# WiseCode Reflect

Reflection turns a session into memory. The learner writes it; you check it
against evidence and point at gaps. Afterwards, you look at how WiseCode itself
behaved and propose fixes to the plugin. Adapted from pstack's `reflect` skill by
Lauren Tan (MIT).

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

## 1. Locate state

Locate the state directory as the [Learn guide](../learn/SKILL.md) describes. If
there is none, say there is nothing to reflect against and suggest
`/wise-code:learn`; don't create state. Read the formats for `reflections.md` and
`plugin-feedback.md` in [materials.md](../learn/materials.md).

## 2. The learner writes first

Ask these three, together, and wait:

1. What did you learn this session, in your own words?
2. What was hard or confusing?
3. What would you do differently next time?

Don't offer a summary, examples, or a list of topics first. A short answer is
fine; don't push for more.

## 3. Check against the evidence

Evidence: this conversation, this session's qa-history entries, changes to
`progress.md`, Code review findings, and the Git diff since the session started.
If the conversation was compacted and the learner agrees, you may read this
session's transcript; read only this project's transcript folder.

Reply in three short parts:

- **Supported**: claims the evidence backs, with the entry or commit.
- **Not yet shown**: things the learner says they learned that no answer or code
  demonstrates yet. Propose one question per item for the question bank.
- **Missed**: something the evidence shows they did or learned that they didn't
  mention. One or two items at most.

Correct a misconception in the reflection directly, citing the evidence. Don't
praise or grade. Append a `reflect` qa-history entry only for a corrected
misconception or a "Not yet shown" item.

Store the reflection in `reflections.md`: the learner's text unchanged, plus a one
to three line evidence check. If the project keeps its own TIL or journal file,
offer to copy the learner's words there; don't rewrite them.

## 4. WiseCode feedback

Review the session for places where WiseCode's instructions didn't work: code or
signatures given at Hint, a skipped or repeated checkpoint, the wrong assist level,
too many questions, a hint that gave the answer away, noisy materials. Also ask the
learner: "Did WiseCode get in the way anywhere?"

For each real finding (a one-off slip that the rules already cover is not a
finding), write an entry in `plugin-feedback.md`: what happened, the guide and
section, and a small proposed edit (old text → new text). Never edit the installed
plugin; the learner applies accepted edits in their WiseCode repository. Show the
entries and say how many were added. If there were none, say so.
