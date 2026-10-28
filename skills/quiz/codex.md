# WiseCode Quiz in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:quiz` is `$wise-code:quiz`; suggest `$wise-code:learn` or
  `$wise-code:teach` where SKILL.md says `/wise-code:learn` or `/wise-code:teach`.
- Arguments: if `$ARGUMENTS` wasn't substituted, read the topic and count from the
  text the user typed after the command.
- Paths: the Learn guide and materials guide are `../learn/SKILL.md` and
  `../learn/materials.md`, relative to this file.
- Files: learning data comes only from `wise.py`; it prints "nothing recorded
  yet" when the project has none.
- Learning graph: `wise.py` is `python3 "<plugin root>/bin/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask one question per reply, at the end of the reply, then end your turn
  and wait. Don't quote these guides to the learner.
