# wise.py integrity review and change requests

This is a review only. It proposes no implementation changes.

Reviewed current main: `2f4a9b84ad99a496665ce8f51af1ec3725da304e`.
The reproductions were run against the earlier local checkout `c0ae4a0`;
the relevant implementations were then checked in current main and remain
unchanged. Other changes in main, including learner quotation handling, are outside this review.

## 1. High: overlapping writers can silently lose records

Location: [Graph.save](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L286).

Each Graph instance loads a full snapshot, and save replaces both files using
that snapshot. There is no lock or stale-state check. Two instances loaded before
either saves can add different concepts; the second save removes the first
instance's addition. This was reproduced with two Graph instances; the same
interleaving is possible between CLI processes.

**Requested change:** protect the complete read/modify/write operation, or reject
a save whose source snapshot has changed. Never report success after silently
discarding another writer's work.

**Hint:** a lock only around file replacement is insufficient when loading
happened before the lock. Think about which snapshot the command actually edited.
If rejecting stale state, give a clear reload/retry message.

**Acceptance evidence:** coordinate two independent processes against one graph.
Either both additions survive, or one process fails explicitly without losing
the other's records. Include the case where the graph does not exist initially.

## 2. High: equal merge stamps discard one version arbitrarily

Locations: [stamp](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L166),
[Graph._load](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L255),
[Graph.touch](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L369).

The merge ordering key contains a calendar date and revision counter. Two clones
editing the same starting node once on the same day produce equal keys. For
different records with that key, the loader keeps whichever line appears last.
Reversing the duplicate lines changed the selected record in the reproduction.
A subsequent save removes the competing version.

**Requested change:** detect and surface divergent versions with equal ordering
keys, retaining the evidence until explicitly resolved. Document the intended
policy for divergent edits with unequal counters as well.

**Hint:** distinguish an identical duplicate from two different records with the
same identity and stamp. A random tie-breaker or higher-resolution timestamp
can choose a winner but cannot preserve both users' edits.

**Acceptance evidence:** load both line orderings of divergent equal-stamp
records. Neither may silently select and persist a winner. Identical duplicates
and unambiguously ordered versions should retain their documented behavior.

## 3. High: forced concept addition can replace an occupied ID

Location: [cmd_add](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L646).

`--force` bypasses similarity detection, including an exact existing concept ID.
The command builds a fresh node and assigns it to the occupied dictionary key.
In the reproduction, adding Alpha with notes and then adding Alpha with
`--force` removed the notes. Existing edges remain attached to the replacement.

**Requested change:** reject exact concept ID collisions even when forcing a
near-duplicate concept. Require an explicit update or a different ID.

**Hint:** keep “similar meaning” and “same identity” as separate checks.
The stable-ID upsert behavior for shelf books and sections is a different contract.

**Acceptance evidence:** a forced add with an occupied concept ID fails and leaves
the graph unchanged; forcing a distinct ID with a similar name still works.

## 4. Medium: a symlinked graph directory bypasses the file checks

Location: [Graph.__init__](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L243).

The constructor rejects symlinked nodes.jsonl and edges.jsonl but does not reject
a symlinked graph directory. Regular files inside its target pass those checks.
The reproduction saved nodes into a directory outside the selected state.

**Requested change:** enforce the documented no-symlink state boundary for the
graph directory and any newly introduced persistence files.

**Hint:** checking the final file alone says nothing about its parent directory.
Apply the same boundary rule to read and write paths.

**Acceptance evidence:** pointing graph/ at an external directory prevents both
reading and saving; external contents stay unchanged. Ordinary graph directories
and supported worktree layouts should continue to work.

## 5. Medium: accepted values can crash later commands

Locations: [coerce](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L385),
[validate_node](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L409),
[cmd_answer](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L824).

A question with `box=0` is accepted. Answering it partial raises `KeyError: 0`
when indexing BOXES. Validation also calls coerce without retaining its result:
an editor-provided string can pass a list-field check while remaining a string,
and metadata fields skip validation.

**Requested change:** validate domain ranges and stored JSON types. Malformed
records should produce actionable errors rather than downstream tracebacks.
Keep backward compatibility for legitimate historical records.

**Hint:** CLI text conversion and stored-record validation have different jobs.
Consider strict validation after conversion, including list element types,
metadata, and the allowed Leitner box range.

**Acceptance evidence:** invalid box values fail without modifying storage;
editor-provided incompatible field types and malformed metadata are rejected;
valid legacy records still load and operate.

## 6. Medium: two file replacements do not form one graph transaction

Location: [Graph.save](https://github.com/UNtergas/wise-code/blob/2f4a9b84ad99a496665ce8f51af1ec3725da304e/scripts/wise.py#L286).

Each replacement is atomic independently. An interruption after replacing nodes
but before replacing edges leaves different graph generations on disk. Deleting
a linked node is an example that can leave a dangling edge. This finding follows
from the two sequential replacements; crash injection has not yet been run.

**Requested change:** provide recoverable commit semantics for the graph as a
whole and prevent readers from observing a partially committed generation.

**Hint:** a journal, versioned snapshots with one atomic publication point, or
transactional storage are possible approaches. Preserve the current Git/JSONL
workflow when evaluating the tradeoffs. Define recovery behavior before choosing
a mechanism, and distinguish process-interruption guarantees from power-loss
durability.

**Acceptance evidence:** interrupt saving between each persistence step, then
reload in a new process. It must yield a consistent old or new graph, or recover
the intended commit, with no unexplained dangling references.

## Validation context

The local baseline suite ran 164 tests: 162 passed and two failed:
`test_no_git_folder_never_resets_parent_notes` and
`test_no_git_project_ignores_parent_folder_notes`.
This environment has a Git repository at /tmp, affecting those fixtures'
assumption that their temporary folders have no enclosing repository.
These results are for c0ae4a0, not a full test run of current main.

The focused reproductions confirmed stale-snapshot overwrite, equal-stamp
line-order dependence, forced concept replacement, graph-directory symlink
writes, and the invalid-box traceback. No fixes or new test implementations are
included in this PR.
