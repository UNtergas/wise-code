---
name: grill
description: "Grill the user relentlessly about a plan, decision, or idea until nothing is left assumed. Use when the user asks to be grilled or to stress-test a plan. Also load it, without being asked, when the user describes a plan, feature, design, architecture or approach that still has open decisions and nothing is built yet: in that case only suggest running /wise-code:grill, never grill unasked. Skip factual questions (research) and tiny reversible edits."
---

## First: did the user ask for a grill?

- **Yes**: they ran `/wise-code:grill`, or said "grill me", "stress-test this" or
  similar. Grill, following the rest of this file.
- **No**: you loaded this because their message describes a plan with open
  decisions. Don't grill. Add one line at the top of your reply naming the open
  decisions you see and suggesting the command, then handle their message as you
  otherwise would:

  > Open decisions: storage, the position unit, offline behavior. Run
  > `/wise-code:grill` to settle them before building.

  Suggest at most once per plan in a conversation. If they ignore it or say no,
  don't bring it up again.

## Grilling

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. A fact from outside the repository (how a library or API behaves) is a job for `/wise-code:research`. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

## Learning mode

Check for this project's WiseCode state as the [Learn guide](../learn/SKILL.md)
describes. If `profile.md` exists and says `Learning mode: active`, the grill is
also a learning checkpoint, so change three things:

1. **Learner answers first.** Ask each question without the ➡️ recommendation.
   After the learner answers the round, add your recommendation only where it
   differs from theirs, with the reason, and let them keep or change their answer.
   If they say "recommend" for a question, give it for that question up front.
2. **The reasoning counts.** For a decision that matters, ask for the why in one
   line ("and what makes that better than B?"). A bare pick is a choice, not
   evidence of understanding.
3. **Record it.** Settled decisions go into `project-map.md` as chosen, in the
   learner's words. Reasoning that shows real understanding, or a real gap, gets a
   `checkpoint` entry in `qa-history.md` per [materials.md](../learn/materials.md).

With no profile, or `Learning mode: paused`, grill as written above.
