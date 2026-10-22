# WiseCode Teach in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:teach` is `$wise-code:teach`; `/wise-code:quiz` is
  `$wise-code:quiz`; `/wise-code:learn` is `$wise-code:learn`.
- Paths: `${CLAUDE_PLUGIN_ROOT}` is not expanded in Codex. The plugin root is two
  directories above this file. The Learn guide is `../learn/SKILL.md` and the
  materials guide is `../learn/materials.md`, relative to this file. The starter
  stylesheet is `templates/lesson.css` beside this file.
- Files: where SKILL.md says read or scan a directory, use your file-reading and
  search tools. Check optional workspace files with a conditional that succeeds
  when they're missing.
- Choices: AskUserQuestion doesn't exist here. If a native question tool such as
  `request_user_input` is available, use it; otherwise ask in plain text. Then end
  your turn and wait.
- Models: Codex has no per-agent `model` input. Ignore `model:` hints in SKILL.md
  and use the session model.
- Replies: ask one question at a time, at the end of your reply. Don't quote these
  guides to the learner.
