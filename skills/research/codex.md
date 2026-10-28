# Research in Codex

These notes adapt Claude Code tool names for Codex. Follow SKILL.md as written
otherwise.

- Delegation: SKILL.md says to run the reading as one background agent with the
  Agent tool. If you can't spawn a sub-agent, do the reading yourself in this
  session and say so in the report. Never spawn more than one worker per question.
- Web access: use your web search and fetch tools for primary sources. If you have
  none, say the run can't reach the sources and stop; don't answer from memory.
- Files: find the repo's notes folder with a conditional check that succeeds when
  a folder is missing.
- Span check: run `python3 skills/research/verify_quotes.py <file>` from the
  plugin folder (no `CLAUDE_PLUGIN_ROOT` in Codex). If Python or the network is
  unavailable, say so and check every span by hand.
- Models: Codex has no per-agent `model` input. Ignore `model:` hints in SKILL.md
  and use the session model.
- Learning graph: `wise.py` is `python3 "<plugin root>/scripts/wise.py"`; the plugin root is two directories above this file. If `python3` is blocked in the sandbox, ask the learner to allow it rather than writing Markdown notes.
- Replies: report back once, at the end of your reply. Don't quote this guide.
