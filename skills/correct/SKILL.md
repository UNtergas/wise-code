---
name: correct
description: Find the learner's recurring mistakes in this project and have the learner make each one impossible or loud — design first, then types, lint or CI, tests, and a note last — proving every check fails on the old mistake.
argument-hint: "[topic]"
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

# WiseCode Correct

Topic filter: `$ARGUMENTS`

A mistake that happened twice will happen again. Correct turns the learner's
repeated mistakes into structure: a type, a lint, or a test that fails loudly.
The learner designs and writes each guard; you find the evidence, name the level,
and check the proof. Adapted from pstack's `correct` skill and the *Encode lessons
in structure* principle by Lauren Tan (MIT).

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

## 1. Locate state

Locate the state directory as the [Learn guide](../learn/SKILL.md) describes. If
there is none, say there is no history to mine and suggest `/wise-code:learn`;
don't create state. Read [principles.md](../learn/principles.md) and the
Guardrails section of [materials.md](../learn/materials.md).

## 2. Ask the learner first

Ask: "Which mistakes do you think keep coming back in this project?" Wait. Their
answer is a hypothesis to test against the evidence, not the result.

## 3. Find mistake classes

Evidence, in this project only:

- `wise.py mistakes --repeated`: concepts with repeated `wrong` and `partial`
  verdicts, their QA ids, and which are already guarded; `wise.py show <id>` for a
  QA's full text; `wise.py history --source review` and `--source critique`
- `wise.py weak`: concepts marked `reinforce`
- Git history: reverts, "fix" commits that undo a recent change, the same file
  fixed for the same reason twice
- existing guardrails (`wise.py list guardrail`), so you don't propose a class twice

Group findings into classes by cause, not by symptom ("byte index used as a char
index", not "panic in tokenizer"). A class counts once it has happened at least
twice. Count only the learner's own mistakes, not yours. Compare with the
learner's hypothesis: say which classes they named, which the evidence adds, and
which of theirs the evidence doesn't support.

## 4. Pick the level, together

Take the most frequent class first. Present its evidence (dates, entries,
commits). Then ask the learner how they would make it impossible. The levels, from
strongest to weakest:

1. **Design**: one owner, one supported way; remove the path that allowed it.
2. **Types**: the compiler rejects it (a newtype, an enum, exhaustive matching,
   no public constructor that skips validation).
3. **Lint or CI**: a check whose error names the fix (for Rust, a Clippy lint set
   to deny; otherwise a small script in CI).
4. **Test**: a behavior test that fails on the old mistake.
5. **Note**: a written rule, only for judgment calls nothing can check.

At Hint, name the highest level that seems to fit and ask why a higher one won't
work; don't design the guard. At Pseudo, give pseudocode for the guard. At Full
code, agree the design at an Implementation checkpoint, then write it. Follow
[assist-levels.md](../learn/assist-levels.md) for the current level.

## 5. Prove it

The guard counts only when it fails on the real past mistake. Ask the learner to
reintroduce the mistake temporarily (a scratch branch or an uncommitted edit),
show the check failing, then remove it and show the check passing. You may run the
checks to confirm. Quote the failure output exactly. Make sure the reintroduced
mistake doesn't stay in the code.

## 6. Record

Add or update the class's guardrail: `wise.py add guardrail mistake=… level=…
enforced_by=… --evidence <QA id> --evidence <QA id>`, then `set <id> proven="<date>:
<how it failed>"` after step 5; it stays `proven=no` until then. Note the
learner's reasoning about the level on the concept (`set <concept> notes+=…`).
One class per session is a good pace; offer to continue with the next.
