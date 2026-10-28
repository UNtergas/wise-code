# Shelf in Codex

These notes adapt Claude Code tool and command names for Codex. Follow SKILL.md
as written otherwise.

- Commands: `/wise-code:shelf` is `$wise-code:shelf`; `/wise-code:quiz` is
  `$wise-code:quiz`; `/wise-code:research` is `$wise-code:research`.
- Paths: `${CLAUDE_PLUGIN_ROOT}` is not expanded in Codex. The plugin root is two
  directories above this file. Run the quote check as
  `python3 skills/shelf/check_quote.py …` from the plugin folder.
- Delegation: if you can't spawn a sub-agent, do the index and page reading
  yourself and say so. Never more than one worker per step.
- Git: clone and push with the learner's existing credentials. If the sandbox
  blocks network or push, say so once and keep the records committed locally.
- Files: check optional files with a conditional that succeeds when they're missing.
- Models: Codex has no per-agent `model` input. Ignore `model:` hints in SKILL.md
  and use the session model.
- Learning graph: `wise.py` is `python3 "<plugin root>/scripts/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: ask the guiding question once, at the end of your reply. Don't quote
  these guides to the learner.
