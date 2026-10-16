# wise-code

Personal Claude Code plugin for learning-first development. You own the design;
the assist level decides how much code Claude writes.

Fork of [VibeWise](https://github.com/nykooi1/vibe-wise) by Noah Kim (MIT).
Main change: three assist levels, defined in `skills/learn/assist-levels.md`.

| Level | Claude gives | You write real code |
|---|---|---|
| Hint (default) | Direction only, one hint at a time | Yes |
| Pseudo | Language-aware pseudocode + concepts | Yes |
| Full code | The agreed implementation | No |

At Hint and Pseudo, Claude never edits your source files. When you finish a step,
it runs a Code review: reads your changes, runs the project's checks, and gives
feedback at your level.

## Commands

- `/wise-code:learn` — start or resume learning mode.
- `/wise-code:level [hint|pseudo|full] [for <topic>]` — show or set the assist level.
- `/wise-code:reset` — back up learning notes and restart onboarding.

Switch levels in chat at any time:

- `level hint` / `level pseudo` / `level full` — change the default.
- `pseudo for Rust`, `hint for FastAPI` — per-topic override.
- `full code for this step` — one step only.

## Install (Claude Code)

```sh
/plugin marketplace add /absolute/path/to/wise-code
/plugin install wise-code@wise-code
```

Restart Claude Code, then run `/wise-code:learn` in your project.

## Notes

Learning notes live in `.wise-code/` at the Git root (add it to `.gitignore`).

Run tests: `python3 -m unittest discover -s tests`
