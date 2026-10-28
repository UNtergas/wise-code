# WiseCode Correct in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:correct` is `$wise-code:correct`; suggest
  `$wise-code:learn` where SKILL.md says `/wise-code:learn`.
- Arguments: if `$ARGUMENTS` wasn't substituted, read the topic from the text the
  user typed after the command.
- Paths: the Learn guide, principles and materials guides are
  `../learn/SKILL.md`, `../learn/principles.md` and `../learn/materials.md`,
  relative to this file.
- Files: learning data comes only from `wise.py`; it prints "nothing recorded
  yet" when the project has none.
- Learning graph: `wise.py` is `python3 "<plugin root>/scripts/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask one question per reply, at the end of the reply, then end your turn
  and wait. Don't quote these guides to the learner.
