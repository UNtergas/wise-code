# WiseCode Critique in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:critique` is `$wise-code:critique`; `/wise-code:correct` is
  `$wise-code:correct`.
- Arguments: if `$ARGUMENTS` wasn't substituted, read the file path or text from
  what the user typed after the command.
- Paths: the rubric is `writing-rubric.md` beside this file. The Learn guide and
  materials guide are `../learn/SKILL.md` and `../learn/materials.md`.
- Learning graph: `wise.py` is `python3 "<plugin root>/bin/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask about reader and intent once, at the end of your reply, then end
  your turn and wait. Don't quote these guides to the learner.
