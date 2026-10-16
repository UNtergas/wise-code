---
name: level
description: Show or set the WiseCode assist level (Hint, Pseudo, or Full code), globally or for one topic or language.
argument-hint: "[hint|pseudo|full] [for <topic or language>]"
disable-model-invocation: true
---

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
