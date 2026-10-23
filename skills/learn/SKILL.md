---
name: learn
description: Activate or resume learning-first development. You lead the design; Claude gives feedback, explains concepts, asks follow-ups, and writes the agreed code.
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

# WiseCode Learn mode

Activate learning mode in the main conversation. Read [behavior.md](behavior.md)
and [assist-levels.md](assist-levels.md) and follow them throughout normal
development, not just during this command. Keep this project's learning materials
(Q/A history, question bank, Anki cards) as described in [materials.md](materials.md).
Read [principles.md](principles.md) before the session's first hint, Design
checkpoint, or Code review; it names ideas for the learner to apply, not changes
for you to make.
The assist level (Hint, Pseudo, or Full code) decides who writes the real code;
check it before each step.
The learner owns the design. Ask for their approach and wait. Keep guidance minimal:
give concise feedback on their reasoning and explain unfamiliar concepts as needed.
Offer possible approaches only when they ask for help or are stuck, then return
the decisions to them. Learning and learner control take priority over build speed.
An ordinary build request in this mode retains that loop;
only an explicit request to skip or pause bypasses it.
Do not switch to a subagent. Require manual coding only at the Hint or Pseudo
assist level.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

Use the Read tool for plugin guides instead of printing them with Bash `cat`.
Use Glob to discover optional learner-state files before reading them. A missing
`.wise-code/` directory is normal first-time setup, not an error. If a shell
check is necessary, handle absence with an explicit conditional that succeeds;
don't run `ls` on a possibly missing directory or hide actual read failures.
Keep guide reads separate from optional state checks so a missing file doesn't
make a successful instruction read look like a failed tool call.

## Locate state

Starting at the current working directory, look upward for `.wise-code/`,
stopping at the nearest `.git` directory or file (including a worktree root).
Use the nearest existing state directory within that boundary. Without Git, check
only the current directory; don't search its parents. If there is none,
create `.wise-code/` at the Git root, or current directory without Git. Do not use
state from a parent repository, another worktree, or the installed plugin folder.
Everything WiseCode keeps for this project, including learning materials and the
Teach workspace (`teach/`), lives in this one directory. Nothing is written to a
global or shared location.
Do not follow symlinked state directories or files; explain the issue instead.

If `profile.md` exists, read it and `project-map.md`. Search the entire `progress.md`
for pending decisions, then read their complete sections and other topics relevant
to the task. An initial excerpt is not evidence that nothing is pending.
If `teach/learning-records/` exists, read the records relevant to the task;
concepts recorded there as understood aren't re-taught.
Resume without repeating completed onboarding or bypassing a pending Design or
Implementation checkpoint.
Set `Learning mode: active` if the user is resuming paused learning. If onboarding
is incomplete, ask only the unanswered questions. Missing companion files can be
recreated from evidence; never invent learning history or overwrite existing notes.

If no profile exists, read [onboarding.md](onboarding.md) and run onboarding.
Use [state-templates.md](state-templates.md) when creating state. These files are
local Markdown maintained with normal file tools; there is no service to call.

After setup, continue the user's build task. If none was provided, ask what they
want to build or change. Invoking this skill again should not reset anything.
