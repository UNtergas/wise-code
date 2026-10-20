# Writing rubric

The standard Critique applies to the learner's technical writing. Adapted from
pstack's `technical-writing` and `unslop` skills by Lauren Tan (MIT), which build on
Diátaxis, Google developer documentation style, Simplified Technical English, and
Global English. Cite rules by their ID so the learner can look them up.

The goal is a tired engineer understanding the text on the first read. When a rule
makes a sentence worse, the sentence wins.

## M: mode (whole document)

- **M1 One document, one mode.** Tutorial (learn by doing), how-to (steps to a
  goal), reference (facts for lookup), or explanation (why, tradeoffs). Mixing
  them is a structure problem: split and link.
- **M2 Mode-specific shape.** A how-to is named by the task and has only steps. A
  reference describes without opinion. An explanation answers one real "why".
  An ADR states context, options, decision, consequences.
- **M3 Headings carry the point**, in sentence case, one level at a time.

## S: sentences

- **S1 Cut words that do no work.** "In order to" → "to". "It is important to note
  that" → nothing.
- **S2 Plain word.** "use", not "utilize"; "help", not "facilitate".
- **S3 Say who does what.** Active voice: "the parser rejects", not "is rejected".
- **S4 One thought per sentence.** Split sentences over about 25 words, or with
  clauses the reader must backtrack over.
- **S5 Condition before instruction.** "To reset, run X", not "Run X to reset".
- **S6 Instructions as commands.** "Run `cargo test`", not "tests should be run".
- **S7 Concrete over vague.** Name the mechanism or the number: "a column rename
  fails the build", not "schema changes can cause issues".
- **S8 Vary rhythm.** All short sentences read as machine-written; keep a long
  sentence that carries one thought with its condition.

## C: clarity (no second reading)

- **C1 One name per thing.** Don't call one component "the gate", "the check" and
  "the budget".
- **C2 Clear references.** Every "it", "this" and "they" points at one obvious noun.
  Repeat the noun when in doubt.
- **C3 Keep the small words.** Articles and "that" carry structure. "Remove backup
  file" reads two ways; "Remove the backup file" reads one.
- **C4 Place "only" and "not" next to what they change.**
- **C5 Break up noun stacks.** "the proto import budget check script" → "the script
  that checks the proto-import budget".
- **C6 No slashes, no "(s)", no "etc."** Write "a, b, or both".
- **C7 Real names.** Use the actual symbol, file, flag or command, in code font.

## T: tells and filler

- **T1 Inflated vocabulary**: crucial, delve, pivotal, leverage, robust, seamless,
  showcase, landscape. Use the plain word.
- **T2 Hedging stacks**: "could potentially possibly" → "may".
- **T3 Empty framing**: "Not just X, but Y", forced groups of three, generic
  conclusions ("this sets us up for success").
- **T4 Over-compression**: dropped articles, verbless fragments, arrows and
  abbreviations that the reader must decode. Fine in chat notes, wrong in docs.
- **T5 Formatting noise**: bold on every term, emojis in headings, a bold label that
  repeats the line after it.

## G: language

- **G1 Grammar and spelling.** Agreement, tense, articles, prepositions, word form
  (adjective where a noun is needed). Name the rule, not just the fix.
- **G2 French texts.** Apply M, S, C and T where they fit, plus French typography:
  the no-break space before `; : ! ?` and inside `« »`, accents on capitals, and
  agreement of past participles.
