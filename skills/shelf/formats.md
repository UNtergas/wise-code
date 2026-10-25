# Shelf formats

Plain Markdown, edited with normal file tools. Dates are `YYYY-MM-DD`. Page
numbers are PDF page numbers (what `pdftotext -f` takes); write the printed page
in brackets when it differs.

## Project config: `<state>/shelf.md`

The learner writes this file in each project that uses the shelf. Its presence
turns the shelf on for that project.

```md
# Shelf
Repo: UNtergas/wise-code-shelf
Project: job-tracking
Folders: job-tracking
```

- `Repo`: exact `owner/name` of the private shelf repo.
- `Project`: name used for this project's citation file. Exact; keep it stable.
- `Folders`: comma-separated top-level folders of the shelf this project may
  read. Usually just the project's own folder. `shared` is always added.
- Optional `Mode: shelf` marks the shelf repo itself when its `origin` can't be read.

## Shelf repo layout

```
wise-code-shelf/
  shared/                  any project may read
  <folder>/                only projects listing <folder> may read
  .wise-code/
    shelf/
      index/<folder>/<book-slug>.md
      reading/<book-slug>.md
      citations/<Project>.md
    questions.md           book questions, quizzed in the shelf repo
    cards.tsv              book cards (deck named after the shelf repo folder)
```

Book slug: file name without extension, lowercase, spaces and underscores to `-`.
Supported files: `.pdf` with a text layer, `.md`, `.txt`.

## `index/<folder>/<book-slug>.md`

```md
# Designing Data-Intensive Applications
File: shared/ddia.pdf · Pages: 611 · L1: 2026-10-25

## Ch 1 Reliable, Scalable, and Maintainable Applications · pp. 25–46 [L2 2026-10-25]
- 1.1 Reliability · pp. 28–32 [6–10]: fault vs failure; hardware faults; software errors; human errors
- 1.2 Scalability · pp. 32–40 [10–18]: load parameters; percentiles; tail latency

## Ch 2 Data Models and Query Languages · pp. 49–90
```

A chapter without `[L2 …]` has only its heading and page range.

## `citations/<Project>.md`

One file per project, so two projects never edit the same file.

```md
# Citations · job-tracking

## C-0001 · 2026-10-25 · ddia 1.2 Scalability · pp. 32–40
Question: Why track p99 latency instead of the average for the job poller?
Quote: «…» (p. 35)
Status: understood
Updated: 2026-10-25
```

Status: `sent` → `understood` | `partial` | `misread`, or `skipped-read`.
Numbering: highest `C-` number in this file + 1.

## `reading/<book-slug>.md`

What the learner has read and shown they understood, across all projects.

```md
# Designing Data-Intensive Applications · reading

## 1.2 Scalability · pp. 32–40
- 2026-10-25 · job-tracking · C-0001 · understood · Explained why tail latency hits the slowest user requests; linked it to fan-out.
- 2026-10-28 · shared · quiz · partial · Mixed up p50 and mean.
```

Evidence is a gist of what they wrote, never a transcript.
