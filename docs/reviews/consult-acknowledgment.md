# Review: track consult acknowledgment independently of session dates

Review only: requested changes and implementation hints. No fix is included.

Reviewed commit: `f20e576ebf2b5542a39ed9c17ad5be2396d21ff3`.
Source: [hooks/session_start.py#L103](https://github.com/UNtergas/wise-code/blob/f20e576ebf2b5542a39ed9c17ad5be2396d21ff3/hooks/session_start.py#L103).

## Finding

consult_counts filters journal entries using the latest graph session date. A later session recap can exclude an unread consult, while same-day entries are repeatedly counted. There is no explicit evidence that the teacher reviewed an entry.

## Evidence and limits

A fixture with an unread disagreement dated 2026-11-03 and a session dated 2026-11-04 returned (0, 0). This reproduces the filtering gap; it does not claim that every normal session misses consults.

## Requested change

Represent pending versus acknowledged consults explicitly so a recap alone cannot make an unread disagreement disappear.

## Hint

Stable consult IDs plus separate acknowledgment state can distinguish receipt from review. Preserve Codex's ownership of the journal; decide where the teacher can record acknowledgment without editing it.

## Acceptance criteria

- An unread consult remains pending across subsequent session recaps.
- An acknowledged consult is not repeatedly announced after restart or compaction.
- Multiple same-day consults can be acknowledged independently.
- Interrupted review does not mark unseen entries as reviewed.

## Validation scope

This PR adds documentation only. Focused observations above come from the prior review of this same commit. The full suite and optional quality gates were not run for this documentation change.
