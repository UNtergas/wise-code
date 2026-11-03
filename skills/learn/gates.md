# Quality gates

Deterministic checks for structure, duplication and test strength. They turn
"is this code good?" into numbers the learner can act on. Adapted from the
"Then Make it Right" part of ub-mode by Robert C. Martin (MIT); see
`THIRD_PARTY_NOTICES.md` at the plugin root.

The gates are Uncle Bob's companion tools. Each supports Clojure, Java, Go,
TypeScript (TSX, JavaScript), Rust and Python, and installs itself into a `.venv`
on first run:

| Gate | Tool | Measures | Passes when |
|---|---|---|---|
| Complexity | [crapper](https://github.com/unclebob/crapper) | CRAP score per function (cyclomatic complexity × missing coverage) | every changed function has CRAP < 10 |
| Duplication | [dryer](https://github.com/unclebob/dryer) | structural similarity between code forms | no changed form reaches similarity 0.8 |
| Test strength | [mutator](https://github.com/unclebob/mutator) | mutants the tests fail to kill, uncovered code | no surviving mutant in changed code |

## Finding the tools

Look for each tool in this order: an executable on `PATH` (`crapper`, `dryer`,
`mutator`), then a checkout next to the project (`../crapper/crapper`,
`../dryer/dryer`, `../mutator/mutator`). Mutator also needs crapper checked out
next to it (`../crapper`).

- No tool found → skip that gate silently. Gates are optional; never install them
  on your own or block a review because one is missing.
- The learner asks how to get them → point to the repositories above. They clone
  and run them; you don't.

## Running

Report on the change, not the whole tree. Crapper and mutator take `--changed`
(Git changes); dryer needs the whole tree, see below.
Run in this order, because each gate's fix can change the next one's result:

1. **crapper** `--changed`. Reads coverage from the project's test run; if no
   coverage is available, run with `--no-coverage` and say that the score is
   complexity only, not CRAP.
2. **dryer** `--threshold 0.8`, on the whole tree, without `--changed`. With
   `--changed`, dryer compares changed files only with each other, so code copied
   from an unchanged file is never seen. Report only the pairs where at least one
   form is in a changed file. Pass the threshold explicitly: dryer's default is
   0.82, which lets pairs from 0.80 to 0.82 pass.
3. **mutator** `--changed`. Slow: run it only when the learner asks, or at Full
   code before the Implementation report. Pass the project's test command with
   `--test-command` when it isn't detected.

The tools write results to `.metrics/` in the project root. If `.metrics/` isn't
ignored by Git, tell the learner once and let them add it to `.gitignore`.

## Reporting

Report what ran and what didn't, like any other check. Quote the tool's own
numbers and function names exactly; worst first; changed code only. A gate that
didn't run is "not run", never "passed".

## Fixing, by level

The numbers are evidence; the fix is a design decision, so it follows the assist
level in [assist-levels.md](assist-levels.md).

- **Hint**: name the function and its number, then the kind of problem
  ("`parse_span`: CRAP 14, complexity 7, 40% covered"). Ask which branch is
  untested, or which decision could move out. One finding at a time.
- **Pseudo**: describe the split or the missing test case as pseudocode.
- **Full code**: fix it yourself, in this order:
  - CRAP ≥ 10: split the function, test it, or both. A `match`/`switch` that
    is flat and exhaustive may be worth keeping; say why instead of splitting it.
  - Duplication ≥ 0.8: extract the shared form only when both copies encode the
    same decision (*Smallest change*: one decision in one place). Two forms that
    merely look alike stay apart; say so.
  - Surviving mutant: add the test that kills it. Uncovered code: cover it, or
    delete it if nothing reaches it.

Never weaken a test, raise a threshold, or add a suppression to make a gate pass.
A threshold the learner changes on purpose is their decision; record it with
`wise.py add decision`.
