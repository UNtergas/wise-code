# WiseCode Explore in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:explore` is `$wise-code:explore`; suggest `$wise-code:learn`
  where SKILL.md says `/wise-code:learn`.
- Arguments: if `$ARGUMENTS` wasn't substituted, read the question from the text
  the user typed after the command.
- Paths: the Learn guide and materials guide are `../learn/SKILL.md` and
  `../learn/materials.md`, relative to this file.
- Subagents: if you can't spawn read-only subagents, investigate each angle
  yourself, one after another, and keep notes short.
- Models: Codex has no per-agent `model` input. Ignore `model:` hints in SKILL.md
  and use the session model.
- Learning graph: `wise.py` is `python3 "<plugin root>/bin/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask for the prediction once, at the end of your reply, then end your
  turn and wait. Don't quote these guides to the learner.
