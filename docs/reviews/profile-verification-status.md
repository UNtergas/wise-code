# Review: distinguish customized Codex profiles from verified restrictions

Review only: requested changes and implementation hints. No fix is included.

Reviewed commit: `f20e576ebf2b5542a39ed9c17ad5be2396d21ff3`.
Source: [scripts/setup.py#L318](https://github.com/UNtergas/wise-code/blob/f20e576ebf2b5542a39ed9c17ad5be2396d21ff3/scripts/setup.py#L318).

## Finding

existing_profile_item returns ok when the profile grants the current plugin path, without checking the remaining permission settings. Its status can therefore suggest successful setup even after important generated restrictions are removed.

## Evidence and limits

Generated a profile, changed ":root" = "deny" to ":root" = "write", and passed it to existing_profile_item with the same plugin root. The result was status=ok. This tests the checker, not whether Codex applies that edited permission.

## Requested change

Distinguish a verified generated profile from a customized profile whose restrictions have not been verified. Preserve deliberate user customization and report meaningful differences rather than overwriting it.

## Hint

File ownership, plugin-path validity, and permission-policy verification are distinct checks. Consider explicit statuses for customization or drift, with an explanation of changed security-relevant fields.

## Acceptance criteria

- An untouched generated profile reports verified/ok.
- Changing root access or removing expected restrictions cannot produce an indistinguishable verified result.
- Intentional customizations are retained and reported clearly.
- Plugin relocation still updates an unedited generated profile safely.

## Validation scope

This PR adds documentation only. Focused observations above come from the prior review of this same commit. The full suite and optional quality gates were not run for this documentation change.
