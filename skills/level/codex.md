# WiseCode Level in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:level` is `$wise-code:level`; suggest `$wise-code:learn`
  where SKILL.md says `/wise-code:learn`.
- Arguments: if `$ARGUMENTS` wasn't substituted, read the level from the text the
  user typed after the command.
- Choices: AskUserQuestion doesn't exist here. If a native question tool such as
  `request_user_input` is available, use it with the same options; otherwise ask
  the same question in text. Then end your turn and wait.
