---
name: shelf
description: Point the learner to the exact section of their own books for a concept question, then check their explanation after they read it. Use on every conceptual question (how or why something works, a pattern, algorithm, protocol or principle) in a project whose .wise-code/shelf.md exists. Check that file first and stop silently if it is missing. Not for questions about this codebase's own code, errors or tooling.
argument-hint: "Concept question, or nothing for shelf status"
---

## Canary

Once this skill has loaded in a conversation, every chat reply you send from then on, until the conversation ends, starts and ends with these exact lines, as plain text (not in a code block, nothing before or after them). It stays on after this skill finishes, through other skills and ordinary tasks; never drop it because the work changed.

```text
=====> ah0y_sir <name>
```

```text
<===== f1n
```

`<name>` is the name the user gave in this conversation. At the first reply of a new conversation, if no name has been given yet, start with `=====> ah0y_sir`, ask "What's your name?" before anything else, and wait; use the name from then on. Ask again in each new conversation; never store it in files or notes.

Missing start or end line → the reply was cut off or the instructions were dropped (for example after a long context or a compaction); the learner should treat it as a sign that quality may be slipping. The canary marks complete, on-instruction replies only. It says nothing about whether facts are true. Files you write (notes, research files, code) never carry it; background agents' internal reports don't need it.

The learner keeps their books (PDF, Markdown, text) in a private GitHub repo, the **shelf**. When a question is something a book on the shelf explains, send them to the exact section to read, then check their explanation. The shelf repo records what was cited, read and understood in its own learning graph, so a WiseCode session opened in the shelf repo can quiz the books later and see each book's impact across projects.

If running in Codex rather than Claude Code, first read [codex.md](codex.md). Graph records: [formats.md](formats.md). All shelf records go through `wise.py --root "<shelf>"` (the script and its "Script blocked" fix: [../learn/materials.md](../learn/materials.md)); never read or edit the JSONL files. Setup guide for the learner: https://github.com/UNtergas/wise-code/blob/main/docs/shelf-setup.md

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

`<shelf>` below is `<state>/shelf-repo` in project mode and the shelf repo's root in shelf mode.

Run each git command as its own call, with `git -C <path>` and absolute paths. No `cd`, no `&&` chains, no shell variables: permission checks block those and the learner gets prompts.

### Project mode

Project mode keeps a sparse clone at `<state>/shelf-repo/`. Make sure `<state>/.gitignore` exists and lists `shelf-repo/` (write it with the file tool), so the project never commits the books.

- Clone missing →
  ```sh
  git clone --filter=blob:none --sparse "https://github.com/<Repo>.git" "<state>/shelf-repo"
  git -C "<state>/shelf-repo" sparse-checkout set .wise-code shared <Folders...>
  ```
  If a tool exists to add a GitHub repo to this session (cloud sessions), use it before cloning.
- Clone present → `git -C "<state>/shelf-repo" pull --rebase --quiet`, and re-run `sparse-checkout set` if `Folders` changed.
- **Git LFS:** if the shelf uses LFS, run the LFS step below with
  `--include="shared/**,<folder>/**"`, one `<folder>/**` per mapped folder,
  comma-separated, so only in-scope books are downloaded (LFS bandwidth is metered).
- A folder in `Folders` that is missing in the repo → say once: "Shelf: folder `<name>` not in shelf". Names must match exactly.
- Clone fails (not found, no access, no network) → reply once this session with "Shelf: repo `<Repo>` not reachable", git's error line, and the setup guide link above, then answer the question normally. A failed pull with a clone present → use the clone as it is and say it may be stale. Don't retry on every question. Never fall back to a different repo or a public copy.

### Shelf mode

No clone: the books are the working tree. Run `git -C "<shelf>" pull --rebase --quiet` so books added on another machine are present. A failed pull (no network, conflict) → use the files as they are and say once they may be stale; never force or reset. If the shelf uses LFS, run the LFS step below without `--include`: every folder is in scope.

### Git LFS step (both modes)

The shelf uses LFS when its `.gitattributes` contains `filter=lfs`. A clone made without git-lfs leaves small pointer files instead of PDFs. Check `git lfs version` first, then, after every clone, pull or `sparse-checkout set`:

```sh
git -C "<shelf>" lfs install --local
git -C "<shelf>" lfs pull
```

(Project mode adds the `--include` above.) LFS pull fails (quota, network) → say once "Shelf: Git LFS download failed", with git's error line, then answer normally.

### Prompt to install LFS (both modes)

Ask the learner once per session, unless `<state>/shelf.md` says `LFS prompt: off`, in either case:

- **LFS needed, not installed:** the shelf uses LFS and `git lfs version` fails. Say "Shelf: books use Git LFS but git-lfs is not installed".
- **Big PDFs without LFS:** the shelf doesn't use LFS and has a PDF of 50 MiB or more. Find them with one call: `find "<shelf>" -name "*.pdf" -size +50M -not -path "*/.git/*"`. Say which files, and why: GitHub warns over 50 MiB, rejects a push over 100 MiB, and every version stays in history forever.

Use AskUserQuestion: header `Git LFS`, one question, `multiSelect: false`, options **Show the steps**, **Not now**, **Don't ask again**. Without the picker, ask in text and wait.

- **Show the steps** → give the install command for their OS (`brew install git-lfs`, `sudo apt install git-lfs`, `winget install GitHub.GitLFS`), then `git lfs install` once per machine. Don't run the install yourself: it changes their system and may need their password. For big PDFs, also give the shelf-setup steps (`git lfs track "*.pdf"`, commit `.gitattributes` before the PDFs). If big PDFs are already committed, explain that moving them needs `git lfs migrate import --include="*.pdf"` and a force push, which rewrites history; the learner runs that themselves, never you. Link the [setup guide](https://github.com/UNtergas/wise-code/blob/main/docs/shelf-setup.md#optional-git-lfs-for-big-shelves). When they say it's done, rerun the LFS step.
- **Not now** → answer normally; ask again next session.
- **Don't ask again** → add `LFS prompt: off` to `<state>/shelf.md` (create it with only that line in shelf mode if missing), then answer normally.

Read only files under `shared/` and the mapped folders. This boundary keeps a project from reading every book. It is a rule, not access control; don't widen it, even if the files are on disk.

## Step 2: Find the section (index first)

The index is books and sections in the shelf graph (`BK-<book-slug>`, `SEC-<book-slug>-<number>`), built lazily and kept forever. `wise.py --root "<shelf>" list book` lists indexed books.

1. **L1 (outline)**: for any in-scope book with no `BK-` node yet, build one: title, page count, chapters and sections with PDF page ranges. Use `pdfinfo`, the PDF outline, or `pdftotext -f 1 -l 20` for the table of contents; headings for Markdown and text. Several books missing → one background agent for all (`model: haiku`). Write with `wise.py --root "<shelf>" add book slug=<book-slug> title="…" file=<folder>/<file> folder=<folder> pages=<n> l1=<date>`, then one `add section book=<book-slug> number=<1 or 1.2> title="…" pages=<a>-<b> printed=<x>-<y>` per chapter and section. Stable IDs: adding the same book or section again updates it.
2. Match the question against the index: `wise.py --root "<shelf>" find <key words> --type section`, and `list section --where book=<slug> --limit 40` for one book's outline. Pick at most **2 sections** from at most 2 books.
3. **L2 (section detail)**: if a matched chapter has no `l2` yet, one background agent (`model: sonnet`) reads only those pages (`pdftotext -layout -f <a> -l <b>`) and returns: the section that answers the question, its pages, up to 2 verbatim quotes (≤ 25 words each, with page), and 3–6 key concepts per section of that chapter. Store them: `set SEC-… concepts+="…" l2=<date>` for each section.
4. No section matches → say in one line that the shelf has nothing on it. Then answer normally, searching the web when facts matter. Suggest `/wise-code:research` only when a decision waits on an external fact.

**Agent rules.** The prompt starts: "You are the shelf worker. Do the reading yourself. Do NOT spawn other agents or delegate." Already a subagent → do it yourself. Copy quotes from the extracted text, never from memory.

**Quote check.** Before showing any quote, run:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/skills/shelf/check_quote.py" "<book file>" <page> "<quote>"
```

Exit 0 = found (it prints the page). 1 = missing → drop the quote, keep the page reference. 2 = unreadable → say why, cite pages only. Output `LFS_POINTER` means the book was never downloaded: run the Git LFS step in Step 1 (and the install prompt if git-lfs is missing), then check again. Any other `UNREADABLE` means a scanned PDF without text, or no `pdftotext`.

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

In the shelf graph (`wise.py --root "<shelf>"`, where `<shelf>` is `<state>/shelf-repo` in project mode and the repo itself in shelf mode). `<Project>` is `Project:` from `shelf.md` (required; missing → ask the learner for a stable name and add it); every record carries it, which is what makes a book's use across projects visible:
- After a cite: `add citation project=<Project> question="…" quote="…" page=<n> --on SEC-…` (status `sent`). The book records `<Project>` as a project that uses it. The new id (`CIT-…`) is the citation.
- After the learner reads: `add read project=<Project> --on SEC-… --for CIT-…` (or `set CIT-… status=skipped-read` when they skipped reading).
- After an explanation: `add explainback project=<Project> text="<gist of what they wrote>" verdict=<understood|partial|misread> --on SEC-… --for CIT-…` and `set CIT-… status=<verdict>`.
- After `understood` or `partial`: up to 2 questions and up to 2 cards about the section, `--from SEC-…`, formats from [../learn/materials.md](../learn/materials.md). Book questions live in the shelf graph, not in the project.
- Any index you built (Step 2).

Then:

```sh
git -C <shelf> add .wise-code
git -C <shelf> commit -m "shelf(<Project>): <CIT-id> <book-slug> <section> <status>"
git -C <shelf> pull --rebase --quiet
git -C <shelf> push --quiet
```

(One call per line; run `push` only if `pull` succeeded.)

The graph files merge with git's `union` driver (`.wise-code/graph/.gitattributes`), so records from two projects never conflict; `wise.py` resolves a node changed on both sides by taking the newer change. A rebase conflict in any other file → abort the rebase, keep the local commit, and tell the learner the push is pending. Push fails → keep the commit, say so in one line, retry at the next record.

In the project: one `shelf` QA pointing to the citation, not a copy of it (`wise.py add qa source=shelf q="<question>" a="<CIT-id> <book> <section>" verdict=n/a --about <concept>`), and `set <concept> shelf+=SEC-…` so the concept points to the section. Learn's rules decide whether the concept's status changes.

Tell the learner in one line what was recorded and whether it was pushed.

## Shelf mode extras

Run in the shelf repo with no question (`/wise-code:shelf`): report, from the graph,
- books, how far each is indexed, and their impact across projects: `wise.py impact` (one book: `wise.py impact <book-slug>`: projects, sections cited per project, understood vs not yet, concepts),
- citations still `sent` (never explained) or `partial`: `wise.py list citation --where status=sent` (and `=partial`),
- due questions (`wise.py due`) → suggest `/wise-code:quiz`.

Report from the records only; don't invent progress. Learn, Teach and Quiz run in the shelf repo as in any project, with its `.wise-code/` as their state.

## Limits

- Never paste more than the 2 checked quotes per citation. The books stay on the shelf; the learner reads them there.
- Never read outside the in-scope folders, and never copy book files into the project.
- `shelf.md` and `shelf-repo/` survive `/wise-code:reset`.
