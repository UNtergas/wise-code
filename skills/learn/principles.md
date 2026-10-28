# Engineering principles

A shared vocabulary for design and review. The learner applies these principles.
You use them to name what you see, so the learner can look the idea up, reason
about it, and decide. Adapted from pstack by Lauren Tan (MIT); see
`THIRD_PARTY_NOTICES.md` at the plugin root.

## How to use them

- **Name, don't apply.** At Hint and Pseudo, a principle's name plus a guiding
  question is a first-level hint ("This touches *Boundary discipline*: where does
  this input stop being untrusted?"). Don't explain how it applies to the
  learner's code until they ask for the next hint. Never rewrite their code to
  follow a principle.
- **One principle per finding**, at most two per reply. Use the exact names below
  so they stay searchable.
- **Proposals, not law.** A principle is a lens, not a requirement. The learner may
  reject one for a stated reason that fits the requirements; accept it and record
  their reasoning. Behavior.md still applies: explain tradeoffs, don't treat
  familiar patterns as mandatory.
- **Evidence.** When the learner applies a principle unprompted, or explains why one
  doesn't fit here, record it on the relevant concept in the learning graph
  (`notes+=`, see [materials.md](materials.md)) as demonstrated reasoning. Questions about principles go in the question bank in
  this project's terms ("Why does `parse_span` return a `Result` while `apply_rule`
  doesn't?"), never as definitions to recite.
- **At Full code**, name the principles that shaped the implementation in the
  Implementation report, so the learner can see the reasoning.
- Don't recite this list, quiz definitions, or cite a principle that adds nothing.

## Shape: before writing logic

**Data structures first.** When choosing core types, sequencing scaffold work, or
deciding what concurrent parts share. Get the data shape right and the logic gets
obvious. Scaffold (CI, lint, test setup, shared types) comes before features.
Ask: *What are the core types, and which access path dominates?*

**Model the domain.** When logic branches a lot, keeps two booleans in sync, or
repeats a shape assumption across files. Encode the domain in a structure: a state
machine, an enum or tagged union, a typed model, a lookup table. Don't force one
when the current code is already clear and local.
Ask: *Does the next new case add a branch, or a variant?*

**Type-system discipline.** When designing a type or a signature. Make illegal
states unrepresentable. Give semantic primitives their own types (a newtype
`ByteOffset` vs `CharOffset`, a branded `UserId`). Match exhaustively.
Ask: *Can the compiler reject this mistake instead of a runtime check?*

**Boundary discipline.** When wiring validation, errors, or adapters. Parse
untrusted input (CLI args, JSON, HTTP, config, files) into typed data at the
boundary, return errors there, and trust the types inside. Keep core logic in pure
functions the thin shell calls. Don't leak wire or storage types into the core.
Ask: *Is this data crossing a boundary right now? If not, why validate again?*

**Separate before serializing shared state.** When two tasks, threads, or
processes could write the same object, file, or key. First remove the sharing:
give each writer its own state and merge when reading. Add a lock, a single-writer
task, or a channel only when one shared target is a real invariant. "We need a
lock" is a smell to check.
Ask: *Do these actors need the same mutable thing, or are they publishing separate facts?*

**Make operations idempotent.** When designing commands, startup steps, or loops
that can crash or retry. Derive each step from the state that exists, apply only
the difference, and make leftovers (temp files, locks) recognizable as stale.
Ask: *What happens if this runs twice, or crashed halfway?*

## Simplicity

**Smallest change.** When sizing a diff or tempted to add a layer. Make the
smallest change that solves the problem. Put a repeated decision behind one source
of truth.
Ask: *What is the least code that meets the requirement?*

**Subtract before you add.** When starting an addition or rewrite. Remove dead
code and speculative guards first, then build on the simpler base. Design for
observed use, not imagined edge cases.
Ask: *What can I delete before I add this?*

**Minimize reader load.** When code is hard to follow. Count the layers a reader
traces and the state they must hold in their head. Inline one-caller wrappers;
prefer locals and pure functions over shared mutable state.
Ask: *Can a new reader answer "where does X come from, and what can change it?" in 30 seconds?*

**Redesign from first principles.** When a new requirement arrives. Don't bolt it
on. Ask what you would build if it had been a day-one requirement, then deliver
that design in small steps.
Ask: *If I started today with this requirement, what would the shape be?*

**Explore the design space.** When a decision has no precedent in the project.
Sketch two or three structurally different options before choosing. Whole shapes,
not tweaks of one shape. The learner sketches them; you may add one they missed
when they ask.
Ask: *What is a genuinely different way to structure this?*

**Experience first.** When scope or UX tradeoffs come up. Serve whoever consumes
the work: the end user, the caller of your module, the next maintainer. Fewer
polished features beat many rough ones.
Ask: *Who notices this change, and what do they notice?*

## Verification

**Prove it works.** Before calling a step done. Check the real artifact: run it,
read the actual value, inspect the actual output. "It compiles" and "the test
exists" are proxies. The strongest proof is a check script the learner wrote and
anyone can rerun.
Ask: *What did I observe that shows it works, not just that it builds?*

**Test behavior, not implementation.** When writing or keeping a test. Imagine
two edits. Break the behavior: the test must fail. Restructure the internals with
the same behavior: the test must still pass. Derive expected values from the
requirement, not from running the code.
Ask: *Would this test catch a wrong answer, and survive a refactor?*

**Sequence verifiable units.** For multi-step work. Small step, check, then the
next. Commit in an order that proves itself: the failing test first, then the fix.
Ask: *What is the next step that ends in something I can check?*

**Fix root causes.** When debugging. Reproduce first. Ask "why" until the answer
is a wrong decision in the code. Is the state that triggered the symptom
legitimate? If not, a guard where it crashed hides the bug; find what produced it.
Look for the same fault elsewhere.
Ask: *Where did the system first do something it shouldn't?*

**Attack the premise.** When two fixes that share one assumption have both failed.
Write the assumption down and test it directly before a third fix.
Ask: *What did both failed fixes assume, and how can I check it?*

**Explain the number.** Before trusting or reporting a measurement. See
[Checking a number](#checking-a-number).
Ask: *Why isn't it twice as good, and what else could this number be measuring?*

## Lessons

**Encode lessons in structure.** When the same mistake happens twice. Make it
impossible or loud, in this order: design, types, lint or CI, test, and a written
note last, only for judgment calls. `/wise-code:correct` runs this with the
learner.
Ask: *What would make this mistake fail to compile, or fail CI?*

## Checking a number

When the learner reports or is about to act on a measured number (latency,
throughput, memory, precision, false positives), ask the questions that apply, one
at a time, and let the learner answer with evidence. At Hint and Pseudo the
learner writes and runs the measurement; you may read and rerun it.

1. **The claim.** Write the sentence you would ship ("p95 check latency is 12 ms on
   the 40-sentence fixture set"). The other questions test that sentence.
2. **Why not double?** What limits it: one core, a lock, I/O, allocation, the load
   generator? Evidence comes from a profile or counters, not from reading code.
3. **Tuned the same?** Every side runs as it would for real: release build (for
   Rust, `cargo build --release`), same data, same cache state, same versions.
4. **Within limits?** Do the arithmetic. Removing a piece that takes 10% of the run
   makes it at most about 11% faster. A result past a limit measured something
   else.
5. **Errors and correctness?** Count failures, and check outputs are correct, not
   just present. Fast failures look like speed.
6. **Reproducible?** At least 5 runs per side, alternated. Report median and range.
   A gap smaller than the spread is no measurable difference.
7. **Does it matter?** Put a micro result next to the end-to-end path a user waits
   on, as a share of the whole.
8. **Did the work happen?** The timed region actually did the work: lazy iterators
   consumed, futures awaited, results used so the optimizer can't drop them (for
   Rust, `std::hint::black_box` or a benchmark harness such as Criterion).

Report: verdict first (faster, slower, no measurable difference, inconclusive),
then number with unit, run count, range, and limiter. Inconclusive when the limiter
is unknown, a side was untuned, or questions 5 and 8 were not checked.

## Not included

Left out of pstack's set on purpose: *Never block on the human* (in WiseCode the
learner's decisions are the point), *Guard the context window* (agent-internal),
*Migrate callers then delete legacy APIs* and *Outcome-oriented execution* (team
migrations). *Build the lever* is folded into *Prove it works*.
