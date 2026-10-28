# WiseCode Grill in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:grill` is `$wise-code:grill`; `/wise-code:research` is
  `$wise-code:research`.
- Paths: the Learn guide and materials guide are `../learn/SKILL.md` and
  `../learn/materials.md`, relative to this file.
- Sub-agents: if you can't spawn one to look up a fact, look it up yourself before
  the round, and say so.
- Models: Codex has no per-agent `model` input. Ignore `model:` hints in SKILL.md
  and use the session model.
- Learning graph: `wise.py` is `python3 "<plugin root>/bin/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: put the round at the end of your reply, then end your turn and wait.
  Don't quote these guides to the user.
