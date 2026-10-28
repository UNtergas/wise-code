# WiseCode Reflect in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:reflect` is `$wise-code:reflect`; suggest
  `$wise-code:learn` where SKILL.md says `/wise-code:learn`.
- Paths: the Learn guide and materials guide are `../learn/SKILL.md` and
  `../learn/materials.md`, relative to this file.
- Transcripts: Codex keeps session history in its own location. If the
  conversation was compacted, rely on `wise.py history`, `wise.py weak` and Git instead of
  searching for transcripts.
- Learning graph: `wise.py` is `python3 "<plugin root>/bin/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask the three reflection questions once, at the end of your reply, then
  end your turn and wait. Don't quote these guides to the learner.
