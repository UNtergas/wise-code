# Review: complete Claude shell protection for .env files

Review only: requested changes and implementation hints. No fix is included.

Reviewed commit: `f20e576ebf2b5542a39ed9c17ad5be2396d21ff3`.
Source: [scripts/setup.py#L38](https://github.com/UNtergas/wise-code/blob/f20e576ebf2b5542a39ed9c17ad5be2396d21ff3/scripts/setup.py#L38).

## Finding

The generated Read-tool deny rules include Read(**/.env), but sandbox.filesystem.denyRead contains only ~/.ssh, ~/.aws and ~/.config/gh. The README promises that .env files are unreadable through both the shell and Read tool.

## Evidence and limits

Calling merge_claude({}) confirmed the mismatch in the generated policy. Actual access inside Claude Code's sandbox was not tested; this finding establishes the missing generated restriction, not a demonstrated sandbox exploit.

## Requested change

Make the generated shell restrictions cover the documented .env scope, and align README wording with the actual policy.

## Hint

Treat shell access and Read-tool access as separate enforcement paths. Check supported path-pattern semantics before selecting a rule; do not assume a Read(...) rule constrains shell commands.

## Acceptance criteria

- Generated settings contain an appropriate .env restriction for both enforcement paths.
- An integration check attempts shell and Read-tool access to representative root and nested .env files and records actual results.
- Unrelated source files remain readable; existing user settings are preserved.

## Validation scope

This PR adds documentation only. Focused observations above come from the prior review of this same commit. The full suite and optional quality gates were not run for this documentation change.
