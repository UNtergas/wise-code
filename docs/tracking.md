# Tracking your learning

What to look at, how often, and what the numbers mean. Everything here reads the
project's learning graph through `scripts/wise.py`; nothing is written. In this
guide `wise.py` means `python3 <wise-code>/scripts/wise.py`, run from the project
(or with `--root <project>`).

The graph records evidence, not time spent: what you answered, how sure you
were, what you got wrong and whether you fixed it. Track those. Lines of code,
session count and lessons opened say nothing about what you can do unaided.

## Three loops

| When | You do | Time |
|---|---|---|
| Every session | Start check, confidence prefix on answers, recap at the end | built in |
| Weekly | The five-command review below, then one Quiz round | 10 min |
| Monthly | `/wise-code:reflect`, `/wise-code:correct`, read the rendered views | 30 min |

The session loop only works if you end sessions out loud ("wrap up", "done for
today"). No recap means no start check next time, and that session's check
points are never tested.

## Weekly review

Replace the date with the day of your last review.

```sh
wise.py calibration --since 2026-11-08    # 1. do I know what I know?
wise.py confusions                        # 2. what is still wrong in my head?
wise.py weak --days 14                    # 3. where are the misses piling up?
wise.py mistakes --days 30                # 4. what do I keep getting wrong?
wise.py due --limit 20                    # 5. what is waiting for review?
```

1. **Calibration** is the most useful number in the graph. Read the `high` row:
   when you say `high:`, you should be right about nine times in ten. Lower
   means you build on things you only think you know; every "sure but missed"
   line is a misconception to repair this week. If `low` answers are mostly
   correct, you are underconfident: commit to answers faster. The numbers mean
   nothing without the prefix, so few answers in the table is itself a finding.
2. **Confusions** should trend to zero, with `skips open 0/2`. A confusion older
   than a week is a skipped repair: ask Claude to repair it before the next build
   step, even if that step doesn't touch the concept.
3. **Weak** with `--days 14` shows recent misses per concept. Without `--days` it
   counts every miss ever recorded and never forgets, so always pass it.
4. **Mistakes** lists concepts missed twice or more. Two misses on one concept
   is the trigger for `/wise-code:correct`: turn it into a type, lint or test
   you write, so the third miss can't happen. "guarded by G-…" means done.
5. **Due** is the review backlog. Clear it with `/wise-code:quiz`. More than
   about 15 waiting means questions are added faster than you review them: quiz
   before adding more.

## Is it sticking?

```sh
wise.py list question --where box=1 --limit 50   # new or recently failed
wise.py list question --where box=4 --limit 50   # survived 7 days
wise.py list question --where box=5 --limit 50   # survived 21 days
wise.py history --source quiz --since 2026-10-15
```

A question climbs one box per correct answer (1, 3, 7, 21, 60 days) and drops
to box 1 on a wrong one. Boxes 4 and 5 are what you retained for weeks; that
count growing month over month is the retention signal. A box 1 that stays
large means questions keep falling back: the concept needs a lesson
(`/wise-code:teach`) or a repair, not more quizzing.

In the quiz history, watch answers that were `correct` only with `hints`: those
are not yet yours.

## Monthly

- `/wise-code:reflect`: you write what changed in how you work; Claude checks it
  against the graph.
- `/wise-code:correct` for anything `mistakes` still shows unguarded.
- `wise.py render all --out /tmp/wise-review` and read `progress.md` and
  `qa.md` once. Fix what is wrong (`wise.py edit <id>`); delete questions you
  would never want to be asked again.
- `wise.py list feedback --where status=proposed`: apply or reject the fixes
  collected for wise-code itself.
- `wise.py export anki`, then File → Import in Anki, if you review cards there.
- Check your assist level per topic (`/wise-code:level`). Still on Pseudo for a
  topic after a month of clean answers: move it to Hint.

## Several projects

Each project has its own graph, on purpose. For one view across them, run the
same read-only command per project:

```sh
for p in ~/code/job-tracking ~/code/grammar-companion; do
  echo "== $p"; python3 <wise-code>/scripts/wise.py --root "$p" calibration --since 2026-11-01
done
```

## What the graph can't tell you

- Whether you can build without Claude. Test it directly: once a month, build
  one small piece with Claude closed, then run a Code review on it.
- Speed. Nothing is timed.
- Anything you didn't answer in your own words. A multiple-choice start-check
  answer carries no confidence and little evidence; the open questions are the
  ones that count.
- Whether a quote is really yours, until `wise.py check-said` has run (`check ok`).
