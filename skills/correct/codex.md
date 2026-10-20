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
- Files: check optional files such as `guardrails.md` with a conditional that
  succeeds when they're missing.
- Replies: ask one question per reply, at the end of the reply, then end your turn
  and wait. Don't quote these guides to the learner.
