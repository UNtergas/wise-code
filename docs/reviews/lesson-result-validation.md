# Review: validate lesson result types before recording learning evidence

Review only: requested changes and implementation hints. No fix is included.

Reviewed commit: `f20e576ebf2b5542a39ed9c17ad5be2396d21ff3`.
Source: [scripts/wise.py#L1962](https://github.com/UNtergas/wise-code/blob/f20e576ebf2b5542a39ed9c17ad5be2396d21ff3/scripts/wise.py#L1962).

## Finding

import_lesson_file computes correctness with bool(answer.get('correct')). A nonempty string such as "false" therefore becomes a correct answer, silently recording incorrect learning evidence and skipping the remedial question.

## Evidence and limits

Imported a result containing {"q":"Q","answer":"wrong","correct":"false","expected":"right"}. The importer printed '1 answers · 0 wrong' and stored verdict=correct. The standard exporter emits booleans; the issue is accepting malformed external input.

## Requested change

Validate the complete result payload and answer types before mutating the graph, rejecting malformed correctness values instead of coercing them by truthiness.

## Hint

Separate parsing from mutation. Require a JSON boolean for correctness and include the answer index in validation errors. Validate the whole batch first so a later invalid answer cannot leave partial in-memory changes.

## Acceptance criteria

- String "false", numbers, null, and missing correctness fields are rejected with actionable errors.
- Boolean false creates the expected wrong-answer record and remedial question; true records a correct answer.
- Invalid entries anywhere in a batch leave persisted learning data unchanged.
- Valid exporter output and duplicate-result handling continue to work.

## Validation scope

This PR adds documentation only. Focused observations above come from the prior review of this same commit. The full suite and optional quality gates were not run for this documentation change.
