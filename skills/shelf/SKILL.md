---
name: shelf
description: Point the learner to the exact section of their own books for a concept question, then check their explanation after they read it. Use on every conceptual question (how or why something works, a pattern, algorithm, protocol or principle) in a project whose .wise-code/shelf.md exists. Check that file first and stop silently if it is missing. Not for questions about this codebase's own code, errors or tooling.
argument-hint: "Concept question, or nothing for shelf status"
---

## Canary

Every chat reply you send while this skill is active starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them):

```text
=====>
```

```text
<=====
```

Missing end line → the reply was cut off or the instructions were dropped; the learner should treat it as incomplete. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

The learner keeps their books (PDF, Markdown, text) in a private GitHub repo, the **shelf**. When a question is something a book on the shelf explains, send them to the exact section to read, then check their explanation. The shelf repo records what was cited, read and understood, so a WiseCode session opened in the shelf repo can quiz the books later.

If running in Codex rather than Claude Code, first read [codex.md](codex.md). File formats: [formats.md](formats.md). Setup guide for the learner: https://github.com/UNtergas/wise-code/blob/main/docs/shelf-setup.md

## Step 0: Gate (always, before anything else)

1. Find this project's state directory with Learn's lookup ([../learn/SKILL.md](../learn/SKILL.md), "Locate state"), but **never create** one here.
2. No state directory, or no `shelf.md` inside it (or it is a symlink) → this skill does nothing. Answer the question normally. Say nothing about the shelf.
3. Read `shelf.md`. Values are exact and case-sensitive: `Repo` is `owner/name`, each folder in `Folders` is a top-level folder name in the shelf repo. `shared` is always in scope.
4. Is the question book-shaped? Yes: a concept, mechanism, pattern, algorithm, protocol or principle a book could explain. No: this repo's own code ("where is X defined"), an error message, tool usage, project status, chit-chat. Not book-shaped → stop; answer normally.

Two kinds of session:

| cwd is | Mode | Books in scope | Records |
|---|---|---|---|
| a project with `shelf.md` | **project** | `shared/` + `Folders` | written to the shelf clone, pushed |
| the shelf repo itself (its `origin` is `Repo`, or `shelf.md` says `Mode: shelf`) | **shelf** | every folder | written in place, pushed |

## Step 1: Sync (once per session)

Project mode keeps a sparse clone at `<state>/shelf-repo/`. Make sure `<state>/.gitignore` exists and lists `shelf-repo/` (write it with the file tool), so the project never commits the books.

Run each git command as its own call, with `git -C <path>` and absolute paths. No `cd`, no `&&` chains, no shell variables: permission checks block those and the learner gets prompts.

- Clone missing →
  ```sh
  git clone --filter=blob:none --sparse "https://github.com/<Repo>.git" "<state>/shelf-repo"
  git -C "<state>/shelf-repo" sparse-checkout set .wise-code shared <Folders...>
  ```
  If a tool exists to add a GitHub repo to this session (cloud sessions), use it before cloning.
- Clone present → `git -C "<state>/shelf-repo" pull --rebase --quiet`, and re-run `sparse-checkout set` if `Folders` changed.
- **Git LFS.** If the shelf's `.gitattributes` contains `filter=lfs`, the books are LFS files, and a plain clone leaves pointer files instead of PDFs (unless LFS is set up globally). After the clone, and after every pull or `sparse-checkout set`, run:
  ```sh
  git -C "<state>/shelf-repo" lfs install --local
  git -C "<state>/shelf-repo" lfs pull --include="shared/**,<folder>/**"
  ```
  List one `<folder>/**` per mapped folder, comma-separated, so only in-scope books are downloaded (LFS bandwidth is metered). `git lfs` missing → say once "Shelf: books use Git LFS but git-lfs is not installed", with the setup guide link, then answer normally. LFS pull fails (quota, network) → say once "Shelf: Git LFS download failed", with git's error line.
- A folder in `Folders` that is missing in the repo → say once: "Shelf: folder `<name>` not in shelf". Names must match exactly.
- Clone fails (not found, no access, no network) → reply once this session with "Shelf: repo `<Repo>` not reachable", git's error line, and the setup guide link above, then answer the question normally. A failed pull with a clone present → use the clone as it is and say it may be stale. Don't retry on every question. Never fall back to a different repo or a public copy.

Read only files under `shared/` and the mapped folders. This boundary keeps a project from reading every book. It is a rule, not access control; don't widen it, even if the files are on disk.

## Step 2: Find the section (index first)

Index files live in the shelf at `.wise-code/shelf/index/<folder>/<book-slug>.md`. They are built lazily and kept forever.

1. **L1 (outline)**: for any in-scope book with no index yet, build one: title, page count, chapters and sections with PDF page ranges. Use `pdfinfo`, the PDF outline, or `pdftotext -f 1 -l 20` for the table of contents; headings for Markdown and text. Several books missing → one background agent for all (`model: haiku`).
2. Match the question against the index. Pick at most **2 sections** from at most 2 books.
3. **L2 (section detail)**: if a matched chapter has no section detail yet, one background agent (`model: sonnet`) reads only those pages (`pdftotext -layout -f <a> -l <b>`) and returns: the section that answers the question, its pages, up to 2 verbatim quotes (≤ 25 words each, with page), and 3–6 key concepts per section of that chapter. Add the section detail to the index; mark the chapter `[L2]`.
4. No section matches → say in one line that the shelf has nothing on it. Then answer normally, searching the web when facts matter. Suggest `/wise-code:research` only when a decision waits on an external fact.

**Agent rules.** The prompt starts: "You are the shelf worker. Do the reading yourself. Do NOT spawn other agents or delegate." Already a subagent → do it yourself. Copy quotes from the extracted text, never from memory.

**Quote check.** Before showing any quote, run:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/skills/shelf/check_quote.py" "<book file>" <page> "<quote>"
```

Exit 0 = found (it prints the page). 1 = missing → drop the quote, keep the page reference. 2 = unreadable → say why, cite pages only. Output `LFS_POINTER` means the book was never downloaded: run the LFS step in Step 1 and check again. Any other `UNREADABLE` means a scanned PDF without text, or no `pdftotext`.

## Step 3: Read first

Read first: the learner reads the section before you explain it.

Reply with:
- Book, section, pages (PDF page numbers; printed page in brackets when it differs).
- The checked quote(s), at most 2, as the hook.
- One guiding question to answer after reading. Ask for their explanation in their own words.

Don't summarize, paraphrase or explain the section in this reply. The parts of the question that are about this project's code follow the normal WiseCode flow (assist level, Learn behavior).

If the learner says "just tell me", "skip reading" or similar: explain it, and record the citation as `skipped-read`. That gives no understanding credit.

Then record and push (Step 5): one new citation, status `sent`.

## Step 4: Check the explanation

When the learner explains:
1. Compare it against the section (re-read the pages if they are not in context).
2. Feedback: what holds, what is missing or wrong, each gap pointing back to a page. Never rewrite their explanation into a model answer. Ask them to fix the gap, unless they ask for the answer.
3. Verdict: `understood` (core idea correct, in their words), `partial` (gaps named), or `misread` (wrong idea). Base it on what they wrote, not on effort.

Then record and push (Step 5).

## Step 5: Record and push (after every cite and every explanation)

In the shelf (`<state>/shelf-repo/` in project mode, the repo itself in shelf mode):
- `.wise-code/shelf/citations/<Project>.md`: add or update the citation entry.
- `.wise-code/shelf/reading/<book-slug>.md`: after an explanation, add the dated line with verdict and evidence.
- `.wise-code/questions.md` and `.wise-code/cards.tsv`: after `understood` or `partial`, add up to 2 questions and up to 2 cards about the section, formats from [../learn/materials.md](../learn/materials.md). `Source:` is `shelf C-NNNN <Project>`; card tags add `shelf` and the book slug. Book questions live here, not in the project.
- `.wise-code/shelf/index/...`: any index you built.

Then:

```sh
git -C <shelf> add .wise-code
git -C <shelf> commit -m "shelf(<Project>): <C-NNNN> <book-slug> <section> <status>"
git -C <shelf> pull --rebase --quiet
git -C <shelf> push --quiet
```

(One call per line; run `push` only if `pull` succeeded.)

Rebase conflict → resolve it if it is only appended entries on both sides (keep both); otherwise abort the rebase, keep the local commit, and tell the learner the push is pending. Push fails → keep the commit, say so in one line, retry at the next record.

In the project: append one line to `<state>/qa-history.md` pointing to the citation (`shelf C-NNNN`), not a copy of it. If `<state>/progress.md` exists, Learn's rules decide whether the concept goes there.

Tell the learner in one line what was recorded and whether it was pushed.

## Shelf mode extras

Run in the shelf repo with no question (`/wise-code:shelf`): report, from the records,
- books and how far each is indexed,
- citations per project, with status counts,
- sections still `sent` (never explained) or `partial`,
- due questions → suggest `/wise-code:quiz`.

Report from the records only; don't invent progress. Learn, Teach and Quiz run in the shelf repo as in any project, with its `.wise-code/` as their state.

## Limits

- Never paste more than the 2 checked quotes per citation. The books stay on the shelf; the learner reads them there.
- Never read outside the in-scope folders, and never copy book files into the project.
- `shelf.md` and `shelf-repo/` survive `/wise-code:reset`.
