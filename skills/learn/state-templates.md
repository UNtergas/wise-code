# Local state templates

Create only these two files in the chosen project's `.wise-code/` at setup. Use the directory selected by SKILL.md.
Learning progress, materials and the Teach workspace live in the learning graph,
written with `wise.py` once there is content; see [materials.md](materials.md).
Replace bracketed values with actual evidence or “Not specified.” Keep the two
status lines unformatted and near the top; the restoration hook reads them.
Do not replace existing state with a fresh template.

## profile.md

```markdown
# Learner Profile

Learning mode: active
Onboarding: complete

## Project
Situation: [New / Existing / Known]
Building: [project purpose]
Codebase familiarity: [answer]
Learning scope: [entire system / parts we touch / mixed]

## Experience
Overall programming: [Beginner / Intermediate / Advanced, or Not specified]
Stack familiarity: [per-technology levels if given; otherwise Not specified]

## Goals
Primary: [answer]
Capability goal: [optional answer]

## Preferences
Checkpoint frequency: Normal
Question style: Open-ended
Assist level: Hint
Level overrides: None

```

Concept understanding (demonstrated, developing, to revisit) is not kept here: it
is each concept's `status` in the graph (`wise.py weak`, `wise.py list concept`).

## Progress (in the graph)

There is no `progress.md`. As learning occurs, add or update a concept
(`wise.py add concept` / `set <slug> status=… notes+=…`): `introduced`,
`demonstrated`, or `reinforce`. Record reasoning evidence, not quotations of a
whole exchange; the dated evidence behind it is QA. Product preferences establish
requirements; they aren't evidence of engineering understanding. Keep
learner-proposed reasoning distinct from concepts the AI explained.

While waiting on a checkpoint, keep one `pending` decision
(`wise.py add decision title=… proposal=… stage=…`) with the proposed approach and
what reply is awaited. Its `stage` is `awaiting-reasoning`,
`choice-confirmation`, or `implementation-approval`. Settle it once resolved
(`set <id> status=settled outcome=… stage=`): record the outcome in the map as
chosen or implemented, labeling approved additions as the AI's, and any reasoning
evidence on its concept. Record confirmed choices in the map without claiming
they are implemented. Keep any proposed coding scope explicit.
Confirmation covers only the proposal presented. Don't append unmentioned fields,
behaviors, rejected alternatives, or reasons to the chosen design. Mark unresolved
details unknown and the AI's suggestions proposed; never attribute them to the learner.

## project-map.md

```markdown
# Project Map

## Purpose
[What this software does.]

## Requirements
[User needs and constraints. These do not automatically settle technical choices.]

## Components
[Components, responsibilities, and supporting file paths.]

## Main Flow
[Compact text diagram with labeled arrows. Mark unknowns and distinguish proposed,
chosen, and implemented components. Reflect the learner's model refined together,
or verified existing code; don't fill missing relationships with assumed designs.]

## Data and Trust Boundaries
[Storage, ownership, auth, external services; unknown when unverified.]

## Build and Deployment
[Commands and configuration paths verified in the repository.]

## Unknowns
[Unresolved technical choices and what needs inspection, including relevant stack,
storage location/model, data structures, interfaces, and deployment choices.]
```
