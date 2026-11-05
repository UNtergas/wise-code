# Review: reconcile divergent graph merge behavior with integrity rules

Review only: requested changes and implementation hints. No fix is included.

Reviewed commit: `f20e576ebf2b5542a39ed9c17ad5be2396d21ff3`.
Source: [scripts/wise.py#L451](https://github.com/UNtergas/wise-code/blob/f20e576ebf2b5542a39ed9c17ad5be2396d21ff3/scripts/wise.py#L451).

## Finding

_keep_version preserves equal-stamp conflicts but chooses the higher stamp for unequal stamps and drops the other record on the next save. Independent edits to different fields can be lost. docs/graph.md documents that loss, while AGENTS.md says two clones' edits must never be resolved by silently dropping one.

## Evidence and limits

Code inspection confirms whole-record selection by (updated, rev), with the losing line discarded on save. This behavior is explicitly documented and tested by test_higher_stamp_wins_in_either_line_order. A new end-to-end reproduction was not run for this finding.

## Requested change

Decide the intended divergent-edit contract and make the implementation, graph specification, review rules, and tests agree. Prefer preserving independent edits or surfacing a conflict over silent loss.

## Hint

A greater revision counter or later date does not establish ancestry: it cannot prove that one record includes the other's changes. Consider how to distinguish sequential updates from independent branches before choosing a merge policy.

## Acceptance criteria

- Exercise a real Git merge where two clones independently change different fields and have unequal stamps.
- Independent edits are preserved or explicitly presented for resolution under the chosen contract.
- Legitimate sequential updates and identical duplicates retain predictable behavior.
- Documentation, AGENTS.md, and tests describe the same policy and any intentional data-loss tradeoff.

## Validation scope

This PR adds documentation only. Focused observations above come from the prior review of this same commit. The full suite and optional quality gates were not run for this documentation change.
