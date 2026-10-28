---
name: research
description: Answer a question about the outside world (how a third-party API behaves, what a spec says, whether a version claim holds) by reading primary sources and writing ONE cited Markdown file. Use when a decision is waiting on an external fact and the user says "research", "find out", "check the docs", "what does X actually do", or when a task turns into reading legwork. Not for decisions made with the user (grilling), testing in the codebase (prototype), or plans too big for one session.
argument-hint: "What do you need to find out?"
---

If you are running in Codex rather than Claude Code, first read [codex.md](codex.md).

## Canary

Every chat reply you send while this skill is active starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them):

```text
=====> ah0y_sir <name>
```

```text
<===== f1n
```

`<name>` is the name the user gave in this conversation. At the first reply of a new conversation, if no name has been given yet, start with `=====> ah0y_sir`, ask "What's your name?" before anything else, and wait; use the name from then on. Ask again in each new conversation; never store it in files or notes.

Missing end line → the reply was cut off or the instructions were dropped; the learner should treat it as incomplete. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

User needs an external fact. Read the sources that own the answer, write one cited Markdown file, report back. Research = legwork delegated, not thinking outsourced. User still decides.

## Contract

- Output is a **file**, never an answer in chat. Survives the session; can be reacted to, handed to another agent, or thrown away.
- Every claim carries a link to the **primary source** that owns it, plus one short **verbatim span** copied from that page.
- A script checks each span against the live page before the report goes out. Citation without a matching span = unverified.
- One file per run.
- Runs in the background so user's own session stays clean.

## Is this the right skill?

| Need | Use |
|---|---|
| External fact a decision waits on | `research` |
| Decision made *with* user, by interview | grilling |
| Does approach work in *this* codebase | prototype / spike |
| Plan too big for one session | break it down first |
| Tiny question, one lookup | just answer; skip the file |

Shelf-life test: research yields **short-lived facts** ("this lib's auth does X as of this week"). A decision you keep is an ADR, not research. Producing a decision → stop, grill instead.

## Step 0: Sharpen the question

Vague question = shallow-everywhere or deep-on-wrong-thing. Before reading anything, restate as **one narrow, answerable question** (one API, one behaviour, one version claim, one spec clause).

- Too broad ("research X") → ask user to narrow, or split into several narrow questions (one file each, one run each).
- Write down **what decision this unblocks** and **done criterion** ("done when I can state X with a link to Y"). This is the stopping rule; without it agents wander.

## Primary sources

Qualifying kinds, best first:
1. Source code of the thing itself (tagged version/commit, not a fork)
2. Official docs of the owner, versioned
3. Specs / RFCs / standards text
4. First-party API responses, changelogs, release notes, issue tracker of the owner
5. Peer-reviewed papers (for scientific claims)

Rules:
- Follow each claim back to the source that **owns** it. Blog post says API does X → read the API docs/code, cite those, not the blog.
- Blogs, forums, Q&A, AI summaries = **leads only**. May point to the primary source; never cited as evidence. If only secondary exists → mark claim `UNVERIFIED (secondary only)`.
- Note **version/date** of every source. Docs for v2 don't answer a v3 question.
- Sources conflict → report both with links; don't pick silently.
- Nothing found → say so. A gap is a result. Never fill from memory; never invent a link.

No allowlist exists, so the agent judges "high-trust". The verification pass below is the guard.

## Delegation

Run the reading as ONE background agent (Agent tool, `model: sonnet`), prompt includes the narrow question, done criterion, source rules, output path, file format and verbatim-span rules below.

**Nesting guard — critical.** Known failure: delegated agent re-delegates, spawning duplicates (huge token cost, hidden results). So:
- Background agent prompt MUST begin: "You are the research worker. Do the reading yourself. Do NOT spawn other agents or delegate."
- If *you* are already a subagent running this skill → do the work yourself, no delegation.
- After spawning, check agent list once. Exactly one task expected. Duplicate → stop it.
- Don't spawn agent at all if user's global rules forbid delegation; do the work inline and say so. Never silently do nothing.

Multiple independent narrow questions → one agent each, in parallel, never nested.

**Model.** Reading and citing is legwork; Sonnet handles it, and the main session keeps its model and cache. Use `model: opus` only when the question needs long multi-source reasoning (reconciling conflicting specs). If the Agent tool takes no `model` input, omit it.

## Where the file goes

Repo decides, not the skill.
1. Look for an existing notes convention (`docs/`, `notes/`, `research/`, `.notes/`, ADR dir). Follow it.
2. None → pick a sensible spot (`./research/`), tell user where.
3. Name: `YYYY-MM-DD-slug.md`.

Don't commit unless user asks. Research files record what was true on one day; stale ones are worse than none. Suggest delete/archive when decision made.

## File format

```md
# {Narrow question}

Date: YYYY-MM-DD · Unblocks: {decision} · Status: answered | partial | unanswered

## Answer
{2-5 sentences. Direct answer to the question, each claim linked.}

## Evidence
- **{Claim}** — {what source says, paraphrased}. «{exact span copied from the page}» [{Source title, version}]({url})
- ...

## Conflicts & gaps
- {Source A says X, B says Y} / {Not found: Z} / {UNVERIFIED (secondary only): claim, lead URL}

## Not checked
- {Out-of-scope adjacent things noticed but not chased}
```

Rules:
- Answer first. Reader should decide from this section alone.
- Paraphrase the claim; the «span» is the only quote on the line.
- Quote only short exact strings otherwise (error messages, signatures, config keys).
- Link as deep as possible (anchor, line permalink at a commit), not site root.
- No padding, no background tutorial, no recommendations. Facts only; recommendations = user's/grilling's job.

## Verbatim spans

Every Evidence bullet carries exactly one span, then its link: `«span» [title](https://…)`.

- **Copy, never recall.** Span is copied character-for-character from the page text the worker fetched in this run. Typed from memory = fabricated, even if "close".
- **≤ 15 words**, the smallest part of the page that states the claim. Must make the claim checkable on its own; a span of filler ("as shown below") proves nothing.
- One span per bullet; a claim resting on two sources = two bullets.
- Same URL as the link right after it, deep link included. Span from page A + link to page B = failure.
- No span available (video, image, page the tool can't render) → no span, and move the claim to **Conflicts & gaps** as `UNVERIFIED (no verbatim span): claim, url`.
- Span supports claim ≠ automatic. Matching words only prove the page says them; still check the claim doesn't overreach the span.

## Verification pass (before reporting)

**Step 1 — mechanical span check.** Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/research/verify_quotes.py" <research-file>
```

(Outside Claude Code: path to `verify_quotes.py` in this skill folder.) It fetches each link, strips to visible text, normalizes whitespace/case/typographic quotes and dashes, and looks for each span.

| Status | Meaning | Action |
|---|---|---|
| `FOUND` | span on the page | pass |
| `MISSING` | page loaded, span absent | re-open page, copy real span, or downgrade claim to UNVERIFIED. Never edit the span to "fit" without re-reading the page |
| `TOO_LONG` | > 15 words | shorten to the smallest part that states the claim |
| `NO_SPAN` | Evidence bullet without `«span» [link](https://…)` | add span or move to Conflicts & gaps |
| `UNREACHABLE` | fetch failed, non-text (PDF), JS-only page | open with your web fetch tool, check by hand, note `span checked manually` on the bullet |

Exit 0 = all found; 1 = failures; 2 = only unreachable. Report is not ready until exit 0, or exit 2 with every UNREACHABLE checked by hand. Script can't run (no Python, no network) → say so in the report and check every span by hand.

**Step 2 — judgement checks.** Do this yourself, don't trust the draft:

Do this yourself, don't trust the draft:
1. Pick 2-3 citations at random; open them; confirm the span means what the claim says (not taken out of context, not a different version).
2. Any link landing on a summary/write-up *of* the thing rather than the thing → run failed for that claim; fix or downgrade to UNVERIFIED.
3. Confirm every claim in **Answer** appears in **Evidence**.
4. Confirm done criterion met; if not, Status = `partial`/`unanswered`.

High-stakes decision → verify all citations, not a sample.

## Report back

Short, in chat:
- Status + one-line answer
- Span check: `verify_quotes.py` result (e.g. `7/7 FOUND`, or which were checked by hand)
- File path
- Gaps / UNVERIFIED items that matter
- One next step if real (e.g. feed file into grilling, attach to spec/ticket)

Nothing loads past research files automatically. File is useful only when user feeds it into the next step. Say so if relevant; don't assume reuse.

## It worked if

- User's session kept going (no sitting and watching).
- Exactly one background task ran.
- One new file, in the repo's notes folder, path reported.
- Every claim linked; random links land on official docs/spec/source, not write-ups.
- `verify_quotes.py` exit 0 (or 2 with each UNREACHABLE checked by hand).
- User can make the stuck decision from the file alone.
