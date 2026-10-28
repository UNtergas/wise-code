---
name: sharpen
description: Make a task, plan or prompt deeper, not bigger. Claude names what a top professional would do, the raw material, the methods, and an outside check; the learner rewrites the task themselves.
argument-hint: "<task, plan or prompt>"
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

# WiseCode Sharpen

Task: `$ARGUMENTS`

Sharpen deepens a task before the learner starts it. Adapted from pstack's
`sharpen` skill by Lauren Tan (MIT). The difference: you supply the ingredients,
and the learner writes the sharper version.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

1. If no task was given, ask for it. Restate it in one line.
2. Answer four questions, briefly and specifically for this task:
   1. What would a top professional do here that the task doesn't ask for?
   2. What is the rawest material they would start from, instead of something
      already digested (the spec instead of a blog post, the source instead of the
      docs, real data instead of a summary)?
   3. Which specific methods and tools would they use?
   4. What, other than the learner or you, would show the result is right (a test,
      a benchmark, a reviewer, a user, a spec)?
3. Aim for deeper, not bigger: more rigor on the same scope, not more scope. Leave
   choices that belong to the learner open; list them as open choices instead of
   deciding them.
4. Ask the learner to rewrite the task in their own words using what's useful, and
   wait.
5. Give short feedback on the rewrite: what got deeper, what only got bigger, and
   any choice it now decides that should stay open. Don't rewrite it for them
   unless they ask ("just rewrite it").

If a WiseCode state directory exists (see the [Learn guide](../learn/SKILL.md)),
nothing needs recording unless the learner asks.
