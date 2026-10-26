---
name: level
description: Show or set the WiseCode assist level (Hint, Pseudo, or Full code), globally or for one topic or language.
argument-hint: "[hint|pseudo|full] [for <topic or language>]"
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

# Set the WiseCode assist level

Arguments: `$ARGUMENTS`

Levels are defined in [assist-levels.md](../learn/assist-levels.md). Hint is the
default. This command only changes the stored level; it doesn't reset notes or
repeat onboarding.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

1. Locate `.wise-code/profile.md` the same way as [the Learn guide](../learn/SKILL.md)
   (nearest `.wise-code/` up to the Git root, no symlinks). If there is no profile,
   say so and suggest `/wise-code:learn`; don't create state here.
2. Parse the arguments, ignoring case:
   - `hint`, `pseudo` (or `pseudocode`), `full` (or `full code`) set the default.
   - `<level> for <topic>` sets a per-topic or per-language override instead
     (for example `pseudo for Rust`).
   - `<level> for this step` applies to the current step only; don't write it to
     the profile.
   - `clear <topic>` removes that topic's override.
   - No arguments: report the current `Assist level:` (Hint if the line is
     missing) and `Level overrides:`, then ask which level to use with
     AskUserQuestion: header `Level`, one question, `multiSelect: false`, options
     **Hint**, **Pseudo**, **Full code**, each with its one-line description from
     assist-levels.md. If the picker is unavailable, ask in text.
   - Anything else: show the accepted forms and stop.
3. Update only the matching line in `profile.md`: `Assist level: <Hint|Pseudo|Full code>`
   or `Level overrides: <topic>: <level>; ...` (`None` when empty). Add the line
   under `## Preferences` if it's missing. Keep the rest of the profile unchanged.
4. Confirm the change in one line, quoting the new value. Report a failed write
   honestly. If learning mode is active, apply the new level from the next step.
