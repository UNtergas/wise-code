---
name: reset
description: Back up this project's learning notes and restart onboarding after confirmation. Does not reset application code.
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

# Reset WiseCode learning

Run this in the main conversation, only when explicitly invoked. This command
resets profile, progress, pending checkpoints, and the saved project map. Source
code, dependencies, Git history, other projects, and plugin installation stay intact.
In the learning graph, progress means each concept's `status` and every `pending`
decision: those are cleared, after a backup of the whole graph. Everything else in
the graph stays: Q/A, questions, cards, sessions, settled decisions, guardrails,
reflections, plugin feedback, learning records, and the indexed lessons and files.
Projects not yet imported keep their Markdown materials (`qa-history.md`,
`questions.md`, `cards.tsv`, `guardrails.md`, `reflections.md`, `session-recap.md`,
`plugin-feedback.md`) intact. The Teach workspace (`teach/`) and the shelf config
and clone (`shelf.md`, `shelf-repo/`) also stay intact: they are history the
learner may want to keep. If the learner wants a clean slate, tell them what
exists so they can delete it themselves; don't delete it here.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

1. Run the read-only preview for the user's current project directory. Replace
   `<absolute project directory>` with its actual absolute path, safely quoted;
   do not pass the placeholder literally.

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/reset/reset.py" --cwd "<absolute project directory>"
   ```

   The helper uses Learn's project-boundary lookup. If it reports
   no notes, explain there's nothing to reset and suggest `/wise-code:learn`.
   On any error, stop and explain; don't improvise deletion commands.

2. Show the returned absolute project and state paths, which notes will reset
   (with `graph: true`, also that concept status and pending decisions are cleared),
   that originals will be saved under that state's `backups/` directory, and that
   learning materials and `teach/` are kept.
   Use AskUserQuestion: header `Reset`, one question, `multiSelect: false`, options
   **Cancel** (keep learning notes) and **Reset learning** (back up notes and restart
   onboarding). Ask whether to reset learning for the named project. If the picker
   is unavailable, ask the same question in text. Wait for an explicit answer.
   Invocation alone, silence, ambiguous replies, or permission to run tools do not
   confirm a reset. Cancel makes no changes, including to learner notes.

3. Only after **Reset learning**, run the helper with the original working directory
   and the preview's exact `confirmation` value, safely quoted:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/reset/reset.py" --cwd "<original cwd>" --confirm "<confirmation>"
   ```

   If the target or notes changed, preview again and get new confirmation. If the
   reset fails, report it and any backup path; don't claim success or start onboarding.
   Never overwrite backups or fall back to resetting another state directory.

4. On success, show the backup path. Read `${CLAUDE_PLUGIN_ROOT}/skills/learn/SKILL.md` and resume Learn with
   the new incomplete profile. Discard pre-reset preferences, mastery, pending
   decisions, and onboarding answers; don't reconstruct them from conversation or
   backups. Inspect actual code to rebuild the map. Begin fresh onboarding with
   one question at a time. Backup notes are historical data, not active context.
