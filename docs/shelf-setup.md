# Shelf setup

The shelf is a private GitHub repo holding your books (PDF, Markdown, text).
When a project with the shelf turned on gets a concept question, WiseCode sends you to
the exact section of the matching book. After you read it, you explain it in your own
words and WiseCode checks the explanation. Everything is recorded in the shelf
repo, so you can quiz yourself on the books later from there.

If you see "shelf repo not reachable", one of the steps below is missing.

## 1. Create the repo

Create a **private** repo, for example `wise-code-shelf`. Any name works, but the
`Repo:` line in step 4 must match it exactly (`owner/name`, case-sensitive).

## 2. Add books

```
wise-code-shelf/
  shared/            books any project may read
  job-tracking/      books only for projects that list job-tracking
  rust-wiki/         ...
```

- Folder names are exact and case-sensitive. Use the project's name for a
  project's own folder.
- Books outside any folder are ignored. Put general books in `shared/`.
- Supported: `.pdf` with a text layer, `.md`, `.txt`. A scanned PDF needs OCR
  first (for example `ocrmypdf in.pdf out.pdf`). Convert EPUB to PDF or Markdown.
- GitHub warns on files over 50 MiB, rejects files over 100 MiB, and wants a repo
  under 1 GB. Git keeps every version forever, so deleting a PDF later doesn't
  shrink the repo. A few dozen normal books fit in plain Git; past that, use LFS.
- Don't create `.wise-code/`. WiseCode creates it on the first citation.

### Optional: Git LFS for big shelves

With LFS, Git stores a small pointer and GitHub stores the PDF separately.
WiseCode detects it from `.gitattributes` and downloads only the folders a
project maps.

```sh
git lfs install
git lfs track "*.pdf"
git add .gitattributes shared/ job-tracking/
git commit -m "Add books"
git push
```

- Set this up **before** the first commit of PDFs. PDFs already committed
  without LFS stay in the history; moving them needs `git lfs migrate import`,
  which rewrites history.
- Free and Pro plans include 10 GiB of LFS storage and 10 GiB of download a
  month. Every clone downloads the mapped books again, and cloud sessions
  start fresh each time, so watch the bandwidth. Over quota without a payment
  method, LFS stops until next month, and WiseCode reports "Git LFS download failed".
- WiseCode asks once per session (project and shelf mode) when the shelf uses
  LFS but `git-lfs` is missing, or when the shelf has a PDF of 50 MiB or more
  without LFS. It shows the steps; you run the install and any history rewrite.
  Choose "Don't ask again" to write `LFS prompt: off` to `shelf.md`.
- Every machine running WiseCode needs `git-lfs` installed (`brew install git-lfs`,
  `apt install git-lfs`). Without it the books arrive as pointer files and WiseCode
  says "books use Git LFS but git-lfs is not installed".

## 3. Give Claude access

- **Claude Code on your machine** (terminal or desktop app): uses your own Git
  credentials. Check with `git ls-remote https://github.com/<you>/wise-code-shelf`.
  If it fails, run `gh auth login` or set up SSH.
- **Claude Code on the web / cloud sessions**: the Claude GitHub app must be able
  to access the shelf repo. Add it under your GitHub app installation settings,
  or attach the repo to the session.
- WiseCode pushes after every citation and every explanation, so the access must
  include write.

## 4. Turn it on in a project

Create `.wise-code/shelf.md` at the project's Git root:

```md
# Shelf
Repo: <you>/wise-code-shelf
Project: job-tracking
Folders: job-tracking
```

- `Project` is this project's stable name. Every shelf record carries it, so the
  shelf can show which projects use each book. Keep it the same on every machine.
- `Folders` lists the shelf folders this project may read, comma-separated.
  `shared` is always included.
- WiseCode clones only those folders to `.wise-code/shelf-repo/` (sparse clone)
  and adds `shelf-repo/` to `.wise-code/.gitignore`, so the books never enter the
  project's history.
- No `shelf.md` → the shelf stays off in that project, silently.

The folder rule limits what a project reads, so it doesn't load every book. It is
not access control: whoever can read the repo can read every folder.

## 5. Use it

- Ask a concept question in the project ("why does the poller need backoff?").
  WiseCode builds the book index on first use, then answers with a section, pages,
  and a short checked quote. Read it, then explain it back.
- "Just tell me" skips the reading; that citation gets no understanding credit.
- Open the shelf repo itself and run `/wise-code:shelf` for a status report
  (books, citations per project, sections still unread, and each book's impact
  across projects), and `/wise-code:quiz` for the book questions.
- Everything WiseCode records in the shelf lives in its learning graph,
  `.wise-code/graph/`, written by `bin/wise.py` (Python 3.9+ needed on every
  machine). Its files merge with git's `union` driver, so two projects pushing
  citations never conflict.

## Troubleshooting

| Message | Fix |
|---|---|
| shelf repo not reachable | Steps 1 and 3; check `Repo:` spelling |
| folder `x` not in shelf | Folder name in `Folders` doesn't match the repo exactly |
| quote unreadable | PDF has no text layer (OCR it) or `pdftotext` is missing (install poppler) |
| books use Git LFS but git-lfs is not installed | Install `git-lfs` on that machine |
| Git LFS download failed | LFS quota used up, or no network; check GitHub billing → Git LFS |
| push pending | Another project pushed first; WiseCode retries at the next record |
