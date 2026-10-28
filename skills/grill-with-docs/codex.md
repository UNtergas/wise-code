# WiseCode Grill with docs in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:grill-with-docs` is `$wise-code:grill-with-docs`;
  `/wise-code:grill`, `/wise-code:research` and `/wise-code:critique` are
  `$wise-code:grill`, `$wise-code:research` and `$wise-code:critique`.
- Arguments: if no plan was substituted after the command, read it from the text
  the user typed.
- Paths: the Learn guide and materials guide are `../learn/SKILL.md` and
  `../learn/materials.md`, relative to this file.
- Files: check for `GLOSSARY.md`, `GLOSSARY-MAP.md` and `docs/adr/` with
  conditionals that succeed when they're missing.
- Learning graph: `wise.py` is `python3 "<plugin root>/scripts/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask the round's 1-3 questions at the end of your reply, then end your
  turn and wait. Don't quote these guides to the user.
